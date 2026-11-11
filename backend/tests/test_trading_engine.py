"""Engine, tournament and Time Machine: no look-ahead (truncation invariance), determinism, the daily loss
limit, the kill switch, supervised approval, and the backtest report."""

import json

import numpy as np
import pandas as pd
import pytest

from axiom.trading.brain import Decision
from axiom.trading.broker.sim import SimBroker
from axiom.trading.engine import KILL_FILE
from axiom.trading.ledger import MemoryLedger
from axiom.trading.models import OrderRequest
from axiom.trading.replay import build_engine, run_replay
from axiom.trading.report import build_report, render_markdown
from axiom.trading.strategies import TRADING_STRATEGIES, SignalBook, bar_times
from axiom.trading.tournament import TournamentConfig, rank

from .conftest import make_ohlcv


def frames(n=700):
    return {
        "SPY": make_ohlcv(n, seed=3, drift=0.0005),
        "AAPL": make_ohlcv(n, seed=4, drift=0.0002, vol=0.02),
        "BTC/USD": make_ohlcv(n, seed=5, drift=0.001, vol=0.04),
    }


# ------------------------------------------------------------------ look-ahead
@pytest.mark.parametrize("name", list(TRADING_STRATEGIES))
def test_every_strategy_is_causal(name):
    df = make_ohlcv(400, seed=11, vol=0.025)
    full = TRADING_STRATEGIES[name](df).to_numpy()
    for t in (60, 150, 299, 398):
        cut = TRADING_STRATEGIES[name](df.iloc[: t + 1]).to_numpy()
        np.testing.assert_array_equal(cut, full[: t + 1], err_msg=f"{name} changed at bar <= {t}")


def test_tournament_ranking_ignores_future_bars():
    df = make_ohlcv(600, seed=8, vol=0.02)
    cfg = TournamentConfig()
    t = 400
    a = rank(SignalBook("SPY", df), t, 10.0, cfg).to_dict()
    b = rank(SignalBook("SPY", df.iloc[: t + 1]), t, 10.0, cfg).to_dict()
    assert a == b


async def test_engine_decisions_ignore_future_bars():
    full = frames()
    cut_ts = float(bar_times(full["SPY"].index)[560])
    cut = {k: v[bar_times(v.index) <= cut_ts] for k, v in full.items()}
    a = await run_replay(full, session="replay:t")
    b = await run_replay(cut, session="replay:t")
    ja = [(e.seq, e.kind, e.text, e.hash) for e in a.ledger.journal_all() if e.ts <= cut_ts]
    jb = [(e.seq, e.kind, e.text, e.hash) for e in b.ledger.journal_all() if e.ts <= cut_ts]
    assert ja == jb and len(ja) > 10
    ca = [c for c in a.ledger.equity_curve(10**6) if c["ts"] <= cut_ts]
    assert ca == b.ledger.equity_curve(10**6)


async def test_replay_is_deterministic():
    a = await run_replay(frames(), session="replay:d")
    b = await run_replay(frames(), session="replay:d")
    assert a.ledger.journal_all()[-1].hash == b.ledger.journal_all()[-1].hash


def test_bar_times_handle_daily_and_intraday():
    daily = pd.DatetimeIndex(["2026-01-02", "2026-01-05"])
    assert list(bar_times(daily)) == [1767398399.0, 1767657599.0]  # 23:59:59 UTC of each date
    hourly = pd.DatetimeIndex(["2026-01-02 10:00", "2026-01-02 11:00"])
    assert bar_times(hourly)[1] - bar_times(hourly)[0] == 3600


# --------------------------------------------------------------- engine levers
class AlwaysEnter:
    name = "test"

    async def decide(self, view):
        if view.position is not None:
            return Decision(symbol=view.symbol, ts=view.ts, action="hold")
        return Decision(symbol=view.symbol, ts=view.ts, action="enter_long", strategy="sma_cross",
                        reason="test entry", confidence=0.6)  # fmt: skip


def live_like(autonomy="AUTONOMOUS", kill_file=None):
    df = make_ohlcv(300, seed=2, vol=0.01)
    book = SignalBook("SPY", df)
    broker = SimBroker(100_000, fill="immediate", slippage_bps=0, fee_bps={"equity": 0, "crypto": 0})
    led = MemoryLedger("live-test")
    eng = build_engine(["SPY"], session="live-test", broker=broker, ledger=led, brain=AlwaysEnter(),
                       autonomy=autonomy, kill_file=kill_file)  # fmt: skip
    eng.set_books({"SPY": book})
    return eng, broker, led, book


async def _tick(eng, broker, book, i):
    ts = float(book.ts[i])
    broker.set_price("SPY", float(book.close[i]), ts)
    await eng.roll_day(ts)
    return await eng.step(ts, {"SPY": i})


async def test_daily_loss_limit_halts_flattens_blocks_and_resets_next_day():
    eng, broker, led, book = live_like()
    ts0 = float(book.ts[100]) - 7200  # mid-day, so the next ticks stay on the same UTC day
    broker.set_price("SPY", 100.0, ts0)
    await eng.roll_day(ts0)
    await broker.submit(
        OrderRequest(symbol="SPY", side="buy", qty=500)
    )  # 50% of equity, bypassing the kernel
    broker.set_price("SPY", 94.0, ts0 + 60)  # -6% on half the book = -3% on the day
    await eng.step(ts0 + 60, {})
    assert eng.st["halted"] and "daily loss limit" in eng.st["halted"]
    assert (await broker.account()).positions == {}
    kinds = [e.kind for e in led.journal_all()]
    assert "halt" in kinds
    await eng.step(ts0 + 120, {"SPY": 100})  # the brain wants in; the kernel says no
    blocked = [e for e in led.journal_all() if e.kind == "blocked"]
    assert blocked and blocked[-1].facts["blocked_by"] == "R3"
    await eng.roll_day(ts0 + 86_400)
    assert eng.st["halted"] is None and led.journal_all()[-1].kind == "resume"


async def test_kill_switch_flattens_and_blocks_until_resumed():
    eng, broker, led, book = live_like()
    await _tick(eng, broker, book, 100)
    assert "SPY" in (await broker.account()).positions
    await eng.kill("demo")
    assert (await broker.account()).positions == {} and eng.killed
    assert await _tick(eng, broker, book, 101) == []  # no decisions while killed
    await eng.resume("tester")
    await _tick(eng, broker, book, 105)
    assert "SPY" in (await broker.account()).positions


async def test_kill_file_is_honoured(tmp_path):
    kf = tmp_path / "KILL"
    eng, broker, led, book = live_like(kill_file=kf)
    await _tick(eng, broker, book, 100)
    kf.write_text("stop")
    await _tick(eng, broker, book, 101)
    assert (await broker.account()).positions == {}
    assert any(e.kind == "kill" for e in led.journal_all())
    assert KILL_FILE.name == "KILL"


async def test_supervised_entries_wait_for_a_human():
    eng, broker, led, book = live_like("SUPERVISED")
    await _tick(eng, broker, book, 100)
    assert (await broker.account()).positions == {}
    assert len(eng.st["pending"]) == 1 and led.journal_all()[-1].kind == "proposal"
    await _tick(eng, broker, book, 101)
    assert len(eng.st["pending"]) == 1  # not duplicated
    res = await eng.approve(eng.st["pending"][0]["id"], now=float(book.ts[101]))
    assert res["ok"] and "SPY" in (await broker.account()).positions
    assert eng.st["pending"] == []


async def test_shadow_mode_trades_nothing_but_logs_once():
    eng, broker, led, book = live_like("SHADOW")
    for i in range(100, 105):
        await _tick(eng, broker, book, i)
    assert (await broker.account()).positions == {}
    blocked = [e for e in led.journal_all() if e.kind == "blocked"]
    assert len(blocked) == 1 and blocked[0].facts["blocked_by"] == "R12"


async def test_engine_stop_exits_and_starts_cooldown():
    eng, broker, led, book = live_like()
    await _tick(eng, broker, book, 100)
    stop = eng.st["meta"]["SPY"]["stop"]
    ts = float(book.ts[101])
    broker.set_price("SPY", stop * 0.99, ts)
    book.close = book.close.copy()
    book.close[101] = stop * 0.99
    await eng.step(ts, {"SPY": 101})
    await eng.step(ts + 1, {})  # the fill is recorded on the next tick
    assert (await broker.account()).positions == {}
    assert eng.st["last_stopout"]["SPY"] >= ts
    assert any(e.kind == "stop" for e in led.journal_all())


# -------------------------------------------------------------------- report
async def test_report_compares_agent_benchmark_and_fixed_strategies():
    res = await run_replay(frames())
    rep = build_report(res)
    assert rep["verdict"]["verdict"] in ("edge_detected", "unproven", "no_edge", "insufficient_data")
    assert set(rep["fixed_strategies"]) == set(TRADING_STRATEGIES)
    assert rep["curve"] and rep["trades"]["entries"] > 0
    assert rep["agent"]["max_drawdown"] <= 0 and 0 <= rep["agent"]["exposure"] <= 1
    md = render_markdown(rep)
    for heading in ("## Agent vs buy-and-hold", "## Against each fixed strategy", "## Trades",
                    "## Risk events", "## Method and caveats"):  # fmt: skip
        assert heading in md
    assert "LLM brain is deliberately excluded" in md
    assert "—" not in md and "–" not in md
    json.dumps(rep)


def test_cli_backtest_writes_markdown_and_json(tmp_path, monkeypatch):
    import sys

    from axiom.trading import __main__ as cli
    from axiom.trading import data

    async def fake_fetch(syms, bars):
        f = frames()
        return {s.name: f[s.name] for s in syms}

    monkeypatch.setattr(data, "fetch_daily", fake_fetch)
    out = tmp_path / "r.md"
    monkeypatch.setattr(sys, "argv", ["x", "backtest", "--symbols", "SPY,BTC/USD", "--out", str(out)])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0
    assert out.read_text(encoding="utf-8").startswith("# Axiom Autopilot backtest")
    assert json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))["universe"] == ["SPY", "BTC/USD"]


async def test_regimes_survive_a_restart_until_the_next_strategy_check():
    eng, broker, led, book = live_like()
    await _tick(eng, broker, book, 280)
    seen = eng.regimes()
    assert seen["SPY"] and "trend" in seen["SPY"]
    again = build_engine(["SPY"], session="live-test", broker=broker, ledger=led, brain=AlwaysEnter())
    assert again.rankings == {} and again.regimes() == seen
