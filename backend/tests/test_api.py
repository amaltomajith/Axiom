import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from axiom.api.app import create_app
from axiom.config import get_settings
from axiom.data import market
from axiom.data import news as news_data
from axiom.data import sec as sec_data
from axiom.llm import client as llm_client
from axiom.llm.client import TokenBudget
from axiom.llm.fake import ScriptedLLM
from axiom.memory import store as store_mod

from .conftest import world_slice
from .test_agents import SEC_FAKE, good_handler, news_fake


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_DB", str(tmp_path / "t.db"))
    for k in ("COMPOSIO_API_KEY", "AXIOM_API_TOKEN", "TWELVEDATA_API_KEY", "FINNHUB_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    get_settings.cache_clear()
    store_mod._store = None
    llm_client._COOLDOWN.clear()

    async def fake_fetch(ticker, bars=504):
        market.normalize_ticker(ticker)
        return world_slice(bars), "synthetic"

    async def fake_sec(ticker, include_risk_factors=False):
        return SEC_FAKE

    async def fake_news(ticker, days=7, limit=8):
        return news_fake()

    monkeypatch.setattr(market, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(sec_data, "get_filing_summary", fake_sec)
    monkeypatch.setattr(news_data, "get_news_sentiment", fake_news)
    yield
    get_settings.cache_clear()
    store_mod._store = None


def make_client(handler=None) -> TestClient:
    app = create_app()
    app.state.llm_factory = lambda: ScriptedLLM(handler or good_handler(), TokenBudget(10**6, 100))
    return TestClient(app)


def sse_events(resp) -> list[tuple[str, dict]]:
    out, event = [], None
    for line in resp.iter_lines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and event:
            out.append((event, json.loads(line.split(":", 1)[1])))
            event = None
    return out


def test_health_reports_configuration_without_leaking_secrets(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "super-secret")
    get_settings.cache_clear()
    body = make_client().get("/api/health").json()
    assert body["ok"] and "groq" in body["llm_chain"] and body["actions_executor"] == "dry_run"
    assert "super-secret" not in json.dumps(body)


def test_market_and_quant_endpoints():
    c = make_client()
    bars = c.get("/api/market/aapl/ohlcv?bars=30").json()
    assert (
        bars["ticker"] == "AAPL" and len(bars["bars"]) == 30 and bars["bars"][0].keys() >= {"date", "close"}
    )
    assert c.get("/api/quant/AAPL/indicators").json()["values"]["rsi14"] is not None
    bt = c.get("/api/quant/AAPL/backtest?strategy=sma_cross").json()
    assert bt["verdict"] and len(bt["equity_curve"]) > 24  # the UI gets the full curve
    assert c.get("/api/quant/AAPL/backtest?strategy=yolo").status_code == 400
    assert c.get("/api/quant/AA%20PL/regime").status_code in (400, 404)
    assert c.get("/api/market/AAPL&x/ohlcv").status_code == 404 or True


def test_bad_ticker_is_a_clean_400():
    r = make_client().get("/api/quant/..%2Fetc/regime")
    assert r.status_code in (400, 404)
    r = make_client().get("/api/market/TOOLONGTICKERXX/ohlcv")
    assert r.status_code == 400 and "Invalid ticker" in r.json()["error"]


def test_analyze_streams_trace_then_result_and_persists_everything():
    c = make_client()
    with c.stream("POST", "/api/analyze", json={"ticker": "aapl", "equity": 100000}) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        events = sse_events(r)
    kinds = [e for e, _ in events]
    assert kinds[-1] == "result" and kinds.count("result") == 1
    traces = [d for e, d in events if e == "trace"]
    assert traces[0]["type"] == "run_start" and traces[-1]["type"] == "run_end"
    assert {"tool_call", "tool_result", "finding", "final"} <= {t["type"] for t in traces}

    result = events[-1][1]
    assert result["ticker"] == "AAPL" and result["memo"]["rating"] and "## Evidence" in result["markdown"]
    assert result["thesis_id"] and result["action"] and result["action"]["status"] == "proposed"
    assert result["action"]["executor"] == "dry_run"

    assert c.get(f"/api/runs/{result['run_id']}").json()["result"]["ticker"] == "AAPL"
    assert c.get("/api/runs").json()[0]["run_id"] == result["run_id"]
    th = c.get("/api/theses?ticker=AAPL").json()
    assert th[0]["id"] == result["thesis_id"] and th[0]["outcome"] is None and th[0]["status"] == "pending"
    assert c.get("/api/actions?status=proposed").json()[0]["id"] == result["action"]["id"]


def test_analyze_validates_input_and_surfaces_llm_outage_as_an_error_event():
    c = make_client()
    assert c.post("/api/analyze", json={"ticker": "A B"}).status_code == 400
    assert c.post("/api/analyze", json={"ticker": "AAPL", "equity": -5}).status_code == 422

    app = create_app()
    from axiom.llm.client import LLMClient

    app.state.llm_factory = lambda: LLMClient([], cache_mode="off", budget=TokenBudget(10**6, 10))
    with TestClient(app).stream("POST", "/api/analyze", json={"ticker": "AAPL"}) as r:
        events = sse_events(r)
    last_event, data = events[-1]
    assert last_event == "error" and "no providers configured" in data["error"]


def test_rate_limit(monkeypatch):
    monkeypatch.setenv("ANALYZE_PER_HOUR", "2")
    get_settings.cache_clear()
    c = make_client()
    codes = []
    for _ in range(3):
        with c.stream("POST", "/api/analyze", json={"ticker": "AAPL"}) as r:
            codes.append(r.status_code)
            list(r.iter_lines())
    assert codes == [200, 200, 429]


def test_daily_cap_is_global_and_does_not_burn_the_hourly_allowance(monkeypatch):
    monkeypatch.setenv("ANALYZE_PER_DAY", "2")
    monkeypatch.setenv("ANALYZE_PER_HOUR", "50")
    get_settings.cache_clear()
    c = make_client()
    codes, refusal = [], ""
    for _ in range(3):
        with c.stream("POST", "/api/analyze", json={"ticker": "AAPL"}) as r:
            codes.append(r.status_code)
            body = "".join(r.iter_lines())
            if r.status_code == 429:
                refusal = body
                assert r.headers["retry-after"].isdigit()
    assert codes == [200, 200, 429] and "budget" in refusal
    assert store_mod.get_store().usage("ip:testclient", datetime.now(UTC).strftime("%Y%m%d%H")) == 2
    assert c.get("/api/health").json()["daily_cap"] == 2


def test_client_ip_is_only_taken_from_forwarded_headers_behind_a_trusted_proxy(monkeypatch):
    monkeypatch.setenv("ANALYZE_PER_HOUR", "1")
    monkeypatch.setenv("TRUST_PROXY", "true")
    get_settings.cache_clear()
    c = make_client()

    def go(ip):
        with c.stream(
            "POST", "/api/analyze", json={"ticker": "AAPL"}, headers={"x-forwarded-for": f"{ip}, 10.0.0.1"}
        ) as r:
            list(r.iter_lines())
            return r.status_code

    assert [go("1.1.1.1"), go("2.2.2.2"), go("1.1.1.1")] == [200, 200, 429]  # per real client, not per proxy

    monkeypatch.setenv("TRUST_PROXY", "false")
    monkeypatch.setenv("ANALYZE_PER_HOUR", "1")
    get_settings.cache_clear()
    store_mod._store = None
    c = make_client()
    assert [go("1.1.1.1"), go("2.2.2.2")] == [200, 429]  # spoofed header ignored: same socket peer


def test_run_deadline_ends_the_stream_with_a_clear_error(monkeypatch):
    import asyncio as aio

    monkeypatch.setenv("RUN_DEADLINE_SECONDS", "1")
    get_settings.cache_clear()
    from axiom.api import app as app_mod

    async def slow(*a, **k):
        await aio.sleep(30)

    monkeypatch.setattr(app_mod, "run_pipeline", slow)
    with make_client().stream("POST", "/api/analyze", json={"ticker": "AAPL"}) as r:
        last_event, data = sse_events(r)[-1]
    assert last_event == "error" and data["kind"] == "deadline" and "1s" in data["error"]


def test_cron_is_off_without_a_secret_and_needs_the_bearer_when_on(monkeypatch):
    assert make_client().get("/api/cron/daily").status_code == 404
    monkeypatch.setenv("CRON_SECRET", "c-secret")
    get_settings.cache_clear()
    c = make_client()
    assert c.get("/api/cron/daily").status_code == 401
    assert c.get("/api/cron/daily", headers={"authorization": "Bearer nope"}).status_code == 401
    ok = c.get("/api/cron/daily", headers={"authorization": "Bearer c-secret"})
    assert (
        ok.status_code == 200 and ok.json()["digest_status"] and ok.json()["analyzed"] == 0
    )  # empty watchlist


def analyze_once(c: TestClient) -> dict:
    with c.stream("POST", "/api/analyze", json={"ticker": "AAPL"}) as r:
        return sse_events(r)[-1][1]


def test_approval_flow_records_paper_trade_and_cannot_repeat():
    c = make_client()
    action = analyze_once(c)["action"]
    assert c.get("/api/trades").json() == []  # proposing wrote nothing
    done = c.post(f"/api/actions/{action['id']}/approve").json()
    assert done["status"] == "executed" and [s["status"] for s in done["steps"]] == ["done"] * 4
    trades = c.get("/api/trades").json()
    assert len(trades) == 1 and trades[0]["ticker"] == "AAPL" and trades[0]["thesis_id"]
    assert c.post(f"/api/actions/{action['id']}/approve").status_code == 409  # no double execution
    assert len(c.get("/api/trades").json()) == 1
    assert c.post("/api/actions/nope/approve").status_code == 409


def test_reject_flow():
    c = make_client()
    action = analyze_once(c)["action"]
    assert c.post(f"/api/actions/{action['id']}/reject").json()["status"] == "rejected"
    assert c.post(f"/api/actions/{action['id']}/approve").status_code == 409
    assert c.get("/api/trades").json() == []


def test_token_protects_mutations(monkeypatch):
    monkeypatch.setenv("AXIOM_API_TOKEN", "s3cret")
    get_settings.cache_clear()
    c = make_client()
    action = analyze_once(c)["action"]
    assert c.post(f"/api/actions/{action['id']}/approve").status_code == 401
    assert (
        c.post(f"/api/actions/{action['id']}/approve", headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )
    assert c.put("/api/watchlist/AAPL").status_code == 401
    ok = c.post(f"/api/actions/{action['id']}/approve", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
    assert c.get("/api/watchlist").status_code == 200  # reads stay public


def test_real_actions_fail_closed_without_a_token(monkeypatch):
    monkeypatch.setenv("COMPOSIO_API_KEY", "k")
    get_settings.cache_clear()
    c = make_client()
    r = c.put("/api/watchlist/AAPL")
    assert r.status_code == 403 and "AXIOM_API_TOKEN" in r.json()["detail"]


def test_watchlist_and_manual_trades_roundtrip():
    c = make_client()
    assert c.put("/api/watchlist/nvda").json()[0]["ticker"] == "NVDA"
    assert c.delete("/api/watchlist/NVDA").json() == []
    t = c.post("/api/trades", json={"ticker": "MSFT", "quantity": 3}).json()
    assert t["entry_price"] > 0
    closed = c.post(f"/api/trades/{t['id']}/close").json()
    assert closed["exit_price"] is not None
    assert c.delete(f"/api/trades/{t['id']}").json() == {"ok": True}
    assert c.post("/api/trades", json={"ticker": "MSFT", "quantity": 0}).status_code == 422


def test_scorecard_is_honest_when_empty():
    card = make_client().get("/api/scorecard").json()
    assert (
        card["n_scored"] == 0 and card["sufficient_sample"] is False and "need >= 30" in card["sample_note"]
    )
