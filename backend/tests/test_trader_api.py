"""The /api/trader routes: public reads, guarded controls, kill and resume, red team, approvals, Time Machine."""

import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from axiom.api.app import create_app
from axiom.config import get_settings
from axiom.memory import store as store_mod
from axiom.trading.models import OrderRequest
from axiom.trading.service import Hub

from .conftest import make_ohlcv

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("AXIOM_API_TOKEN", TOKEN)
    for k, v in {"TRADER_BROKER": "sim", "TRADER_BRAIN": "rule", "TRADER_SYMBOLS": "BTC/USD,ETH/USD",
                 "TRADER_TIMEFRAME": "1Hour", "TRADER_AUTONOMY_START": "AUTONOMOUS",
                 "TRADER_ENABLED": "false"}.items():  # fmt: skip
        monkeypatch.setenv(k, v)
    for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    get_settings.cache_clear()
    store_mod._store = None
    yield
    get_settings.cache_clear()
    store_mod._store = None


def hourly(n=400, seed=5):
    df = make_ohlcv(n, seed=seed, drift=0.0004, vol=0.01)
    end = pd.Timestamp.now("UTC").tz_localize(None).floor("h") - pd.Timedelta(hours=1)
    df.index = pd.date_range(end=end, periods=n, freq="h")
    return df


def client(**kw) -> tuple[TestClient, object]:
    app = create_app()
    svc = app.state.trader
    data = {"BTC/USD": hourly(seed=5), "ETH/USD": hourly(seed=6)}

    async def fetch(sym):
        return data[sym.name]

    async def frames(symbols, bars):
        return {s.name: make_ohlcv(bars, seed=i + 3, drift=0.0006, vol=0.02) for i, s in enumerate(symbols)}

    svc.fetch_frames = frames
    t = svc.trader()
    t.fetch = fetch
    return TestClient(app, **kw), svc


def test_reads_are_public_and_report_paper():
    c, svc = client()
    with c:
        st = c.get("/api/trader/status").json()
        assert st["ok"] and st["paper"] is True and st["broker"] == "sim" and st["account"]["is_paper"]
        assert st["budget"]["daily_loss_limit_pct"] == 0.025 and st["ladder"]["level"] == "AUTONOMOUS"
        for path in ("positions", "orders", "journal", "journal/verify", "contracts", "calibration", "equity",
                     "tournament", "replays"):  # fmt: skip
            assert c.get(f"/api/trader/{path}").status_code == 200, path
        assert c.get("/api/trader/journal/verify").json()["ok"]
        assert c.get("/api/trader/journal?session=bad session").status_code == 422


def test_controls_need_the_token():
    c, _ = client()
    with c:
        assert c.post("/api/trader/kill").status_code == 401
        assert c.post("/api/trader/kill", headers={"Authorization": "Bearer nope"}).status_code == 401
        assert c.post("/api/trader/redteam").status_code == 401
        assert c.post("/api/trader/kill", headers=AUTH).json()["ok"]


def test_without_a_token_only_direct_local_requests_may_control(monkeypatch):
    monkeypatch.delenv("AXIOM_API_TOKEN")
    get_settings.cache_clear()
    remote, _ = client()
    with remote:
        assert remote.post("/api/trader/resume").status_code == 403
    local, _ = client(client=("127.0.0.1", 5000))
    with local:
        assert local.post("/api/trader/resume").status_code == 200
        tunneled = local.post("/api/trader/resume", headers={"cf-connecting-ip": "203.0.113.9"})
        assert tunneled.status_code == 403  # a Cloudflare tunnel also connects from loopback


async def _tick(svc):
    await svc.trader().start()
    return await svc.trader().tick()


def test_kill_flattens_journals_and_resume_releases():
    c, svc = client()
    with c:
        c.portal.call(_tick, svc)
        t = svc.trader()
        t.broker.set_price("BTC/USD", 100.0)
        c.portal.call(t.broker.submit, OrderRequest(symbol="BTC/USD", side="buy", qty=1))
        assert c.get("/api/trader/positions").json()
        r = c.post("/api/trader/kill", headers=AUTH, json={"reason": "demo"}).json()
        assert r["closed"] >= 1 and c.get("/api/trader/positions").json() == []
        assert c.get("/api/trader/status").json()["killed"] is True
        kinds = [e["kind"] for e in c.get("/api/trader/journal").json()]
        assert "kill" in kinds
        c.post("/api/trader/resume", headers=AUTH)
        assert c.get("/api/trader/status").json()["killed"] is False
        assert c.get("/api/trader/journal/verify").json()["ok"]


def test_redteam_is_blocked_and_the_poisoned_headline_is_flagged():
    c, svc = client()
    with c:
        c.portal.call(_tick, svc)
        r = c.post("/api/trader/redteam", headers=AUTH).json()
        assert r["approved"] is False and "R6" in r["failed_rules"]
        assert r["headline"]["flagged"] and "REDACTED" in r["headline"]["model_sees"]
        assert c.get("/api/trader/orders").json() == [] or all(
            o["qty"] < 1_000_000 for o in c.get("/api/trader/orders").json()
        )
        j = c.get("/api/trader/journal").json()
        assert any(e["kind"] == "blocked" and "Red team" in e["text"] for e in j)
        assert any(e["kind"] == "flag" and "Red team" in e["text"] for e in j)


def test_autonomy_and_supervised_approval_flow():
    c, svc = client()
    with c:
        assert c.post("/api/trader/autonomy", headers=AUTH, json={"level": "WILD"}).status_code == 422
        r = c.post("/api/trader/autonomy", headers=AUTH, json={"level": "SUPERVISED"}).json()
        assert r["autonomy"] == "SUPERVISED"
        st = c.get("/api/trader/status").json()
        assert st["ladder"]["ceiling"] == "SUPERVISED"
        eng = svc.trader().engine
        eng.st["pending"] = [{"id": "p-x", "created_at": time.time(), "intent": {"symbol": "BTC/USD",
                              "action": "enter_long", "stop_price": 95.0, "strategy": "sma_cross"},
                              "verdict": {"approved": True, "price": 100.0}, "decision": {"symbol": "BTC/USD",
                              "ts": time.time(), "action": "enter_long"}}]  # fmt: skip
        assert c.post("/api/trader/orders/p-missing/approve", headers=AUTH).status_code == 404
        assert c.post("/api/trader/orders/p-x/reject", headers=AUTH).json()["ok"]
        assert eng.st["pending"] == []


def test_time_machine_replay_runs_and_is_browsable_after():
    c, svc = client()
    with c:
        job = c.post(
            "/api/trader/replay", headers=AUTH, json={"bars": 400, "symbols": ["SPY", "BTC/USD"]}
        ).json()
        assert job["status"] in ("queued", "fetching", "running")
        assert (
            c.post("/api/trader/replay", headers=AUTH, json={"bars": 400}).status_code == 409
        )  # one at a time
        for _ in range(300):
            d = c.get(f"/api/trader/replays/{job['id']}").json()
            if d["status"] not in ("queued", "fetching", "running"):
                break
            time.sleep(0.05)
        assert d["status"] == "done", d
        assert d["report"]["verdict"]["verdict"] and d["progress"] == 1.0
        sess = job["session"]
        j = c.get(f"/api/trader/journal?session={sess}&limit=2000").json()
        assert j and c.get(f"/api/trader/journal/verify?session={sess}").json()["ok"]
        assert len(c.get(f"/api/trader/equity?session={sess}").json()) > 100


def test_backtest_report_endpoint(monkeypatch, tmp_path):
    import axiom.trading.service as service

    c, _ = client()
    with c:
        monkeypatch.setattr(service, "REPORT_JSON", tmp_path / "missing.json")
        assert c.get("/api/trader/backtest/report").status_code == 404
        p = tmp_path / "r.json"
        p.write_text('{"verdict": {"verdict": "no_edge"}}')
        monkeypatch.setattr(service, "REPORT_JSON", p)
        assert c.get("/api/trader/backtest/report").json()["verdict"]["verdict"] == "no_edge"


def test_a_broken_trader_config_is_reported_not_raised(monkeypatch):
    monkeypatch.setenv("TRADER_BROKER", "alpaca")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        st = c.get("/api/trader/status").json()
        assert st["ok"] is False and "ALPACA_API_KEY" in st["error"] and st["paper"] is True
        assert c.post("/api/trader/start", headers=AUTH).status_code == 409


async def test_hub_drops_oldest_for_slow_clients():
    hub = Hub(maxsize=2)
    q = hub.subscribe()
    for i in range(5):
        hub.publish({"i": i})
    assert [q.get_nowait()["i"] for _ in range(2)] == [3, 4]
    hub.unsubscribe(q)
    hub.publish({"i": 9})
    assert q.empty()


def test_serves_the_built_frontend_on_the_same_port(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    monkeypatch.setenv("SERVE_FRONTEND", "true")
    monkeypatch.setenv("FRONTEND_DIST", str(dist))
    get_settings.cache_clear()
    c = TestClient(create_app())
    assert c.get("/api/trader/status").json()["paper"] is True  # API routes win
    assert "id=root" in c.get("/").text
    assert "id=root" in c.get("/app?tab=autopilot").text  # SPA fallback for client routes
    js = c.get("/assets/app.js")
    assert js.text == "console.log(1)" and "immutable" in js.headers["cache-control"]
    assert c.get("/api/nope").status_code == 404  # unknown API paths stay 404, not index.html
    assert "nope" not in c.get("/../secret.txt").text
    assert "nope" not in c.get("/%2e%2e/secret.txt").text


def test_serve_frontend_without_a_build_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setenv("SERVE_FRONTEND", "true")
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path / "missing"))
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="build:selfhost"):
        create_app()


def test_desk_reviews_are_readable_after_a_restart_and_review_now_is_guarded():
    c, svc = client()
    rec = {"run_id": "r1", "symbol": "BTC/USD", "strategy": "sma_cross", "trigger": "manual", "started_at": 5.0,
           "finished_at": 9.0, "review": {"rating": "HOLD"}, "outcome": {"action": "veto"},
           "events": [{"seq": 1, "kind": "tool_call", "agent": "Technical Analyst", "data": {"tool": "run_backtest"}}]}  # fmt: skip
    svc.trader().engine.ledger.save_review(rec)

    c2, _ = client()  # a fresh app on the same database
    (row,) = c2.get("/api/trader/desk/runs").json()
    assert row["run_id"] == "r1" and row["outcome"] == {"action": "veto"} and "events" not in row
    full = c2.get("/api/trader/desk/runs/r1").json()
    assert full["events"][0]["data"]["tool"] == "run_backtest"
    assert c2.get("/api/trader/desk/runs/nope").status_code == 404

    assert c2.post("/api/trader/desk/review", json={"symbol": "BTC/USD"}).status_code == 401
    off = c2.post("/api/trader/desk/review", json={"symbol": "BTC/USD"}, headers=AUTH)
    assert off.status_code == 400 and "trading desk is off" in off.json()["detail"]
    assert "not_taken" in c2.get("/api/trader/calibration").json()


def test_guest_actions_allow_scenarios_and_reviews_but_nothing_that_touches_the_broker(monkeypatch):
    c, _ = client()
    with c:
        assert (
            c.post("/api/trader/replay", json={"scenario": "breakout"}).status_code == 401
        )  # off by default
        monkeypatch.setenv("TRADER_GUEST_ACTIONS", "true")
        get_settings.cache_clear()
        assert c.post("/api/trader/replay", json={"bars": 400}).status_code == 403  # only the named scenarios
        job = c.post("/api/trader/replay", json={"scenario": "breakout"})
        assert job.status_code == 200 and job.json()["scenario"] == "breakout"
        assert c.post(f"/api/trader/replays/{job.json()['id']}/stop").status_code == 200
        off = c.post("/api/trader/desk/review", json={"symbol": "BTC/USD"})
        assert (
            off.status_code == 400 and "trading desk is off" in off.json()["detail"]
        )  # allowed, desk is off here
        for path in ("/api/trader/kill", "/api/trader/resume", "/api/trader/redteam", "/api/trader/stop"):
            assert c.post(path).status_code == 401, path
        assert c.post("/api/trader/autonomy", json={"level": "AUTONOMOUS"}).status_code == 401
        assert c.post("/api/trader/orders/p-1/approve").status_code == 401
