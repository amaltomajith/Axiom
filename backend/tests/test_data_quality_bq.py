"""Positive controls for the data-quality checks, against real BigQuery (opt-in, a few minutes):

    AXIOM_BQ_INTEGRATION=1 AXIOM_GCP_PROJECT=<project> pytest tests/test_data_quality_bq.py

Clean synthetic data passes every critical check. Then one deliberately bad row per rule goes into the
source, and exactly the matching checks must fail, each counting exactly the injected row.
"""

import json
import os
import time

import pytest

from axiom.db import Db
from data_platform.config import Layout, load_config
from data_platform.dq import run_checks
from data_platform.pipeline import run
from data_platform.seed import seed

PROJECT = os.environ.get("AXIOM_GCP_PROJECT")
pytestmark = pytest.mark.skipif(
    os.environ.get("AXIOM_BQ_INTEGRATION") != "1" or not PROJECT,
    reason="set AXIOM_BQ_INTEGRATION=1 and AXIOM_GCP_PROJECT",
)


def _tool_event(seq: int, tool: str, latency: int, ts: float) -> dict:
    data = {"tool": tool, "ok": True, "latency_ms": latency, "chars": 10}
    return {
        "seq": seq,
        "ts": ts,
        "run_id": "x",
        "type": "tool_result",
        "agent": "Technical Analyst",
        "data": data,
    }


def inject_bad_rows(db: Db) -> None:
    now = time.time()
    with db.connect() as c:
        dup = [_tool_event(1, "get_indicators", 100, now), _tool_event(1, "get_indicators", 100, now)]
        odd = [_tool_event(1, "drop_all_tables", -5, now)]
        for rid, evs in (("bad_dup_seq", dup), ("bad_tool", odd)):
            c.execute("INSERT INTO runs VALUES (?, 'AAPL', ?, '{}', ?)", (rid, now, json.dumps(evs)))
        cols = "(id, run_id, ticker, created_at, issue_date, horizon_days, price_at_issue, rating, conviction, memo_json, findings_json)"
        for tid, rating, conviction in (
            (None, "HOLD", 0.5),
            ("bad_rating", "MOON", 0.5),
            ("bad_conv", "BUY", 1.7),
        ):
            c.execute(
                f"INSERT INTO theses {cols} VALUES (?, 'bad_dup_seq', 'AAPL', ?, '2026-11-10', 5, 100, ?, ?, '{{}}', '[]')",
                (tid, now, rating, conviction),
            )
        c.execute(
            "INSERT INTO outcomes (thesis_id, scored_at, horizon_date, price_at_horizon, ret_pct)"
            " VALUES ('ghost', ?, '2026-11-10', 100, 1.0)",
            (now,),
        )
        c.execute("INSERT INTO paper_trades (id, ticker, side, quantity, entry_price, entry_date) VALUES"
                  " ('pt_bad', 'AAPL', 'sideways', 1, 100, '2026-11-10')")  # fmt: skip
        c.execute("DELETE FROM runs WHERE run_id = 'syn00079'")  # a delete an incremental load cannot see


def failures(wh, layout, batch_id):
    rows = wh.query(
        f"SELECT check_name, table_name, severity, observed FROM `{layout.fq('mart', 'dq_results')}`"
        f" WHERE batch_id = '{batch_id}' AND NOT passed"
    )
    return {(r["check_name"], r["table_name"]): (r["severity"], r["observed"]) for r in rows}


def test_each_check_catches_its_bad_row_and_only_that(tmp_path):
    from data_platform.warehouse import BigQueryWarehouse

    wh, layout, cfg = BigQueryWarehouse(PROJECT), Layout(PROJECT, "dqtest"), load_config()
    for layer in ("raw", "staging", "mart"):
        wh.client.delete_dataset(layout.fq(layer), delete_contents=True, not_found_ok=True)
    db = Db(path=tmp_path / "src.db")
    seed(tmp_path / "src.db", n_runs=80)

    good = run(wh, layout, cfg, db, source_label="sqlite:dqtest", with_prices=False)
    assert good.ok, good.dq_failed_critical
    # synthetic history ends weeks ago, so the (warn-level) source freshness check rightly complains
    good_fail = failures(wh, layout, good.batch_id)
    assert set(good_fail) == {("source_freshness", "runs+actions")}
    assert good_fail[("source_freshness", "runs+actions")][0] == "warn"
    assert "mart.scorecard" in good.built

    inject_bad_rows(db)
    bad = run(wh, layout, cfg, db, source_label="sqlite:dqtest", with_prices=False)
    assert not bad.ok
    assert not any(k.startswith("mart.") for k in bad.built)  # the pipeline stopped before the marts
    assert failures(wh, layout, bad.batch_id) == {
        ("not_null_keys", "theses"): ("critical", 1.0),
        ("accepted_values", "theses.rating"): ("critical", 1.0),
        ("accepted_values", "paper_trades.side"): ("critical", 1.0),
        ("value_ranges", "theses"): ("critical", 1.0),
        ("value_ranges", "tool_calls"): ("critical", 1.0),
        ("referential_integrity", "outcomes"): ("critical", 1.0),
        ("unique_keys", "tool_calls"): ("critical", 1.0),
        ("row_count_reconciliation", "runs"): ("critical", 1.0),  # warehouse has one more run than the source
        ("known_tools", "tool_calls"): ("warn", 1.0),
    }

    # load freshness: the same warehouse judged three hours later must fail; judged now it passes
    later = run_checks(
        wh, layout, bad.source_counts, now_sql="TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 3 HOUR)"
    )
    now = run_checks(wh, layout, bad.source_counts)
    assert [r.passed for r in later.results if r.check_name == "load_freshness"] == [False]
    assert [r.passed for r in now.results if r.check_name == "load_freshness"] == [True]

    for layer in ("raw", "staging", "mart"):
        wh.client.delete_dataset(layout.fq(layer), delete_contents=True, not_found_ok=True)
