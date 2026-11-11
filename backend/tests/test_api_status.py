"""/api/status: one public call. Config from /api/health plus store counts, nothing secret."""

import json
from datetime import UTC, datetime

from axiom.config import get_settings
from axiom.memory.store import get_store

from .test_api import env, make_client  # noqa: F401  (env is an autouse fixture, imported to apply here)


def test_status_on_an_empty_store():
    body = make_client().get("/api/status").json()
    assert body["ok"] and body["storage"] == "sqlite"
    assert body["counts"] == {
        "runs": 0, "last_run_at": None, "theses": {}, "actions": {}, "watchlist": 0, "trades": 0,
    }  # fmt: skip
    assert body["analyses_today"] == {"used": None, "cap": None}


def test_status_counts_what_the_store_holds(monkeypatch):
    monkeypatch.setenv("ANALYZE_PER_DAY", "40")
    monkeypatch.setenv("GROQ_API_KEY", "super-secret")
    get_settings.cache_clear()
    c = make_client()
    st = get_store()
    st.save_run("r1", "AAPL", {"memo": {"rating": "HOLD"}}, [])
    st.save_run("r2", "MSFT", {"memo": {"rating": "BUY"}}, [])
    st.watch_add("AAPL")
    st.hit("global", datetime.now(UTC).strftime("%Y%m%d"), 40)

    body = c.get("/api/status").json()
    assert body["counts"]["runs"] == 2 and body["counts"]["last_run_at"] is not None
    assert body["counts"]["watchlist"] == 1
    assert body["analyses_today"] == {"used": 1, "cap": 40}
    dumped = json.dumps(body)
    assert "super-secret" not in dumped


def test_health_is_unchanged_by_status():
    c = make_client()
    health = c.get("/api/health").json()
    status = c.get("/api/status").json()
    assert {k: status[k] for k in health} == health
    assert "counts" not in health
