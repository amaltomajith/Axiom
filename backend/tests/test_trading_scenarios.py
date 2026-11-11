"""The three demo scenarios: real-history windows, cut and checked. Synthetic frames here, no network."""

import time
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from axiom.api.app import create_app
from axiom.config import get_settings
from axiom.memory import store as store_mod
from axiom.trading import scenarios as sc

from .conftest import make_ohlcv

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def daily(end="2026-11-11", n=1500, seed=3):
    df = make_ohlcv(n, seed=seed, drift=0.0006, vol=0.02)
    df.index = pd.date_range(end=end, periods=n, freq="D")
    return df


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("AXIOM_API_TOKEN", TOKEN)
    for k, v in {"TRADER_BROKER": "sim", "TRADER_BRAIN": "rule", "TRADER_SYMBOLS": "BTC/USD",
                 "TRADER_ENABLED": "false"}.items():  # fmt: skip
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    store_mod._store = None
    yield
    get_settings.cache_clear()
    store_mod._store = None


def test_there_are_exactly_the_three_scenarios_the_deck_names():
    assert list(sc.SCENARIOS) == ["breakout", "flash_crash", "trojan_headline"]
    for s in sc.SCENARIOS.values():
        assert s.start < s.end and s.symbols and s.expect_text
        assert s.inject_on is None or s.start < s.inject_on < s.end
    with pytest.raises(ValueError, match="unknown scenario"):
        sc.get("moon")


def test_a_window_is_cut_from_real_history_never_generated():
    s = sc.SCENARIOS["breakout"]
    df = daily()
    out = sc.slice_frames({"BTC/USD": df}, s)["BTC/USD"]
    assert out.index[sc.WARMUP] == pd.Timestamp(s.start) and out.index[-1] == pd.Timestamp(s.end)
    assert len(out) == sc.WARMUP + (pd.Timestamp(s.end) - pd.Timestamp(s.start)).days + 1
    pd.testing.assert_frame_equal(out, df.loc[out.index[0] : out.index[-1]])  # the same rows, untouched
    with pytest.raises(ValueError, match="does not reach back far enough"):
        sc.slice_frames({"BTC/USD": df.loc["2023-12-01":]}, s)
    with pytest.raises(ValueError, match="no history"):
        sc.slice_frames({}, s)


def _entry(kind, text="", facts=None):
    return SimpleNamespace(kind=kind, text=text, facts=facts or {})


def _contract(outcome, ret, shadow=False, status="graded"):
    return {"status": status, "shadow": shadow, "symbol": "BTC/USD", "strategy": "donchian_breakout",
            "result": {"outcome": outcome, "return_pct": ret, "grade": "A" if outcome else "D"}}  # fmt: skip


def test_outcomes_are_read_from_the_journal_not_assumed():
    b, f, t = (sc.SCENARIOS[k] for k in ("breakout", "flash_crash", "trojan_headline"))
    won = sc.outcome(b, [_entry("entry"), _entry("exit")], [_contract(1, 39.67), _contract(1, 2.0)])
    assert won == {"ok": True, "detail": "BTC/USD donchian_breakout closed +39.67%, grade A."}
    assert not sc.outcome(b, [_entry("entry"), _entry("exit")], [_contract(0, -3.0)])["ok"]
    assert not sc.outcome(b, [_entry("entry"), _entry("exit")], [_contract(1, 5.0, shadow=True)])["ok"]

    halt = _entry("halt", "Daily loss limit hit: equity is -2.87% on the day against a limit of -2.50%.")
    assert sc.outcome(f, [halt], []) == {"ok": True, "detail": halt.text}
    assert not sc.outcome(f, [_entry("halt", "Watchdog tripped: 3 failed ticks.")], [])["ok"]

    flag = _entry("flag", "Red team: a headline...", {"source": "redteam"})
    block = _entry("blocked", "Red team: asked to buy 1,000,000 BTC/USD at once.", {"source": "redteam"})
    assert sc.outcome(t, [flag, block], []) == {"ok": True, "detail": block.text}
    assert not sc.outcome(t, [flag], [])["ok"] and not sc.outcome(t, [block], [])["ok"]


def _run(c, scenario):
    job = c.post("/api/trader/replay", headers=AUTH, json={"scenario": scenario}).json()
    for _ in range(600):
        d = c.get(f"/api/trader/replays/{job['id']}").json()
        if d["status"] not in ("queued", "fetching", "running"):
            break
        time.sleep(0.05)
    return job, d


def test_the_trojan_headline_replay_flags_the_headline_and_blocks_its_order():
    app = create_app()
    svc = app.state.trader
    asked = {}

    async def frames(symbols, bars):
        asked.update(symbols=[s.name for s in symbols], bars=bars)
        return {s.name: daily(seed=i + 3) for i, s in enumerate(symbols)}

    svc.fetch_frames = frames
    with TestClient(app) as c:
        listed = c.get("/api/trader/scenarios").json()
        assert [s["id"] for s in listed] == ["breakout", "flash_crash", "trojan_headline"]
        assert c.post("/api/trader/replay", headers=AUTH, json={"scenario": "moon"}).status_code == 422

        job, d = _run(c, "trojan_headline")
        assert d["status"] == "done", d
        assert asked == {"symbols": ["BTC/USD"], "bars": 1500}  # the scenario fixes its own symbols
        assert d["scenario"] == "trojan_headline" and d["outcome"]["ok"], d["outcome"]
        j = c.get(f"/api/trader/journal?session={job['session']}&limit=2000").json()
        red = [e for e in j if (e.get("facts") or {}).get("source") == "redteam"]
        assert sorted(e["kind"] for e in red) == ["blocked", "flag"]  # once, on its day
        inject = sc.day_ts(sc.SCENARIOS["trojan_headline"].inject_on)
        assert all(inject <= e["ts"] < inject + 86_400 for e in red)
        first, last = j[0]["ts"], j[-1]["ts"]
        assert first >= sc.day_ts("2024-01-25") and last < sc.day_ts("2024-03-11") + 86_400
        assert c.get(f"/api/trader/journal/verify?session={job['session']}").json()["ok"]
        eq = c.get(f"/api/trader/equity?session={job['session']}").json()
        assert 40 <= len(eq) <= 50 and np.isfinite([p["equity"] for p in eq]).all()


def test_a_scenario_without_enough_history_fails_with_a_reason():
    app = create_app()

    async def frames(symbols, bars):
        return {s.name: daily(n=200) for s in symbols}

    app.state.trader.fetch_frames = frames
    with TestClient(app) as c:
        _, d = _run(c, "breakout")
        assert d["status"] == "error" and "does not reach back far enough" in d["error"]
