"""The five trading MCP tools, called over a real in-memory MCP session against a SimBroker. No network."""

import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from axiom.agents import prompts
from axiom.mcp_server.server import mcp
from axiom.trading import service as service_mod
from axiom.trading.brain import Decision, RuleBrain
from axiom.trading.broker.sim import SimBroker
from axiom.trading.contracts import ContractBook, outcomes_by_regime, outcomes_text
from axiom.trading.ledger import MemoryLedger
from axiom.trading.live import Trader
from axiom.trading.mcp_tools import TRADING_TOOLS
from axiom.trading.replay import build_engine
from axiom.trading.service import TraderService
from axiom.trading.strategies import SignalBook
from axiom.trading.symbols import parse

from .conftest import make_ohlcv

SYM = "BTC/USD"
DF = make_ohlcv(400, seed=3, drift=0.002)


class FlatBrain:
    """Never enters on its own, so every entry in these tests comes from an MCP tool."""

    name = "flat"

    async def decide(self, view):
        return Decision(symbol=view.symbol, ts=view.ts, action="hold" if view.position else "stay_flat")


def _engine(brain, df, autonomy):
    broker = SimBroker(100_000.0, fill="immediate")
    eng = build_engine([SYM], session="live", broker=broker, ledger=MemoryLedger("live"), brain=brain,
                       autonomy=autonomy, bar_seconds=86_400, contracts=ContractBook())  # fmt: skip
    eng.set_books({SYM: SignalBook(SYM, df)})
    return eng, broker


async def _entry_bar() -> int:
    """The first bar where the rule brain would enter: a strategy is qualified and signalling there."""
    eng, broker = _engine(RuleBrain(), DF, "AUTONOMOUS")
    book = eng.books[SYM]
    for i in range(eng.cfg.tournament.window - 1, len(book)):
        broker.set_price(SYM, float(book.close[i]), float(book.ts[i]))
        await eng.step(float(book.ts[i]), {SYM: i})
        if (await broker.account()).positions:
            return i
    raise AssertionError("the fixture must produce a rule entry")


@pytest.fixture
async def desk(monkeypatch):
    """A service whose engine sits on the entry bar, flat, with the tournament already run."""
    i = await _entry_bar()

    async def make(autonomy="AUTONOMOUS"):
        eng, broker = _engine(FlatBrain(), DF.iloc[: i + 1], autonomy)
        now = float(eng.books[SYM].ts[-1])
        broker.set_price(SYM, float(eng.books[SYM].close[-1]), now)
        await eng.step(now, {SYM: i})
        monkeypatch.setattr("axiom.trading.engine.time.time", lambda: now)

        async def fetch(_sym):
            return DF.iloc[: i + 1]

        trader = Trader(eng, broker, [parse(SYM)], fetch, timeframe="1Day", interval=60)
        svc = TraderService(lambda: None, trader_factory=lambda _store: trader)
        service_mod.set_current(svc)
        return svc, eng, broker

    yield make
    service_mod.set_current(None)


async def call(name, **args):
    async with connect(mcp._mcp_server) as client:
        res = await client.call_tool(name, args)
    return json.loads(res.content[0].text)


def kinds(eng):
    return [j.kind for j in eng.ledger.journal(500)]


# ------------------------------------------------------------------- shape
async def test_the_server_registers_sixteen_tools_and_no_order_tool_takes_a_size():
    async with connect(mcp._mcp_server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert len(tools) == 16 and set(TRADING_TOOLS) <= set(tools)
    props = set(tools["place_paper_bracket_order"].inputSchema["properties"])
    assert props == {"symbol", "reason", "strategy", "size_fraction"}  # no qty, no price, no stop
    assert tools["place_paper_bracket_order"].inputSchema["properties"]["size_fraction"]["maximum"] == 1


def test_no_research_agent_may_call_a_trading_tool():
    allowed = set(prompts.TECH_TOOLS) | set(prompts.FUND_TOOLS) | set(prompts.RISK_TOOLS)
    assert not allowed & set(TRADING_TOOLS)


# ------------------------------------------------------------------ entries
async def test_an_order_is_sized_by_the_kernel_and_carries_a_stop(desk):
    svc, eng, broker = await desk()
    out = await call("place_paper_bracket_order", symbol="BTC-USD", reason="Trend and tournament agree.")
    assert out["ok"] and out["status"] == "submitted" and out["paper"] is True
    pos = (await broker.account()).positions[SYM]
    assert pos.qty == pytest.approx(out["qty"]) and pos.stop_price == out["stop_price"] < out["price"]
    assert out["risk_amount"] <= 0.0101 * 100_000 and all(c["ok"] for c in out["checks"])
    assert "entry" in kinds(eng)


async def test_a_caller_can_ask_for_less_but_never_for_more(desk):
    _, _, broker = await desk()
    full = await call("place_paper_bracket_order", symbol=SYM, reason="Full size.")
    _, _, broker2 = await desk()
    half = await call("place_paper_bracket_order", symbol=SYM, reason="Half size.", size_fraction=0.5)
    assert half["ok"] and half["qty"] == pytest.approx(full["qty"] / 2, rel=1e-3)
    async with connect(mcp._mcp_server) as client:
        res = await client.call_tool(
            "place_paper_bracket_order", {"symbol": SYM, "reason": "All in.", "size_fraction": 50}
        )
    assert res.isError  # the schema itself refuses a fraction above 1


async def test_supervised_mode_queues_the_order_for_a_human(desk):
    svc, eng, broker = await desk("SUPERVISED")
    out = await call("place_paper_bracket_order", symbol=SYM, reason="Needs a human.")
    assert out["ok"] and out["status"] == "pending_approval" and out["pending_id"]
    assert not (await broker.account()).positions and len(eng.st["pending"]) == 1
    again = await call("place_paper_bracket_order", symbol=SYM, reason="Twice.")
    assert not again["ok"] and "already waiting" in again["error"]
    assert (await svc.approve(out["pending_id"]))["ok"] and (await broker.account()).positions


async def test_shadow_mode_and_an_unqualified_strategy_are_refused(desk):
    _, eng, broker = await desk("SHADOW")
    out = await call("place_paper_bracket_order", symbol=SYM, reason="Shadow may not trade.")
    assert not out["ok"] and out["status"] == "blocked" and out["blocked_by"] == "R12"
    await desk()
    bad = await call("place_paper_bracket_order", symbol=SYM, reason="x", strategy="martingale")
    assert not bad["ok"] and "not both qualified and signalling" in bad["error"]
    unknown = await call("place_paper_bracket_order", symbol="DOGE/USD", reason="Not watched.")
    assert not unknown["ok"] and "no market data" in unknown["error"]
    assert not (await broker.account()).positions


# ------------------------------------------------------- stops, exits, kill
async def test_a_stop_can_be_raised_but_never_lowered(desk):
    _, eng, broker = await desk()
    o = await call("place_paper_bracket_order", symbol=SYM, reason="Entry.")
    lower = await call("modify_stop_loss", symbol=SYM, stop_price=o["stop_price"] * 0.9)
    assert not lower["ok"] and "only be tightened" in lower["error"]
    above = await call("modify_stop_loss", symbol=SYM, stop_price=o["price"] * 1.5)
    assert not above["ok"] and "below the price" in above["error"]
    new = round((o["stop_price"] + o["price"]) / 2, 2)
    ok = await call("modify_stop_loss", symbol=SYM, stop_price=new)
    assert ok["ok"] and (await broker.account()).positions[SYM].stop_price == new
    assert "Stops only ever move up" in eng.ledger.journal(500)[-1].text
    none = await call("modify_stop_loss", symbol="ETH/USD", stop_price=10.0)
    assert not none["ok"] and "no open" in none["error"]


async def test_closing_a_position_grades_its_contract_and_feeds_the_outcome_memory(desk):
    _, eng, broker = await desk()
    await call("place_paper_bracket_order", symbol=SYM, reason="Entry.")
    out = await call("close_paper_position", symbol=SYM, reason="Taking it off before the weekend.")
    assert out["ok"] and not (await broker.account()).positions and "exit" in kinds(eng)
    mem = await call("get_past_trade_outcomes")
    assert mem["ok"] and mem["graded_trades"] == 1 and mem["groups"][0]["trades"] == 1
    assert (await call("close_paper_position", symbol=SYM, reason="Again."))["ok"] is False


async def test_emergency_flatten_engages_the_kill_switch_and_blocks_new_entries(desk):
    _, eng, broker = await desk()
    await call("place_paper_bracket_order", symbol=SYM, reason="Entry.")
    out = await call("emergency_flatten_all", reason="Something looks wrong.")
    assert out["ok"] and out["closed"] == 1 and out["killed"] and eng.killed
    assert not (await broker.account()).positions
    after = await call("place_paper_bracket_order", symbol=SYM, reason="Try again.")
    assert not after["ok"] and after["blocked_by"] == "R0"


# ------------------------------------------------------------ outcome memory
def test_outcomes_group_graded_contracts_by_regime_and_strategy():
    def c(regime, strategy, outcome, ret, reason="signal", status="graded", shadow=False):
        return {"status": status, "regime_at_entry": regime, "strategy": strategy, "shadow": shadow,
                "result": {"outcome": outcome, "return_pct": ret, "reason": reason, "ts": 1.0}}  # fmt: skip

    rows = outcomes_by_regime([
        c("uptrend", "sma_cross", 1, 4.0),
        c("uptrend", "sma_cross", 0, -2.0, reason="stop-loss at 90 hit"),
        c("uptrend", "sma_cross", 0, -1.0, reason="stop-loss at 91 hit", shadow=True),
        c("sideways", "rsi_reversion", 1, 1.5),
        {"status": "open", "regime_at_entry": "uptrend", "strategy": "sma_cross", "result": None},
    ])  # fmt: skip
    assert rows[0] == {"regime": "uptrend", "strategy": "sma_cross", "trades": 3, "wins": 1, "win_rate": 0.333,
                       "avg_return_pct": 0.33, "stop_outs": 2, "shadow": 1, "last_ts": 1.0}  # fmt: skip
    assert rows[1]["regime"] == "sideways" and rows[1]["win_rate"] == 1.0
    text = outcomes_text([c("uptrend", "sma_cross", 0, -2.0, reason="stop-loss hit")])
    assert text == (
        "- sma_cross (market regime at entry: uptrend): 1 graded paper trade(s), 0 profitable, average result -2.00%, "
        "1 ended at the stop-loss."
    )
    assert outcomes_text([]) == ""
