"""The Store and TTLCache run on SQLite (default) and Postgres (deployed). These tests run every operation
on SQLite always, and on Postgres too when AXIOM_TEST_DATABASE_URL points at a disposable database."""

from __future__ import annotations

import os
import time
import uuid

import pytest

from axiom.data.cache import TTLCache
from axiom.db import is_postgres_url, upsert_sql
from axiom.memory.store import Store

PG_URL = os.environ.get("AXIOM_TEST_DATABASE_URL")


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param("postgres", marks=pytest.mark.skipif(not PG_URL, reason="no AXIOM_TEST_DATABASE_URL")),
    ]
)
def backend(request, tmp_path):
    return {"path": tmp_path / "s.db"} if request.param == "sqlite" else {"url": PG_URL}


def _tid() -> str:
    return uuid.uuid4().hex[:8].upper()


def test_upsert_sql_shape():
    sql = upsert_sql("runs", ["run_id", "ticker"], "run_id")
    assert (
        sql
        == "INSERT INTO runs (run_id, ticker) VALUES (?, ?) ON CONFLICT (run_id) DO UPDATE SET ticker=excluded.ticker"
    )


def test_url_detection():
    assert is_postgres_url("postgresql://u:p@h/db") and is_postgres_url("postgres://u@h/db")
    assert not is_postgres_url(None) and not is_postgres_url("sqlite:///x.db")


def test_runs_theses_outcomes_roundtrip(backend):
    st = Store(**backend)
    rid, ticker = uuid.uuid4().hex, _tid()
    st.save_run(rid, ticker, {"memo": {"rating": "buy", "conviction": 0.6}}, [{"seq": 1}])
    st.save_run(
        rid, ticker, {"memo": {"rating": "hold", "conviction": 0.4}}, [{"seq": 1}, {"seq": 2}]
    )  # upsert
    run = st.get_run(rid)
    assert run["result"]["memo"]["rating"] == "hold" and len(run["events"]) == 2
    listed = [r for r in st.list_runs(200) if r["run_id"] == rid]
    assert len(listed) == 1 and listed[0]["rating"] == "hold"

    tid = st.add_thesis(run_id=rid, ticker=ticker, issue_date="2026-01-02", horizon_days=20, price_at_issue=101.25,
                        rating="buy", conviction=0.6, stop_price=95.5, memo={"thesis": "x"}, findings=[{"a": 1}])  # fmt: skip
    assert st.theses(ticker=ticker)[0]["price_at_issue"] == 101.25
    st.save_outcome(tid, {"horizon_date": "2026-02-01", "price_at_horizon": 110.0, "ret_pct": 8.6,
                          "benchmark_ret_pct": 2.0, "excess_ret_pct": 6.6, "direction_hit": True,
                          "beat_benchmark": True, "stop_hit": False, "brier": 0.16, "detail": {"k": 1}})  # fmt: skip
    scored = st.scored(ticker)
    assert len(scored) == 1 and scored[0]["direction_hit"] == 1 and scored[0]["stop_hit"] == 0
    assert scored[0]["detail"] == {"k": 1} and st.theses(ticker=ticker)[0]["status"] == "scored"
    assert (
        abs(scored[0]["created_at"] - time.time()) < 60
    )  # float precision survives (REAL would not on Postgres)


def test_actions_idempotency_watchlist_trades(backend):
    st = Store(**backend)
    aid, run, ticker = uuid.uuid4().hex[:10], uuid.uuid4().hex, _tid()
    action = {
        "id": aid,
        "run_id": run,
        "ticker": ticker,
        "created_at": time.time(),
        "status": "pending",
        "steps": [],
    }
    st.save_action(action)
    st.save_action({**action, "status": "done", "decided_at": time.time(), "result": {"ok": True}})
    assert st.get_action(aid)["status"] == "done"
    assert any(a["id"] == aid for a in st.list_actions("done"))

    key = uuid.uuid4().hex
    assert st.claim_key(key, aid) is True and st.claim_key(key, aid) is False
    st.release_key(key)
    assert st.claim_key(key, aid) is True

    st.watch_add(ticker)
    st.watch_add(ticker)
    assert [w["ticker"] for w in st.watchlist()].count(ticker) == 1
    st.watch_remove(ticker)
    assert ticker not in [w["ticker"] for w in st.watchlist()]

    tr = st.add_trade(
        {"ticker": ticker, "side": "BUY", "quantity": 3, "entry_price": 10.5, "entry_date": "2026-01-02"}
    )
    st.close_trade(tr, 12.0, "2026-01-09")
    mine = [t for t in st.trades() if t["id"] == tr][0]
    assert mine["exit_price"] == 12.0
    st.delete_trade(tr)
    assert tr not in [t["id"] for t in st.trades()]


def test_usage_counter_is_a_hard_cap(backend):
    st = Store(**backend)
    key = "ip:" + _tid()
    assert [st.hit(key, "2026010201", 3) for _ in range(5)] == [True, True, True, False, False]
    assert st.usage(key, "2026010201") == 3  # refused hits are not counted
    assert st.hit(key, "2026010202", 3) is True  # a new window starts fresh
    assert st.hit(key, "w", 0) is True  # limit 0 means unlimited


def test_ttl_cache_roundtrip(backend):
    c = TTLCache(**backend)
    k = "k:" + _tid()
    assert c.get(k) is None
    c.set(k, {"a": [1, 2]}, 60)
    c.set(k, {"a": [3]}, 60)  # overwrite
    assert c.get(k) == {"a": [3]}
    c.set(k + "x", 1, -1)
    assert c.get(k + "x") is None  # expired
    assert c.clear(k) == 2  # prefix match: the live row and the expired one
    assert c.get(k) is None
