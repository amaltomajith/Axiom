"""The trading desk: four agents review a candidate entry. No network: a fake analyzer and SimBroker."""

import asyncio
from contextlib import asynccontextmanager

import pytest

from axiom.agents.orchestrator import AnalysisResult
from axiom.agents.schemas import Claim, Finding, Memo, PositionPlan
from axiom.trading.brain import MarketView, RuleBrain
from axiom.trading.broker.sim import SimBroker
from axiom.trading.desk import DeskBrain, DeskTracer
from axiom.trading.engine import _scaled
from axiom.trading.ledger import MemoryLedger
from axiom.trading.replay import build_engine
from axiom.trading.strategies import SignalBook
from axiom.trading.tournament import Ranking, Standing

from .conftest import make_ohlcv


def ranking():
    st = [
        Standing("sma_cross", 1.4, 0.22, -0.08, 6, True, "qualified"),
        Standing("macd_trend", 0.9, 0.12, -0.10, 9, True, "qualified"),
    ]
    return Ranking("BTC/USD", 300, 1.7e9, 0.7, 0.10, {"trend": "uptrend", "volatility": "normal"}, st)


def view(signals=None, position=None):
    sig = signals or {"sma_cross": 1.0, "macd_trend": 1.0}
    return MarketView(symbol="BTC/USD", kind="crypto", ts=1.7e9, price=60_000.0, atr=1_200.0, ranking=ranking(),
                      signals_now=sig, signals_prev=sig, position=position)  # fmt: skip


def result(rating="BUY", conviction=0.7, critic=(True, []), stances=("bullish", "neutral")):
    claim = Claim(text="A backtest found an edge on the trailing window.", evidence=["T1"])
    memo = Memo(rating=rating, conviction=conviction, thesis="Trend and backtest agree on the long side.",
                bull_case=[claim], bear_case=[claim], key_risks=["Volatility can rise."])  # fmt: skip
    findings = [
        Finding(agent=a, stance=s, confidence=0.6, summary="A short summary.", claims=[claim])
        for a, s in zip(("Technical Analyst", "Fundamental Auditor"), stances, strict=True)
    ]
    events = []
    if critic is not None:
        events.append(
            {"type": "critique", "agent": "Risk Critic", "data": {"ok": critic[0], "issues": critic[1]}}
        )
    return AnalysisResult("run123", "BTC-USD", memo, "# memo", findings, PositionPlan(action="none"),
                          {"T1": {"id": "T1", "tool": "run_backtest", "args": {}, "text": "{}"}}, [], [], {},
                          events)  # fmt: skip


@asynccontextmanager
async def no_box():
    yield object()


def desk(res=None, *, fail=None, delay=0.0, **kw):
    calls = []

    async def analyzer(ticker, *, llm, box, equity, tracer, memory_context):
        calls.append({"ticker": ticker, "memory": memory_context})
        tracer.emit("run_start", "system", ticker=ticker)
        tracer.emit("final", "Lead Synthesizer", rating="BUY", markdown="x" * 5000)
        if delay:
            await asyncio.sleep(delay)
        if fail:
            raise fail
        return res or result()

    kw.setdefault("wait", 1.0)
    b = DeskBrain(RuleBrain(), llm_factory=lambda: None, box_factory=no_box, analyzer=analyzer, **kw)
    b.calls = calls
    return b


# ------------------------------------------------------------------ mapping
async def test_a_buy_with_a_content_critic_enters_at_full_size_and_records_the_review():
    b = desk()
    d = await b.decide(view())
    assert d.action == "enter_long" and d.source == "desk" and not d.degraded and not d.veto
    assert d.strategy == "sma_cross" and d.size_factor == 1.0 and d.confidence == 0.7
    assert d.desk["rating"] == "BUY" and d.desk["evidence"] == ["T1"] and d.desk["run_id"] == "run123"
    assert d.desk["stances"] == {"Technical Analyst": "bullish", "Fundamental Auditor": "neutral"}
    assert b.calls == [{"ticker": "BTC-USD", "memory": ""}]  # the agents get the Yahoo spelling


@pytest.mark.parametrize(
    "res, why",
    [
        (result(critic=(False, ["The stop is inside normal noise."])), "Risk Critic raised issues"),
        (result(conviction=0.4), "conviction ended below"),
    ],
)
async def test_the_desk_can_only_ask_for_less(res, why):
    d = await desk(res).decide(view())
    assert d.action == "enter_long" and d.size_factor == 0.5 and why in d.reason


@pytest.mark.parametrize("rating", ["HOLD", "SELL", "STRONG_SELL"])
async def test_a_rating_that_is_not_bullish_vetoes_the_entry(rating):
    d = await desk(result(rating=rating)).decide(view())
    assert d.action == "stay_flat" and d.veto and d.source == "desk" and rating in d.reason
    assert d.desk["rating"] == rating


async def test_hold_can_be_configured_to_take_half_size_instead():
    d = await desk(result(rating="HOLD"), hold_policy="half").decide(view())
    assert d.action == "enter_long" and d.size_factor == 0.5


@pytest.mark.parametrize(
    "kw, why",
    [
        ({"fail": RuntimeError("429 from every provider")}, "the review failed (RuntimeError)"),
        ({"res": result(rating="NO_CALL", conviction=0.0)}, "NO_CALL"),
        ({"delay": 5.0, "timeout": 0.05}, "timed out"),
        ({"max_runs_per_hour": 0}, "hourly cap"),
    ],
)
async def test_when_the_desk_has_no_view_the_wrapped_brain_decides_marked_degraded(kw, why):
    d = await desk(**kw).decide(view())
    assert d.action == "enter_long" and d.source == "rule" and d.degraded and why in d.reason
    assert d.size_factor is None  # no view means no size request either


async def test_the_desk_is_not_consulted_when_there_is_no_candidate_entry():
    b = desk()
    d = await b.decide(view(signals={"sma_cross": 0.0, "macd_trend": 1.0}))
    assert d.action == "stay_flat" and d.source == "rule" and b.calls == []


async def test_a_slow_review_answers_reviewing_then_is_reused_without_a_second_run():
    b = desk(delay=0.15, wait=0.01)
    first = await b.decide(view())
    assert first.action == "stay_flat" and first.reviewing and not first.veto
    await asyncio.sleep(0.3)
    second = await b.decide(view())
    assert second.action == "enter_long" and second.source == "desk"
    assert len(b.calls) == 1 and b.runs_left() == b.max_runs_per_hour - 1


async def test_reviews_are_capped_per_hour_and_expire_after_their_ttl():
    now = [1000.0]
    b = desk(max_runs_per_hour=1, ttl=600.0, clock=lambda: now[0])
    assert (await b.decide(view())).source == "desk"
    now[0] += 300
    assert (await b.decide(view())).source == "desk" and len(b.calls) == 1  # cached
    now[0] += 400  # past the ttl, but the hourly cap is spent
    d = await b.decide(view())
    assert d.degraded and "hourly cap" in d.reason and len(b.calls) == 1
    now[0] += 3600
    assert (await b.decide(view())).source == "desk" and len(b.calls) == 2


async def test_agent_steps_are_streamed_to_listeners_without_the_memo_markdown():
    b = desk()
    seen = []
    b.listeners.append(seen.append)
    b.listeners.append(lambda ev: 1 / 0)  # a broken listener must not break the review
    d = await b.decide(view())
    assert d.source == "desk"
    assert [e["type"] for e in seen] == ["desk", "desk", "desk_done"]
    assert seen[1]["kind"] == "final" and "markdown" not in seen[1]["data"] and seen[1]["symbol"] == "BTC/USD"
    assert seen[2]["review"]["rating"] == "BUY"
    st = b.status()
    assert st["runs"]["BTC/USD"]["review"]["rating"] == "BUY" and len(st["runs"]["BTC/USD"]["events"]) == 2


def test_desk_tracer_keeps_the_ordinary_tracer_behaviour():
    got = []
    t = DeskTracer(on_event=got.append)
    ev = t.emit("finding", "Technical Analyst", stance="bullish")
    assert t.events == [ev] and got == [ev] and ev.seq == 1


# ------------------------------------------------------------------- engine
def test_scaled_sizes_round_down_and_never_reach_zero():
    assert _scaled(0.333333, 0.5, "crypto") == 0.166666
    assert _scaled(7, 0.5, "equity") == 3.0 and _scaled(1, 0.5, "equity") == 1.0


async def _engine_with(brain, autonomy="AUTONOMOUS"):
    df = make_ohlcv(400, seed=3, drift=0.002)
    broker = SimBroker(100_000.0, fill="immediate")
    eng = build_engine(["BTC/USD"], session="t", broker=broker, ledger=MemoryLedger("t"), brain=brain,
                       autonomy=autonomy, bar_seconds=86_400)  # fmt: skip
    book = SignalBook("BTC/USD", df)
    eng.set_books({"BTC/USD": book})
    return eng, broker, book


async def _first(eng, broker, book, kinds=("entry",)):
    """Step bar by bar until the journal shows one of `kinds`; return that entry."""
    for i in range(eng.cfg.tournament.window - 1, len(book)):
        ts = float(book.ts[i])
        broker.set_price("BTC/USD", float(book.close[i]), ts)
        await eng.step(ts, {"BTC/USD": i})
        hit = [j.model_dump() for j in eng.ledger.journal(500) if j.kind in kinds]
        if hit:
            return hit[-1]
    return None


async def test_engine_buys_half_the_kernel_size_when_the_critic_objects():
    full_eng, fb, fbook = await _engine_with(RuleBrain())
    full = await _first(full_eng, fb, fbook)
    assert full is not None, "the fixture must produce a rule entry"

    b = desk(result(critic=(False, ["Momentum is stretched."])), clock=lambda: 0.0, ttl=1e12)
    eng, broker, book = await _engine_with(b)
    e = await _first(eng, broker, book)
    assert e is not None and e["facts"]["source"] == "desk" and e["facts"]["size_factor"] == 0.5
    assert e["facts"]["qty"] == pytest.approx(full["facts"]["qty"] / 2, rel=1e-3)
    assert e["facts"]["desk"]["critic_issues"] == ["Momentum is stretched."]
    assert "trading desk" in e["text"] and "half the size" in e["text"]
    assert all(c["ok"] for c in e["facts"]["checks"])


async def test_engine_journals_a_desk_veto_and_places_no_order():
    b = desk(result(rating="SELL"), clock=lambda: 0.0, ttl=1e12)
    eng, broker, book = await _engine_with(b)
    v = await _first(eng, broker, book, kinds=("veto", "entry"))
    assert v is not None and v["kind"] == "veto" and v["facts"]["desk"]["rating"] == "SELL"
    assert "Did not buy BTC/USD" in v["text"] and not (await broker.account()).positions


async def test_supervised_proposal_carries_the_desk_review_and_the_smaller_size():
    b = desk(result(conviction=0.3), clock=lambda: 0.0, ttl=1e12)
    eng, broker, book = await _engine_with(b, autonomy="SUPERVISED")
    p = await _first(eng, broker, book, kinds=("proposal",))
    assert p is not None and p["facts"]["size_factor"] == 0.5 and "trading desk rated it BUY" in p["text"]
    item = eng.st["pending"][0]
    assert item["intent"]["requested_qty"] == item["verdict"]["qty"]
    out = await eng.approve(item["id"], now=item["created_at"])
    assert out["ok"] and out["order"]["qty"] == pytest.approx(item["verdict"]["qty"], rel=0.05)
