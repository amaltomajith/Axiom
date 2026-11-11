"""Alpaca paper broker against a fake TradingClient, and the live loop (decisions per bar, watchdog, kill)."""

import asyncio
import time
from types import SimpleNamespace

import pandas as pd
import pytest

from axiom.trading.broker.alpaca import AlpacaPaperBroker
from axiom.trading.broker.base import BrokerError
from axiom.trading.broker.sim import SimBroker
from axiom.trading.engine import KILL_FILE
from axiom.trading.live import Trader, periods_per_year
from axiom.trading.models import OrderRequest
from axiom.trading.symbols import parse

from .conftest import make_ohlcv


class FakeTradingClient:
    """Implements the slice of alpaca-py's TradingClient the broker uses. Market orders fill at `price`."""

    def __init__(self, price=100.0, equity=100_000.0):
        self.price = price
        self.cash = equity
        self.orders: dict[str, SimpleNamespace] = {}
        self.positions: dict[str, SimpleNamespace] = {}
        self.cancelled: list[str] = []
        self.calls: list[str] = []

    def get_account(self):
        mv = sum(float(p.qty) * self.price for p in self.positions.values())
        return SimpleNamespace(equity=str(self.cash + mv), last_equity=str(self.cash), cash=str(self.cash),
                               non_marginable_buying_power=str(self.cash), status="ACTIVE", crypto_status="ACTIVE",
                               trading_blocked=False, account_blocked=False)  # fmt: skip

    def get_all_positions(self):
        return list(self.positions.values())

    def get_order_by_client_id(self, cid):
        if cid not in self.orders:
            raise RuntimeError("order not found")
        return self.orders[cid]

    def submit_order(self, req):
        self.calls.append(type(req).__name__)
        side = req.side.value
        o = SimpleNamespace(id=f"uuid-{len(self.orders)}", client_order_id=req.client_order_id, symbol=req.symbol,
                            side=side, qty=str(req.qty), status="new", filled_qty="0", filled_avg_price=None,
                            stop_price=getattr(req, "stop_price", None), type=req.type.value,
                            time_in_force=req.time_in_force.value)  # fmt: skip
        if o.type == "market":
            self._fill(o)
        self.orders[o.client_order_id] = o
        return o

    def _fill(self, o):
        q = float(o.qty)
        key = o.symbol.replace("/", "")
        if o.side == "buy":
            self.cash -= q * self.price
            self.positions[key] = SimpleNamespace(symbol=key, qty=str(q), avg_entry_price=str(self.price),
                                                  current_price=str(self.price))  # fmt: skip
        else:
            self.cash += q * self.price
            self.positions.pop(key, None)
        o.status, o.filled_qty, o.filled_avg_price = "filled", str(q), str(self.price)

    def trigger_stops(self, price):
        self.price = price
        for o in self.orders.values():
            if o.type in ("stop", "stop_limit") and o.status == "new" and float(o.stop_price) >= price:
                self._fill(o)

    def cancel_order_by_id(self, oid):
        for o in self.orders.values():
            if o.id == oid:
                o.status = "canceled"
                self.cancelled.append(oid)

    def close_all_positions(self, cancel_orders=None):
        out = []
        for o in self.orders.values():
            if o.status == "new":
                o.status = "canceled"
        for key, p in list(self.positions.items()):
            o = SimpleNamespace(id=f"uuid-c{key}", client_order_id=f"close-all-{key}", symbol=key, side="sell",
                                qty=p.qty, status="new", filled_qty="0", filled_avg_price=None, type="market")  # fmt: skip
            self._fill(o)
            self.orders[o.client_order_id] = o
            out.append(SimpleNamespace(order_id=o.id, status=200, symbol=key, body=o))
        return out

    def get_clock(self):
        return SimpleNamespace(is_open=False)

    def get_orders(self, req):
        return [o for o in self.orders.values() if o.status == "new"]


def broker(price=100.0):
    fake = FakeTradingClient(price)
    return AlpacaPaperBroker("k", "s", client=fake, quotes=lambda s: fake.price), fake


def test_trading_client_is_always_paper(monkeypatch):
    import alpaca.trading.client as tc

    seen = {}

    class Spy:
        def __init__(self, *a, **kw):
            seen.update(kw)

    monkeypatch.setattr(tc, "TradingClient", Spy)
    AlpacaPaperBroker("k", "s")
    assert seen["paper"] is True


async def test_crypto_entry_fills_then_a_gtc_stop_limit_is_placed():
    b, fake = broker(60_000.0)
    o = await b.submit(
        OrderRequest(symbol="BTC/USD", side="buy", qty=0.1, stop_price=58_000, client_order_id="ax-1")
    )
    assert o.status == "filled" and fake.orders["ax-1"].time_in_force == "gtc"
    assert fake.calls == ["MarketOrderRequest", "StopLimitOrderRequest"]  # stop placed as soon as it filled
    stop = next(x for x in fake.orders.values() if x.type == "stop_limit")
    assert float(stop.stop_price) == 58_000 and stop.time_in_force == "gtc"
    acct = await b.account()
    assert acct.positions["BTC/USD"].stop_price == 58_000


async def test_equity_stop_is_a_plain_stop_and_a_broker_stop_fill_reports_pnl():
    b, fake = broker(100.0)
    await b.submit(OrderRequest(symbol="SPY", side="buy", qty=10, stop_price=95, client_order_id="ax-2"))
    assert "StopOrderRequest" in fake.calls
    await b.account()
    fake.trigger_stops(94.0)
    fills = await b.poll()
    stop_fill = next(f for f in fills if f.reason.startswith("stop-loss"))
    assert stop_fill.status == "filled" and stop_fill.realized_pl == pytest.approx(-60.0)
    assert "SPY" not in b._stops


async def test_moving_a_broker_stop_cancels_the_old_order_and_places_the_new_one():
    b, fake = broker(60_000.0)
    await b.submit(
        OrderRequest(symbol="BTC/USD", side="buy", qty=0.1, stop_price=58_000, client_order_id="ax-9")
    )
    first = next(x for x in fake.orders.values() if x.type == "stop_limit")
    await asyncio.sleep(0.002)  # stop order ids carry a millisecond timestamp
    await b.set_stop("BTC/USD", 59_000.0)
    live = [x for x in fake.orders.values() if x.type == "stop_limit" and x.status == "new"]
    assert first.status == "canceled" and len(live) == 1 and float(live[0].stop_price) == 59_000
    assert (await b.account()).positions["BTC/USD"].stop_price == 59_000 and b.stop_error is None
    with pytest.raises(BrokerError):
        await b.set_stop("ETH/USD", 10.0)


async def test_submit_is_idempotent_across_restarts():
    b, fake = broker()
    req = OrderRequest(symbol="SPY", side="buy", qty=1, client_order_id="ax-3")
    await b.submit(req)
    b2 = AlpacaPaperBroker("k", "s", client=fake, quotes=lambda s: 100.0)  # a new process, same account
    again = await b2.submit(req)
    assert again.id == "ax-3" and sum(1 for c in fake.calls if c == "MarketOrderRequest") == 1


async def test_close_cancels_the_stop_then_sells():
    b, fake = broker()
    await b.submit(OrderRequest(symbol="SPY", side="buy", qty=5, stop_price=95, client_order_id="ax-4"))
    o = await b.close("SPY", "signal off")
    assert fake.cancelled and o.status == "filled" and (await b.account()).positions == {}


async def test_flatten_all_closes_everything_and_reports_orders():
    b, fake = broker()
    await b.submit(OrderRequest(symbol="SPY", side="buy", qty=5, client_order_id="ax-5"))
    await b.submit(OrderRequest(symbol="BTC/USD", side="buy", qty=0.01, client_order_id="ax-6"))
    orders = await b.flatten_all("kill")
    assert len(orders) == 2 and (await b.account()).positions == {}


async def test_rejected_submit_comes_back_as_a_rejected_order():
    b, fake = broker()

    def boom(req):
        raise RuntimeError("insufficient buying power")

    fake.submit_order = boom
    o = await b.submit(OrderRequest(symbol="SPY", side="buy", qty=5, client_order_id="ax-7"))
    assert o.status == "rejected" and "insufficient" in o.error


async def test_reconcile_replaces_a_missing_stop():
    b, fake = broker()
    await b.submit(OrderRequest(symbol="SPY", side="buy", qty=5, client_order_id="ax-8"))  # no stop
    b2 = AlpacaPaperBroker("k", "s", client=fake, quotes=lambda s: 100.0)
    notes = await b2.reconcile({"SPY": {"stop": 96.0}})
    assert notes and b2._stops["SPY"]["stop"] == 96.0


# ------------------------------------------------------------------ live loop
def hourly(n=400, seed=5, end=None):
    df = make_ohlcv(n, seed=seed, drift=0.0004, vol=0.01)
    end = end or pd.Timestamp.now("UTC").tz_localize(None).floor("h") - pd.Timedelta(hours=1)
    df.index = pd.date_range(end=end, periods=n, freq="h")
    return df


def trader(tmp_path, fetch, monkeypatch, **env):
    from axiom.config import get_settings
    from axiom.memory.store import Store

    for k, v in {"TRADER_SYMBOLS": "BTC/USD,ETH/USD", "TRADER_TIMEFRAME": "1Hour", "TRADER_AUTONOMY_START": "AUTONOMOUS",
                 "TRADER_INTERVAL_SECONDS": "5", **env}.items():  # fmt: skip
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return Trader.from_settings(Store(tmp_path / "s.db"), fetch=fetch)


async def test_live_tick_decides_once_per_completed_bar(tmp_path, monkeypatch):
    data = {"BTC/USD": hourly(seed=5), "ETH/USD": hourly(seed=6)}

    async def fetch(sym):
        return data[sym.name]

    t = trader(tmp_path, fetch, monkeypatch)
    assert isinstance(t.broker, SimBroker)
    await t.start()
    first = await t.tick()
    assert sorted(first["decided"]) == ["BTC/USD", "ETH/USD"]
    again = await t.tick()
    assert again["decided"] == []  # same bars: no new decisions
    st = t.status()
    assert st["heartbeat_age_seconds"] is not None and st["broker"] == "sim"
    assert t.engine.benchmark_value == pytest.approx(100_000, rel=0.01)
    assert any("Autopilot started" in e.text for e in t.engine.ledger.journal_all())


async def test_watchdog_halts_and_flattens_after_three_failed_ticks(tmp_path, monkeypatch):
    calls = {"n": 0}
    good = {"BTC/USD": hourly(seed=5), "ETH/USD": hourly(seed=6)}

    async def fetch(sym):
        if calls["n"] >= 1:
            raise RuntimeError("feed down")
        return good[sym.name]

    t = trader(tmp_path, fetch, monkeypatch, TRADER_INTERVAL_SECONDS="5")
    t.interval = 0.01
    await t.start()
    await t.tick()
    t.broker.set_price("BTC/USD", 100.0)
    await t.broker.submit(OrderRequest(symbol="BTC/USD", side="buy", qty=1))
    calls["n"] = 1
    t.engine.set_books({})

    import asyncio

    task = asyncio.create_task(t.run_forever())
    for _ in range(200):
        await asyncio.sleep(0.02)
        if t.engine.st["halted"]:
            break
    await t.stop()
    task.cancel()
    assert t.engine.st["halted"] and t.engine.st["halted"].startswith("watchdog")
    assert (await t.broker.account()).positions == {}
    assert any(e.kind == "halt" and "Watchdog" in e.text for e in t.engine.ledger.journal_all())


async def test_cli_kill_file_flattens_on_the_next_tick(tmp_path, monkeypatch):
    import axiom.trading.engine as engine_mod

    kf = tmp_path / "KILL"
    monkeypatch.setattr(engine_mod, "KILL_FILE", kf)
    data = {"BTC/USD": hourly(seed=5), "ETH/USD": hourly(seed=6)}

    async def fetch(sym):
        return data[sym.name]

    t = trader(tmp_path, fetch, monkeypatch)
    t.engine.cfg.kill_file = kf
    await t.start()
    await t.tick()
    t.broker.set_price("BTC/USD", 100.0)
    await t.broker.submit(OrderRequest(symbol="BTC/USD", side="buy", qty=1))
    kf.write_text("stop now")
    await t.tick()
    assert (await t.broker.account()).positions == {}
    assert t.status()["killed"] is True
    assert KILL_FILE.name == "KILL"


def test_alpaca_broker_needs_keys(tmp_path, monkeypatch):
    with pytest.raises(BrokerError):
        trader(tmp_path, None, monkeypatch, TRADER_BROKER="alpaca", ALPACA_API_KEY="", ALPACA_SECRET_KEY="")


def test_no_keys_means_crypto_only_intraday(tmp_path, monkeypatch):
    t = trader(tmp_path, None, monkeypatch, TRADER_SYMBOLS="BTC/USD,SPY")
    assert [s.name for s in t.symbols] == ["BTC/USD"]


def test_periods_per_year():
    assert periods_per_year([parse("BTC/USD")], 3600) == 8760
    assert periods_per_year([parse("SPY")], 86_400) == 252
    assert time.time() > 0


async def test_crypto_stop_is_sized_from_the_coins_held_after_the_fee():
    """Alpaca paper takes the crypto fee out of the coins: 0.000136 BTC bought leaves 0.00013566 to sell."""
    b, fake = broker(73_700.0)
    fill = fake._fill

    def fill_with_fee(o):
        fill(o)
        key = o.symbol.replace("/", "")
        if o.side == "buy" and key in fake.positions:
            fake.positions[key].qty = fake.positions[key].qty_available = "0.00013566"

    fake._fill = fill_with_fee
    real_submit = fake.submit_order

    def submit(req):
        held = sum(float(p.qty) for p in fake.positions.values())
        if req.side.value == "sell" and float(req.qty) > held:
            raise RuntimeError("insufficient balance for BTC")
        return real_submit(req)

    fake.submit_order = submit
    await b.submit(
        OrderRequest(symbol="BTC/USD", side="buy", qty=0.000136, stop_price=72_000, client_order_id="ax-f")
    )
    stop = next(x for x in fake.orders.values() if x.type == "stop_limit")
    assert float(stop.qty) == 0.00013566 and b.stop_error is None


async def test_a_rejected_broker_stop_is_reported_not_raised():
    b, fake = broker(60_000.0)
    real_submit = fake.submit_order

    def submit(req):
        if type(req).__name__ == "StopLimitOrderRequest":
            raise RuntimeError("stop rejected")
        return real_submit(req)

    fake.submit_order = submit
    o = await b.submit(
        OrderRequest(symbol="BTC/USD", side="buy", qty=0.1, stop_price=58_000, client_order_id="ax-r")
    )
    assert o.status == "filled" and "was not placed" in b.stop_error
    assert await b.poll() == []  # polling keeps working
