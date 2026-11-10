"""Data-quality runner logic with a fake warehouse. The check SQL itself is proven against real BigQuery,
bad rows included, in test_data_quality_bq.py (AXIOM_BQ_INTEGRATION=1)."""

import re

import pytest

from axiom.db import Db
from data_platform import dq
from data_platform.config import Layout, load_config
from data_platform.models import models
from data_platform.pipeline import run
from data_platform.seed import seed
from data_platform.warehouse import FakeWarehouse

LAYOUT = Layout("proj", "test")
_NAME = re.compile(r"'(\w+)' AS check_name")


def responder(fail: dict[str, str] | None = None):
    """Answer every check query with one passing row, except checks named in `fail` (name -> table)."""
    fail = fail or {}

    def answer(sql: str):
        name = _NAME.search(sql).group(1)
        bad = name in fail
        return [
            {
                "check_name": name,
                "table_name": fail.get(name, "t"),
                "observed": 1.0 if bad else 0.0,
                "passed": not bad,
                "detail": "1 bad row" if bad else "",
            }
        ]

    return answer


@pytest.fixture
def src(tmp_path):
    seed(tmp_path / "s.db", n_runs=20)
    return Db(path=tmp_path / "s.db")


def test_every_check_file_declares_its_contract():
    files = models("dq")
    assert len(files) >= 9
    for m in files:
        assert m.severity in dq.SEVERITIES, m.path.name
        assert m.description, m.path.name
        for col in ("check_name", "table_name", "observed", "passed", "detail"):
            assert re.search(rf"\bAS {col}\b", m.sql) or (col == "table_name" and "table_name" in m.sql), (
                m.path.name,
                col,
            )
    names = {_NAME.search(m.sql).group(1) for m in files}
    assert {
        "not_null_keys",
        "unique_keys",
        "accepted_values",
        "value_ranges",
        "referential_integrity",
        "load_freshness",
        "source_freshness",
        "row_count_reconciliation",
    } <= names


def test_rendering_leaves_no_placeholders():
    counts = {"runs": 5, "usage": 6}
    for m in models("dq"):
        sql = dq.render(m, LAYOUT, counts)
        assert "${" not in sql, m.path.name
    lit = dq.source_counts_literal(counts)
    assert lit == '[STRUCT("runs" AS table_name, 5 AS n), STRUCT("usage" AS table_name, 6 AS n)]'
    assert dq.source_counts_literal({}).startswith("ARRAY<STRUCT<")


def test_critical_failure_stops_before_the_marts(src):
    wh = FakeWarehouse(responder=responder({"accepted_values": "theses.rating"}))
    rep = run(wh, LAYOUT, load_config(), src, source_label="t", with_prices=False)
    assert not rep.ok
    assert rep.dq_failed_critical == ["accepted_values:theses.rating (1 bad row)"]
    assert any(".axiomtest_staging." in t for t in wh.built)
    assert not any(".axiomtest_mart." in t for t in wh.built)  # bad data never reaches a dashboard
    written = wh.tables[LAYOUT.fq("mart", "dq_results")]
    assert len(written) == len(models("dq")) - 1  # price_bars_valid skipped: no price table without prices
    assert {r["batch_id"] for r in written} == {rep.batch_id}
    assert [r["check_name"] for r in written if not r["passed"]] == ["accepted_values"]


def test_all_checks_passing_builds_the_marts(src):
    wh = FakeWarehouse(responder=responder())
    rep = run(wh, LAYOUT, load_config(), src, source_label="t", with_prices=False)
    assert rep.ok
    marts = {t.rsplit(".", 1)[1] for t in wh.built if ".axiomtest_mart." in t}
    assert marts >= {"scorecard", "tool_latency_daily", "llm_usage_daily"}


def test_a_warning_is_recorded_but_does_not_block(src):
    wh = FakeWarehouse(responder=responder({"source_freshness": "runs+actions"}))
    rep = run(wh, LAYOUT, load_config(), src, source_label="t", with_prices=False)
    assert rep.ok and rep.dq_warnings == ["source_freshness:runs+actions (1 bad row)"]
    assert any(".axiomtest_mart." in t for t in wh.built)


def test_results_accumulate_across_runs(src):
    wh = FakeWarehouse(responder=responder())
    a = run(wh, LAYOUT, load_config(), src, source_label="t", with_prices=False)
    b = run(wh, LAYOUT, load_config(), src, source_label="t", with_prices=False)
    batches = {r["batch_id"] for r in wh.tables[LAYOUT.fq("mart", "dq_results")]}
    assert batches == {a.batch_id, b.batch_id}  # append-only history, one batch per run


def test_column_docs_name_real_columns():
    import yaml

    from data_platform import PKG_DIR

    docs = yaml.safe_load((PKG_DIR / "column_docs.yaml").read_text(encoding="utf-8"))
    sql = {(m.layer, m.name): m.sql for layer in ("staging", "mart") for m in models(layer)}
    for layer, tables in docs.items():
        for table, cols in tables.items():
            if (layer, table) == ("mart", "dq_results"):
                assert set(cols) == {n for n, _ in dq.RESULT_SCHEMA}
                continue
            body = sql[(layer, table)]
            for col in cols:
                assert re.search(rf"\b{col}\b", body), f"{layer}.{table}.{col} is not in the SQL"


def test_dashboard_reader_only_reads_marts():
    from data_platform.access import wanted

    grants = wanted("proj")
    assert set(grants) == {f"axiom{e}_{layer}" for e in ("", "dev") for layer in ("raw", "staging", "mart")}
    for dataset, roles in grants.items():
        reader = [r for r, who in roles if who.startswith("axiom-dashboard-reader@")]
        assert reader == (["roles/bigquery.dataViewer"] if dataset.endswith("_mart") else []), dataset
        assert ("roles/bigquery.dataEditor", "axiom-elt-loader@proj.iam.gserviceaccount.com") in roles
