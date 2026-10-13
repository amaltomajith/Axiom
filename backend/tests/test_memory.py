from datetime import date

import numpy as np
import pandas as pd
import pytest

from axiom.config import get_settings
from axiom.data import market
from axiom.memory import scorer
from axiom.memory.store import Store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_DB", str(tmp_path / "t.db"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "state.db")


def frame(prices: list[float], start="2025-01-01", lows: list[float] | None = None) -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(prices))
    p = np.array(prices, dtype=float)
    return pd.DataFrame(
        {"open": p, "high": p * 1.01, "low": np.array(lows) if lows else p * 0.99, "close": p, "volume": 1e6},
        index=idx,
    )


def patch_prices(monkeypatch, series: dict[str, pd.DataFrame]):
    async def fake(ticker, bars=504):
        return series[ticker].iloc[-bars:], "synthetic"

    monkeypatch.setattr(market, "fetch_ohlcv", fake)


def add(store, *, rating="BUY", conviction=0.6, horizon=5, price=100.0, issue="2025-01-06", stop=None, ticker="AAA",
        findings=None):  # fmt: skip
    return store.add_thesis(
        run_id="r1", ticker=ticker, issue_date=issue, horizon_days=horizon, price_at_issue=price, rating=rating,
        conviction=conviction, stop_price=stop, memo={"rating": rating},
        findings=findings or [{"agent": "Technical Analyst", "stance": "bullish"}],
    )  # fmt: skip


def test_store_roundtrips(store):
    store.save_run("r1", "AAA", {"memo": {"rating": "BUY", "conviction": 0.5}}, [{"type": "x"}])
    assert store.get_run("r1")["events"] == [{"type": "x"}]
    assert store.list_runs()[0]["rating"] == "BUY"
    store.watch_add("AAA")
    store.watch_add("AAA")
    assert [w["ticker"] for w in store.watchlist()] == ["AAA"]
    store.watch_remove("AAA")
    assert store.watchlist() == []
    tid = store.add_trade(
        {"ticker": "AAA", "side": "BUY", "quantity": 5, "entry_price": 10, "entry_date": "2025-01-02"}
    )
    store.close_trade(tid, 12.0, "2025-02-01")
    assert store.trades()[0]["exit_price"] == 12.0
    store.delete_trade(tid)
    assert store.trades() == []


def test_idempotency_key_is_claimed_once(store):
    assert store.claim_key("k1", "a1") is True
    assert store.claim_key("k1", "a2") is False
    store.release_key("k1")
    assert store.claim_key("k1", "a3") is True


async def test_correct_buy_beats_benchmark(store, monkeypatch):
    # issue 2025-01-06 is bar index 3 (Jan 1,2,3,6); horizon 5 bars later
    aaa = frame([98, 99, 99.5, 100, 101, 102, 103, 104, 108, 110, 111])
    spy = frame([500, 500, 500, 500, 501, 502, 503, 504, 505, 505, 506])
    patch_prices(monkeypatch, {"AAA": aaa, "SPY": spy})
    tid = add(store, issue=str(aaa.index[3].date()), price=100.0, stop=95.0)
    out = await scorer.score_thesis(store.theses()[0], today=date(2025, 3, 1))
    assert out["ret_pct"] == pytest.approx(8.0, abs=0.001)  # 100 -> 108 over 5 bars
    assert out["direction_hit"] == 1 and out["beat_benchmark"] == 1 and out["stop_hit"] == 0
    assert out["excess_ret_pct"] > 0 and 0 < out["brier"] < 0.25
    assert tid


async def test_sell_that_rises_is_wrong_and_stop_hit_detected(store, monkeypatch):
    aaa = frame(
        [100, 100, 100, 100, 99, 90, 98, 105, 106, 107, 108],
        lows=[99, 99, 99, 99, 98, 80, 97, 104, 105, 106, 107],
    )
    spy = frame([500] * 11)
    patch_prices(monkeypatch, {"AAA": aaa, "SPY": spy})
    add(store, rating="SELL", conviction=0.8, issue=str(aaa.index[3].date()), horizon=6)
    add(store, rating="BUY", conviction=0.8, issue=str(aaa.index[3].date()), horizon=6, stop=85.0)
    sell, buy = sorted(store.theses(), key=lambda t: t["rating"], reverse=True)  # SELL first
    s = await scorer.score_thesis(sell)
    assert s["direction_hit"] == 0 and s["brier"] > 0.25  # confidently wrong costs more than a coin flip
    b = await scorer.score_thesis(buy)
    assert b["stop_hit"] == 1  # low touched 80 during the window


async def test_hold_has_no_directional_score_and_not_due_returns_none(store, monkeypatch):
    aaa = frame([100] * 8)
    patch_prices(monkeypatch, {"AAA": aaa, "SPY": frame([500] * 8)})
    add(store, rating="HOLD", issue=str(aaa.index[0].date()), horizon=3)
    o = await scorer.score_thesis(store.theses()[0])
    assert o["direction_hit"] is None and o["brier"] is None and o["beat_benchmark"] is None
    add(store, rating="BUY", issue=str(aaa.index[6].date()), horizon=10)
    assert await scorer.score_thesis(store.theses()[0]) is None  # horizon not reached yet


async def test_agent_level_scoring(store, monkeypatch):
    aaa = frame([100, 100, 100, 100, 102, 103, 104, 105, 106, 107, 108])
    patch_prices(monkeypatch, {"AAA": aaa, "SPY": frame([500] * 11)})
    add(store, issue=str(aaa.index[3].date()), horizon=5, findings=[
        {"agent": "Technical Analyst", "stance": "bullish"},
        {"agent": "Fundamental Auditor", "stance": "bearish"},
        {"agent": "Other", "stance": "neutral"},
    ])  # fmt: skip
    o = await scorer.score_thesis(store.theses()[0])
    agents = o["detail"]["agents"]
    assert agents["Technical Analyst"]["hit"] == 1 and agents["Fundamental Auditor"]["hit"] == 0
    assert agents["Other"]["hit"] is None


async def test_score_due_and_scorecard_honesty_about_sample_size(store, monkeypatch):
    aaa = frame([100, 100, 100, 100, 102, 103, 104, 105, 106, 107, 108, 109, 110])
    patch_prices(monkeypatch, {"AAA": aaa, "SPY": frame([500] * 13)})
    for r in ("BUY", "BUY", "SELL", "HOLD"):
        add(store, rating=r, issue=str(aaa.index[3].date()), horizon=5)
    add(store, rating="BUY", issue=str(aaa.index[12].date()), horizon=5)  # not due
    res = await scorer.score_due(store, today=date(2025, 6, 1))
    assert res == {"scored": 4, "not_yet_due": 1, "failed": 0}
    card = scorer.scorecard(store)
    assert card["n_scored"] == 4 and card["n_pending"] == 1 and card["n_directional"] == 3
    assert card["direction_hit_rate"] == pytest.approx(2 / 3, abs=0.001)  # two BUYs right, SELL wrong
    assert card["sufficient_sample"] is False and "need >= 30" in card["sample_note"]
    assert card["baseline_up_rate"] == 1.0  # every scored thesis saw a rising price
    assert card["by_rating"]["HOLD"] == 1
    assert card["mean_excess_return_pct"] is not None


async def test_score_due_survives_data_errors(store, monkeypatch):
    async def boom(ticker, bars=504):
        raise market.DataError("down")

    monkeypatch.setattr(market, "fetch_ohlcv", boom)
    add(store)
    assert (await scorer.score_due(store, today=date(2026, 1, 1)))["failed"] == 1
    assert store.theses()[0]["status"] == "pending"  # untouched, retried next run


async def test_recall_text_reports_outcomes_and_pending(store, monkeypatch):
    aaa = frame([100, 100, 100, 100, 102, 103, 104, 105, 106, 107, 108])
    patch_prices(monkeypatch, {"AAA": aaa, "SPY": frame([500] * 11)})
    t_old = add(store, issue=str(aaa.index[3].date()), horizon=5)
    await scorer.score_due(store, today=date(2025, 6, 1))
    add(store, rating="SELL", issue=str(aaa.index[9].date()), horizon=20)
    text = scorer.recall(store, "AAA")
    assert "call was right" in text and "still pending" in text and "SELL" in text
    assert scorer.recall(store, "ZZZ") == "" and t_old
