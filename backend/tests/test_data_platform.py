"""Data platform (ELT into BigQuery). BigQuery is replaced by FakeWarehouse here; the SQL itself runs in
test_data_platform_bq.py against real BigQuery when AXIOM_BQ_INTEGRATION=1."""

import re
import sqlite3
from collections import Counter

import pytest

from axiom.db import Db
from axiom.memory.store import SCHEMA, USAGE_SCHEMA
from data_platform.config import Layout, TableSpec, load_config
from data_platform.extract import Batch, load_table
from data_platform.pipeline import models
from data_platform.seed import BASE_TS, seed
from data_platform.warehouse import FakeWarehouse

LAYOUT = Layout("proj", "test")


@pytest.fixture
def src(tmp_path):
    path = tmp_path / "synthetic.db"
    counts = seed(path, n_runs=60)
    return Db(path=path), counts


def load_all(wh, db, cfg, lookback=None):
    batch = Batch.new("sqlite:test")
    lb = cfg.lookback_seconds if lookback is None else lookback
    return {s.name: load_table(wh, LAYOUT, s, db, batch, lb) for s in cfg.tables.values()}


def _source_columns() -> dict[str, set[str]]:
    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA + USAGE_SCHEMA)
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return {t: {r[1] for r in con.execute(f"PRAGMA table_info({t})")} for t in tables}


def test_config_matches_the_real_store_schema():
    cols = _source_columns()
    for spec in load_config().tables.values():
        assert spec.name in cols, spec.name
        assert set(spec.columns) <= cols[spec.name], (spec.name, set(spec.columns) - cols[spec.name])


def test_config_rejects_bad_specs():
    with pytest.raises(ValueError, match="watermark"):
        TableSpec("t", "incremental", ["id"], {"id": "STRING"})
    with pytest.raises(ValueError, match="pk"):
        TableSpec("t", "snapshot", ["nope"], {"id": "STRING"})
    with pytest.raises(ValueError, match="redact"):
        TableSpec("t", "snapshot", ["id"], {"id": "STRING"}, redact={"id": "rot13"})


def test_seed_is_deterministic_and_big_enough_for_the_scorecard(tmp_path):
    a, b = seed(tmp_path / "a.db", n_runs=80), seed(tmp_path / "b.db", n_runs=80)
    assert a == b
    with Db(path=tmp_path / "a.db").connect() as c:
        n_dir = c.execute("SELECT COUNT(*) AS n FROM outcomes WHERE direction_hit IS NOT NULL").fetchone()[
            "n"
        ]
        first = c.execute("SELECT MIN(created_at) AS t FROM runs").fetchone()["t"]
    assert n_dir >= 30  # the scorecard mart only shows statistics from 30 directional calls
    assert BASE_TS <= first < BASE_TS + 86_400


def test_second_load_adds_nothing(src):
    db, counts = src
    wh, cfg = FakeWarehouse(), load_config()
    first = load_all(wh, db, cfg)
    sizes = {t: len(rows) for t, rows in wh.tables.items()}
    second = load_all(wh, db, cfg)

    for name, spec in cfg.tables.items():
        assert first[name].loaded == counts[name]
        if spec.mode == "incremental":
            assert second[name].loaded == 0, name
            assert second[name].extracted > 0 or counts[name] == 0  # the look-back window was re-read...
    assert {t: len(rows) for t, rows in wh.tables.items()} == sizes  # ...and skipped, so raw did not grow
    for name, spec in cfg.tables.items():
        versions = Counter(
            (*(r[c] for c in spec.pk), r.get("_wm")) for r in wh.tables[LAYOUT.fq("raw", name)]
        )
        if not spec.redact:
            assert max(versions.values()) == 1, name


def test_new_rows_and_changed_rows_are_picked_up(src):
    db, _ = src
    wh, cfg = FakeWarehouse(), load_config()
    load_all(wh, db, cfg)
    with db.connect() as c:
        top = c.execute("SELECT MAX(created_at) AS t FROM runs").fetchone()["t"]
        c.execute("INSERT INTO runs VALUES ('new1','AAPL',?,'{}','[]')", (top + 10,))
        tid = c.execute("SELECT thesis_id FROM outcomes LIMIT 1").fetchone()["thesis_id"]
        best = c.execute("SELECT MAX(scored_at) AS t FROM outcomes").fetchone()["t"]
        c.execute("UPDATE outcomes SET scored_at=?, ret_pct=99 WHERE thesis_id=?", (best + 10, tid))
        c.execute("UPDATE actions SET decided_at=?, status='executed' WHERE decided_at IS NULL", (top + 20,))
        n_decided = c.execute("SELECT COUNT(*) AS n FROM actions WHERE decided_at=?", (top + 20,)).fetchone()[
            "n"
        ]
    second = load_all(wh, db, cfg)
    assert second["runs"].loaded == 1
    assert second["outcomes"].loaded == 1  # a new version of an existing key; staging keeps the newest
    assert second["actions"].loaded == n_decided > 0
    assert second["theses"].loaded == 0


def test_late_commit_inside_the_lookback_is_not_lost(src):
    db, _ = src
    cfg = load_config()
    spec = cfg.tables["runs"]

    def late_insert(wh, lookback):
        with db.connect() as c:
            top = c.execute("SELECT MAX(created_at) AS t FROM runs").fetchone()["t"]
            # committed after the last load but stamped earlier than the newest row (clock skew, slow txn)
            c.execute("INSERT INTO runs VALUES (?, 'MSFT', ?, '{}', '[]')", (f"late{lookback}", top - 60))
        return load_table(wh, LAYOUT, spec, db, Batch.new("t"), lookback).loaded

    wh = FakeWarehouse()
    load_table(wh, LAYOUT, spec, db, Batch.new("t"), 0)
    assert late_insert(wh, 0) == 0  # positive control: with no look-back the row really is missed
    assert late_insert(wh, 3600) == 2  # with one, both late rows arrive (the earlier miss included)


def test_client_ips_never_reach_the_warehouse(src):
    db, _ = src
    with db.connect() as c:
        assert c.execute("SELECT COUNT(*) AS n FROM usage WHERE key LIKE 'ip:%'").fetchone()["n"] > 0
    wh = FakeWarehouse()
    load_all(wh, db, load_config())
    blob = repr(wh.tables)
    assert "198.51.100" not in blob
    assert {r["key"] for r in wh.tables[LAYOUT.fq("raw", "usage")]} == {"ip", "global"}


def test_every_staging_model_reads_a_configured_table():
    cfg = load_config()
    known = set(cfg.tables) | {"price_bars"}
    stg = models("staging")
    assert {m.name for m in stg} >= set(cfg.tables)  # each configured table has a staging model
    for m in stg + models("mart"):
        for layer, table in re.findall(r"\$\{(raw|staging)\}\.(\w+)", m.sql):
            assert table in known or (layer == "staging" and table in {x.name for x in stg}), (m.name, table)
        assert m.description, f"{m.path.name} needs a -- description: line"


def test_price_tables_are_partitioned_and_clustered():
    by_name = {m.name: m for m in models("staging") + models("mart")}
    for name in ("price_bars", "price_indicators"):
        assert by_name[name].partition_by == "date_key" and by_name[name].cluster_by == ["ticker", "date"]


def test_layout_renders_layer_placeholders():
    assert LAYOUT.render("SELECT * FROM `${raw}.runs` JOIN `${mart}.x`") == (
        "SELECT * FROM `proj.axiomtest_raw.runs` JOIN `proj.axiomtest_mart.x`"
    )
    assert Layout("p", "prod").dataset("staging") == "axiom_staging"


def test_a_partial_price_fetch_keeps_the_previous_window(tmp_path, monkeypatch):
    from data_platform import prices
    from data_platform.extract import Batch

    seed(tmp_path / "s.db", n_runs=5)
    db, cfg, layout, wh = Db(path=tmp_path / "s.db"), load_config(), Layout("p", "t"), FakeWarehouse()
    bar = {"date": "2026-11-09", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}

    async def ok(tickers, bars):
        return [{"ticker": t, **bar, "provider": "test"} for t in tickers], []

    async def outage(tickers, bars):
        return [], list(tickers)

    monkeypatch.setattr(prices, "fetch_bars", ok)
    first, _ = prices.load_prices(wh, layout, cfg, db, Batch.new("t"))
    assert first.rows > 0
    monkeypatch.setattr(prices, "fetch_bars", outage)
    res, failed = prices.load_prices(wh, layout, cfg, db, Batch.new("t"))
    assert failed and res.rows == 0
    assert len(wh.tables[layout.fq("raw", "price_bars")]) == first.rows  # history survives the outage
