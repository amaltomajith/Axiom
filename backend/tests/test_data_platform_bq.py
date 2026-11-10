"""End-to-end ELT against real BigQuery (sandbox is fine). Opt-in: costs a few minutes and needs credentials.

AXIOM_BQ_INTEGRATION=1 AXIOM_GCP_PROJECT=<project> pytest tests/test_data_platform_bq.py
"""

import os

import pytest

from axiom.db import Db
from data_platform.config import Layout, load_config
from data_platform.pipeline import run
from data_platform.seed import seed

PROJECT = os.environ.get("AXIOM_GCP_PROJECT")
pytestmark = pytest.mark.skipif(
    os.environ.get("AXIOM_BQ_INTEGRATION") != "1" or not PROJECT,
    reason="set AXIOM_BQ_INTEGRATION=1 and AXIOM_GCP_PROJECT",
)


def _one(wh, sql):
    return list(wh.query(sql)[0].values())[0]


def test_pipeline_is_idempotent_and_gates_the_scorecard(tmp_path):
    from data_platform.warehouse import BigQueryWarehouse

    wh, layout, cfg = BigQueryWarehouse(PROJECT), Layout(PROJECT, "citest"), load_config()
    for layer in ("raw", "staging", "mart"):
        wh.client.delete_dataset(layout.fq(layer), delete_contents=True, not_found_ok=True)
    path = tmp_path / "src.db"
    db = Db(path=path)

    # 1) the first 20 runs of the history: too few directional calls, so the scorecard must stay empty (rule: 30)
    seed(path, n_runs=80)
    with db.connect() as c:
        cut = c.execute("SELECT created_at FROM runs WHERE run_id='syn00020'").fetchone()["created_at"]
        c.execute("DELETE FROM outcomes WHERE scored_at >= ?", (cut,))
        c.execute("DELETE FROM action_keys WHERE done_at >= ?", (cut,))
        for t in ("runs", "theses", "actions"):
            c.execute(f"DELETE FROM {t} WHERE created_at >= ?", (cut,))
        c.execute("UPDATE actions SET decided_at=NULL, status='pending' WHERE decided_at >= ?", (cut,))
    rep1 = run(wh, layout, cfg, db, source_label="sqlite:citest", with_prices=False)
    assert rep1.reconciled
    assert _one(wh, f"SELECT COUNT(*) FROM `{layout.fq('mart', 'scorecard')}`") == 0

    # 2) the rest of the history arrives (same deterministic rows, later timestamps): new rows load, actions
    #    decided since step 1 arrive as new versions, and staging keeps the newest one per key
    seed(path, n_runs=80)
    rep2 = run(wh, layout, cfg, db, source_label="sqlite:citest", with_prices=False)
    assert rep2.reconciled, rep2.reconciliation
    assert {x.table: x.loaded for x in rep2.loads}["runs"] == 60
    n_dir = _one(wh, f"SELECT COUNTIF(direction_hit IS NOT NULL) FROM `{layout.fq('staging', 'outcomes')}`")
    assert n_dir >= 30
    assert (
        _one(wh, f"SELECT COUNT(*) FROM `{layout.fq('mart', 'scorecard')}`") > 0
    )  # positive control for (1)

    # 3) nothing changed: nothing loads, and no table holds a duplicate key
    raw_before = {t: wh.count(layout.fq("raw", t)) for t in ("runs", "theses", "outcomes", "actions")}
    rep3 = run(wh, layout, cfg, db, source_label="sqlite:citest", with_prices=False)
    assert rep3.reconciled
    assert all(x.loaded == 0 for x in rep3.loads if x.mode == "incremental")
    assert {t: wh.count(layout.fq("raw", t)) for t in raw_before} == raw_before
    for spec in cfg.tables.values():
        if spec.redact:
            continue
        pk = ", ".join(spec.pk)
        dupes = _one(
            wh,
            f"SELECT COUNT(*) FROM (SELECT {pk} FROM `{layout.fq('staging', spec.name)}` GROUP BY {pk} HAVING COUNT(*) > 1)",
        )
        assert dupes == 0, spec.name
