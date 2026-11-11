"""Risk Kernel: one test per rule, exits always allowed, and a randomized property test against SimBroker."""

import random

import pytest

from axiom.trading.broker.sim import SimBroker
from axiom.trading.journal import verify_chain
from axiom.trading.ledger import MemoryLedger, StoreLedger
from axiom.trading.models import AccountState, Bar, Order, OrderIntent, OrderRequest, Position
from axiom.trading.risk import RiskContext, RiskKernel, RiskLimits, daily_loss_breached
from axiom.trading.symbols import parse, parse_list

LIMITS = RiskLimits(allowlist=frozenset({"SPY", "BTC/USD", "AAPL"}))


def acct(equity=100_000.0, cash=None, positions=None, is_paper=True):
    return AccountState(equity=equity, cash=equity if cash is None else cash, positions=positions or {},
                        is_paper=is_paper)  # fmt: skip


def ctx(**kw):
    base = dict(now=1_000_000.0, price=100.0, kind="equity", day_start_equity=100_000.0)
    return RiskContext(**{**base, **kw})


def entry(symbol="SPY", stop=96.0, **kw):
    return OrderIntent(symbol=symbol, action="enter_long", stop_price=stop, reason="test", **kw)


def review(intent=None, account=None, c=None, limits=LIMITS):
    return RiskKernel(limits).review(intent or entry(), account or acct(), c or ctx())


def test_clean_entry_is_sized_at_one_percent_risk():
    v = review()
    assert v.approved and v.blocked_by is None
    # 1% of 100k = 1000 risk / 4 per share = 250 shares, but 20% cap = 200 shares
    assert v.qty == 200 and v.notional == 20_000
    assert {c.rule for c in v.checks} == {f"R{i}" for i in range(13)}


def test_crypto_is_sized_fractionally():
    v = review(entry("BTC/USD", stop=58_800.0), c=ctx(price=60_000.0, kind="crypto"))
    assert v.approved
    assert v.qty == pytest.approx(0.333333, abs=1e-6)  # 20% cap: 20k / 60k
    assert v.notional <= 20_000


@pytest.mark.parametrize(
    "rule,kwargs",
    [
        ("R0", {"c": ctx(killed=True)}),
        ("R1", {"c": ctx(broker_is_paper=False)}),
        ("R1", {"account": acct(is_paper=False)}),
        ("R2", {"intent": entry("TSLA")}),
        ("R3", {"account": acct(equity=97_400.0)}),
        ("R3", {"c": ctx(halted="daily loss limit")}),
        ("R4", {"c": ctx(data_age_seconds=10 * 86_400)}),
        ("R5", {"intent": entry(stop=None)}),
        ("R5", {"intent": entry(stop=101.0)}),
        ("R5", {"intent": entry(stop=99.95)}),  # 0.05%, inside the noise floor
        ("R5", {"intent": entry(stop=50.0)}),  # 50%, wider than 15%
        ("R6", {"intent": entry(requested_qty=10_000)}),
        ("R8", {"account": acct(cash=5.0)}),
        ("R9", {"limits": RiskLimits(allowlist=LIMITS.allowlist, max_open_positions=0)}),
        ("R10", {"c": ctx(trades_today=10)}),
        ("R11", {"c": ctx(last_stopout=1_000_000.0 - 86_400)}),
        ("R12", {"c": ctx(autonomy="SHADOW")}),
    ],
)  # fmt: skip
def test_each_rule_blocks(rule, kwargs):
    v = review(**kwargs)
    assert not v.approved
    assert v.blocked_by == rule, v.reason
    assert v.qty == 0


def test_r7_position_cap_is_enforced_even_when_risk_allows_more():
    tight = RiskLimits(allowlist=LIMITS.allowlist, max_position_pct=0.05)
    v = review(limits=tight)
    assert v.approved and v.notional <= 5_000 + 1e-6


def test_r8_gross_exposure_shrinks_the_order_to_the_room_left():
    held = {"AAPL": Position(symbol="AAPL", qty=900, avg_entry=100, market_price=100)}  # 90k exposure
    v = review(account=acct(equity=100_000, cash=10_000, positions=held))
    assert v.approved and v.notional <= 10_000 * 0.995 + 1e-6


def test_no_adding_to_an_open_position():
    held = {"SPY": Position(symbol="SPY", qty=10, avg_entry=100, market_price=100)}
    v = review(account=acct(positions=held))
    assert v.blocked_by == "R9" and "Already holding" in v.reason


def test_supervised_needs_approval_but_a_human_does_not():
    assert review(c=ctx(autonomy="SUPERVISED")).needs_approval
    assert not review(entry(source="human"), c=ctx(autonomy="SUPERVISED")).needs_approval
    assert review(entry(source="human"), c=ctx(autonomy="SHADOW")).approved  # a human may trade in shadow


def test_smaller_request_is_honoured():
    v = review(entry(requested_qty=5))
    assert v.approved and v.qty == 5


def test_exit_is_allowed_while_killed_and_halted():
    held = {"SPY": Position(symbol="SPY", qty=10, avg_entry=100, market_price=90)}
    v = RiskKernel(LIMITS).review(
        OrderIntent(symbol="SPY", action="exit", reason="stop"),
        acct(equity=90_000, positions=held),
        ctx(killed=True, halted="daily loss limit", autonomy="SHADOW"),
    )
    assert v.approved and v.qty == 10


def test_exit_without_position_is_refused():
    v = RiskKernel(LIMITS).review(OrderIntent(symbol="SPY", action="exit"), acct(), ctx())
    assert not v.approved and v.blocked_by == "EXIT"


def test_daily_loss_breach_boundary():
    assert not daily_loss_breached(97_501, 100_000, 0.025)
    assert daily_loss_breached(97_500, 100_000, 0.025)
    assert review(account=acct(equity=97_500)).blocked_by == "R3"


def test_symbols_parse_every_spelling():
    assert parse("btc/usd").name == "BTC/USD" and parse("BTCUSD").name == "BTC/USD"
    assert parse("BTC-USD").yahoo == "BTC-USD" and parse("BTC/USD").alpaca_position == "BTCUSD"
    assert parse("spy").kind == "equity" and parse("ETH/USD").is_crypto
    assert [s.name for s in parse_list("SPY, BTCUSD,spy")] == ["SPY", "BTC/USD"]
    with pytest.raises(ValueError):
        parse("FOO/USD")


# ------------------------------------------------------------------ SimBroker
def bar(ts, o, h, low, c):
    return Bar(ts=ts, open=o, high=h, low=low, close=c)


async def test_sim_fills_at_next_open_with_costs_and_holds_the_stop():
    b = SimBroker(10_000, fill="next_open", fee_bps={"equity": 10}, slippage_bps=0)
    b.on_bar("SPY", bar(1, 100, 101, 99, 100))
    o = await b.submit(OrderRequest(symbol="SPY", side="buy", qty=10, stop_price=95))
    assert o.status == "new"  # nothing fills at the decision bar's close
    b.on_bar("SPY", bar(2, 102, 103, 101, 102))
    assert o.status == "filled" and o.filled_avg_price == 102 and o.fee == pytest.approx(1.02)
    a = await b.account()
    assert a.cash == pytest.approx(10_000 - 1020 - 1.02) and a.positions["SPY"].stop_price == 95
    fills = b.on_bar("SPY", bar(3, 94, 96, 90, 92))  # gapped through the stop: fills at the open
    assert fills[0].reason.startswith("stop-loss") and fills[0].filled_avg_price == 94
    assert "SPY" not in (await b.account()).positions


async def test_sim_submit_is_idempotent_and_flatten_closes_everything():
    b = SimBroker(10_000, fill="immediate", slippage_bps=0)
    b.set_price("SPY", 100)
    b.set_price("BTC/USD", 50_000)
    r = OrderRequest(symbol="SPY", side="buy", qty=10, client_order_id="ax-1")
    assert (await b.submit(r)).id == (await b.submit(r)).id
    await b.submit(OrderRequest(symbol="BTC/USD", side="buy", qty=0.01))
    assert len((await b.account()).positions) == 2
    await b.flatten_all("kill")
    a = await b.account()
    assert a.positions == {} and a.cash > 9_900


async def test_property_kernel_plus_broker_never_breaks_cash_or_position_caps():
    rng = random.Random(42)
    syms = ["SPY", "AAPL", "BTC/USD"]
    limits = RiskLimits(allowlist=frozenset(syms), max_trades_per_day=10_000, max_open_positions=3)
    kernel = RiskKernel(limits)
    b = SimBroker(100_000, fill="immediate")
    prices = {"SPY": 100.0, "AAPL": 200.0, "BTC/USD": 60_000.0}
    for step in range(600):
        for s in syms:
            prices[s] *= 1 + rng.gauss(0, 0.02)
            b.set_price(s, prices[s], ts=float(step))
        s = rng.choice(syms)
        a = await b.account()
        if rng.random() < 0.6:
            stop = prices[s] * (1 - rng.uniform(-0.05, 0.3))  # some invalid stops on purpose
            req_qty = rng.choice([None, None, rng.uniform(0.001, 5_000)])
            intent = OrderIntent(symbol=s, action="enter_long", stop_price=stop, requested_qty=req_qty)
        else:
            intent = OrderIntent(symbol=s, action="exit")
        c = RiskContext(now=float(step), price=prices[s], kind=parse(s).kind, day_start_equity=a.equity)
        v = kernel.review(intent, a, c)
        if v.approved and intent.action == "enter_long":
            assert v.notional <= limits.max_position_pct * a.equity + 1e-6
            assert v.notional <= a.cash + 1e-6
            await b.submit(OrderRequest(symbol=s, side="buy", qty=v.qty, stop_price=intent.stop_price))
        elif v.approved:
            await b.close(s)
        a2 = await b.account()
        assert a2.cash >= -1e-6
        assert sum(p.market_value for p in a2.positions.values()) <= limits.max_gross_pct * a2.equity * 1.5


# ------------------------------------------------------------------- ledgers
def _exercise(led):
    led.save_order(Order(id="o1", symbol="SPY", side="buy", qty=1, submitted_at=5))
    led.save_contract({"id": "k1", "created_at": 5, "symbol": "SPY", "status": "open", "x": 1})
    for i in range(3):
        led.append_journal("note", f"entry {i}", ts=float(i), symbol="SPY", facts={"i": i})
    led.snapshot(1.0, 100.0, 50.0, 99.0)
    led.set_state("kill", True)
    assert led.orders()[0]["id"] == "o1"
    assert led.contracts("open")[0]["x"] == 1 and led.contracts("closed") == []
    assert [e.text for e in led.journal(limit=2)] == ["entry 1", "entry 2"]
    assert verify_chain(led.journal_all())["ok"]
    assert led.equity_curve()[0]["benchmark"] == 99.0
    assert led.get_state("kill") is True and led.get_state("missing", 7) == 7


def test_memory_ledger_round_trip():
    _exercise(MemoryLedger("replay:t"))


def test_store_ledger_round_trip_and_sessions_are_isolated(tmp_path):
    from axiom.memory.store import Store

    st = Store(tmp_path / "s.db")
    _exercise(StoreLedger(st, "live"))
    other = StoreLedger(st, "replay:x")
    assert other.journal_all() == [] and other.get_state("kill") is None


def test_memory_ledger_flushes_to_the_store(tmp_path):
    from axiom.memory.store import Store

    st = Store(tmp_path / "s.db")
    mem = MemoryLedger("replay:abc")
    _exercise(mem)
    led = mem.flush_to(st)
    assert [e.hash for e in led.journal_all()] == [e.hash for e in mem.journal_all()]
    assert verify_chain(led.journal_all())["ok"] and len(led.orders()) == 1
