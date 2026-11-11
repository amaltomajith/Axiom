"""Alpaca paper trading. `paper=True` is hard-coded: this class cannot reach a live account.

Every name used here was checked against the installed alpaca-py 0.45.0 source. The SDK is synchronous, so
calls run in a worker thread. Protective stops are separate orders placed after an entry fills, because
Alpaca crypto supports no bracket, OCO or OTO orders: crypto gets a GTC stop-limit (crypto has no plain stop
orders), equities a GTC stop. Order ids are our deterministic client ids, so a retried submit is idempotent.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ..models import AccountState, Order, OrderRequest, Position
from ..symbols import parse
from .base import BrokerError

log = logging.getLogger(__name__)

STOP_LIMIT_BUFFER = 0.005  # crypto stop-limit: limit 0.5% under the stop, so a fast fall still fills
_STATUS = {
    "filled": "filled",
    "partially_filled": "partially_filled",
    "canceled": "canceled",
    "expired": "canceled",
    "done_for_day": "canceled",
    "replaced": "canceled",
    "rejected": "rejected",
    "stopped": "filled",
}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _val(x: Any) -> str:
    return str(getattr(x, "value", x) or "")


class AlpacaPaperBroker:
    name = "alpaca"
    is_paper = True

    def __init__(self, api_key: str, secret_key: str, *, client: Any = None, quotes: Any = None):
        if client is None:
            from alpaca.trading.client import TradingClient

            client = TradingClient(api_key, secret_key, paper=True)  # never paper=False
        self.client = client
        self._key, self._secret = api_key, secret_key
        self._quotes = quotes  # callable(symbol) -> float | None; tests inject one
        self._open: dict[str, Order] = {}  # client_order_id -> our view of an order we are tracking
        self._stops: dict[str, dict] = {}  # symbol -> {"cid": stop order client id, "stop": price}
        self._pending_stop: dict[str, float] = {}  # entry client id -> stop price to place after the fill
        self._avg_entry: dict[str, float] = {}
        self._clock: tuple[float, bool] | None = None
        self.stop_error: str | None = (
            None  # last failure to place a broker stop (the engine still checks stops)
        )

    async def _call(self, fn, *a, **kw):
        try:
            return await asyncio.to_thread(fn, *a, **kw)
        except Exception as e:  # APIError and network errors alike
            raise BrokerError(f"Alpaca: {type(e).__name__}: {e}"[:300]) from e

    # --------------------------------------------------------------- account
    async def account(self) -> AccountState:
        acct = await self._call(self.client.get_account)
        raw_positions = await self._call(self.client.get_all_positions)
        positions: dict[str, Position] = {}
        for p in raw_positions:
            try:
                sym = parse(p.symbol).name
            except ValueError:
                continue
            qty = _f(p.qty)
            if qty <= 0:
                continue  # Autopilot is long-only; it never opens shorts
            avg = _f(p.avg_entry_price)
            self._avg_entry[sym] = avg
            positions[sym] = Position(
                symbol=sym, qty=qty, avg_entry=avg, market_price=_f(p.current_price, avg),
                stop_price=(self._stops.get(sym) or {}).get("stop"),
            )  # fmt: skip
        return AccountState(
            equity=_f(acct.equity),
            cash=_f(getattr(acct, "non_marginable_buying_power", None), _f(acct.cash)),
            positions=positions,
            is_paper=True,
            broker=self.name,
        )

    async def preflight(self) -> dict:
        """What the smoke script and startup check: the account can trade, and crypto is enabled."""
        a = await self._call(self.client.get_account)
        return {
            "status": _val(a.status),
            "crypto_status": _val(getattr(a, "crypto_status", None)),
            "trading_blocked": bool(getattr(a, "trading_blocked", False)),
            "account_blocked": bool(getattr(a, "account_blocked", False)),
            "equity": _f(a.equity),
            "last_equity": _f(a.last_equity),
        }

    # ---------------------------------------------------------------- orders
    def _market(self, symbol: str, side: str, qty: float, cid: str):
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        crypto = parse(symbol).is_crypto
        return MarketOrderRequest(
            symbol=symbol, qty=qty, side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.GTC if crypto else TimeInForce.DAY, client_order_id=cid,
        )  # fmt: skip

    def _stop(self, symbol: str, qty: float, stop: float, cid: str):
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import StopLimitOrderRequest, StopOrderRequest

        if parse(symbol).is_crypto:
            return StopLimitOrderRequest(
                symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
                stop_price=round(stop, 2), limit_price=round(stop * (1 - STOP_LIMIT_BUFFER), 2), client_order_id=cid,
            )  # fmt: skip
        return StopOrderRequest(symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
                                stop_price=round(stop, 2), client_order_id=cid)  # fmt: skip

    def _to_order(self, raw: Any, ours: Order | None = None) -> Order:
        o = ours.model_copy() if ours else Order(
            id=raw.client_order_id, symbol=parse(raw.symbol).name, side=_val(raw.side) or "sell",
            qty=_f(raw.qty),
        )  # fmt: skip
        o.broker_id = str(getattr(raw, "id", "") or "") or o.broker_id
        o.status = _STATUS.get(_val(raw.status), "new")  # type: ignore[assignment]
        o.filled_qty = _f(raw.filled_qty)
        fap = getattr(raw, "filled_avg_price", None)
        o.filled_avg_price = _f(fap) if fap not in (None, "") else None
        if o.filled_qty > 0 and o.filled_at is None:
            o.filled_at = time.time()
        return o

    async def submit(self, req: OrderRequest) -> Order:
        if req.client_order_id in self._open:
            return self._open[req.client_order_id]
        try:
            existing = await self._call(self.client.get_order_by_client_id, req.client_order_id)
            return self._track(self._to_order(existing))  # already sent earlier (retry after a crash)
        except BrokerError:
            pass
        ours = Order(id=req.client_order_id, symbol=req.symbol, side=req.side, qty=req.qty,
                     stop_price=req.stop_price, reason=req.reason)  # fmt: skip
        try:
            raw = await self._call(
                self.client.submit_order, self._market(req.symbol, req.side, req.qty, req.client_order_id)
            )
        except BrokerError as e:
            ours.status, ours.error = "rejected", str(e)
            return ours
        if req.side == "buy" and req.stop_price:
            self._pending_stop[req.client_order_id] = req.stop_price
        o = self._track(self._to_order(raw, ours))
        await self._ensure_stop(o)  # crypto market orders often come back already filled
        return o

    async def _ensure_stop(self, o: Order) -> None:
        if o.side == "buy" and o.status == "filled" and o.id in self._pending_stop:
            stop = self._pending_stop.pop(o.id)
            try:
                await self._place_stop(o.symbol, await self._held(o.symbol, o.filled_qty), stop)
                self.stop_error = None
            except (
                BrokerError
            ) as e:  # never let a stop failure break polling: the engine checks stops each tick
                self.stop_error = f"{o.symbol}: the broker stop at {stop:g} was not placed ({e})"[:300]
                log.warning(self.stop_error)

    async def _held(self, symbol: str, filled: float) -> float:
        """What the account can actually sell. Alpaca takes the crypto fee out of the coins received, so a
        0.000136 BTC buy leaves 0.00013566: a stop for the filled quantity would be rejected."""
        if not parse(symbol).is_crypto:
            return filled
        key = symbol.replace("/", "")
        for p in await self._call(self.client.get_all_positions):
            if str(p.symbol).replace("/", "") == key:
                held = _f(getattr(p, "qty_available", None), _f(p.qty))
                return min(filled, held) if held > 0 else filled
        return filled

    def _track(self, o: Order) -> Order:
        self._open[o.id] = o
        return o

    async def _place_stop(self, symbol: str, qty: float, stop: float) -> None:
        cid = f"stop-{symbol.replace('/', '')}-{int(time.time() * 1000)}"
        raw = await self._call(self.client.submit_order, self._stop(symbol, qty, stop, cid))
        o = self._to_order(raw, Order(id=cid, symbol=symbol, side="sell", qty=qty, stop_price=stop,
                                      reason="stop-loss triggered at the broker"))  # fmt: skip
        self._track(o)
        self._stops[symbol] = {"cid": cid, "stop": stop}

    async def _cancel_stop(self, symbol: str) -> None:
        s = self._stops.pop(symbol, None)
        if not s:
            return
        o = self._open.pop(s["cid"], None)
        if o is not None and o.broker_id:
            try:
                await self._call(self.client.cancel_order_by_id, o.broker_id)
            except BrokerError:
                pass  # already filled or cancelled; poll() reconciles

    async def poll(self) -> list[Order]:
        changed: list[Order] = []
        for cid, ours in list(self._open.items()):
            try:
                raw = await self._call(self.client.get_order_by_client_id, cid)
            except BrokerError:
                continue
            o = self._to_order(raw, ours)
            if o.status == ours.status and o.filled_qty == ours.filled_qty:
                await self._ensure_stop(o)
                if o.status in ("filled", "canceled", "rejected") and o.side == "buy":
                    self._open.pop(cid, None)
                continue
            if o.side == "sell" and o.filled_qty > ours.filled_qty and o.filled_avg_price:
                entry = self._avg_entry.get(o.symbol)
                if entry:
                    o.realized_pl = round((o.filled_avg_price - entry) * o.filled_qty, 2)
            self._open[cid] = o
            changed.append(o)
            if o.status in ("filled", "canceled", "rejected"):
                self._open.pop(cid, None)
                if o.side == "sell" and self._stops.get(o.symbol, {}).get("cid") == cid:
                    self._stops.pop(o.symbol, None)
            await self._ensure_stop(o)
        return changed

    async def close(self, symbol: str, reason: str = "") -> Order | None:
        await self._cancel_stop(symbol)
        acct = await self.account()
        pos = acct.positions.get(symbol)
        if pos is None:
            return None
        cid = f"close-{symbol.replace('/', '')}-{int(time.time() * 1000)}"
        last: BrokerError | None = None
        for attempt in range(3):  # a just-cancelled stop can hold the quantity for a moment
            try:
                raw = await self._call(self.client.submit_order, self._market(symbol, "sell", pos.qty, cid))
                ours = Order(id=cid, symbol=symbol, side="sell", qty=pos.qty, reason=reason)
                return self._track(self._to_order(raw, ours))
            except BrokerError as e:
                last = e
                await asyncio.sleep(0.5 * (attempt + 1))
        o = Order(id=cid, symbol=symbol, side="sell", qty=pos.qty, reason=reason, status="rejected",
                  error=str(last))  # fmt: skip
        return o

    async def flatten_all(self, reason: str = "") -> list[Order]:
        await self.account()  # refresh average entries for P&L
        responses = await self._call(self.client.close_all_positions, cancel_orders=True)
        self._stops.clear()
        self._pending_stop.clear()
        out = []
        for r in responses or []:
            body = getattr(r, "body", None)
            if body is not None and getattr(body, "client_order_id", None):
                o = self._to_order(body, Order(id=body.client_order_id, symbol=parse(body.symbol).name, side="sell",
                                               qty=_f(body.qty), reason=reason))  # fmt: skip
                out.append(self._track(o))
        for cid in [
            c
            for c, o in self._open.items()
            if o.status == "new" and o.side == "sell" and c.startswith("stop-")
        ]:
            self._open.pop(cid, None)
        return out

    async def last_price(self, symbol: str) -> float | None:
        if self._quotes is not None:
            return self._quotes(symbol)
        sym = parse(symbol)
        try:
            if sym.is_crypto:
                from alpaca.data.historical import CryptoHistoricalDataClient
                from alpaca.data.requests import CryptoLatestTradeRequest

                c = CryptoHistoricalDataClient(self._key, self._secret)
                res = await asyncio.to_thread(
                    c.get_crypto_latest_trade, CryptoLatestTradeRequest(symbol_or_symbols=sym.name)
                )
            else:
                from alpaca.data.enums import DataFeed
                from alpaca.data.historical import StockHistoricalDataClient
                from alpaca.data.requests import StockLatestTradeRequest

                c = StockHistoricalDataClient(self._key, self._secret)
                req = StockLatestTradeRequest(symbol_or_symbols=sym.name, feed=DataFeed.IEX)
                res = await asyncio.to_thread(c.get_stock_latest_trade, req)
            return float(res[sym.name].price)
        except Exception:
            return None

    async def market_open(self) -> bool:
        if self._clock and time.time() - self._clock[0] < 60:
            return self._clock[1]
        clock = await self._call(self.client.get_clock)
        self._clock = (time.time(), bool(clock.is_open))
        return self._clock[1]

    async def reconcile(self, meta: dict[str, dict]) -> list[str]:
        """After a restart: re-attach open stop orders, and place a stop for any position that lost one."""
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        notes: list[str] = []
        opened = await self._call(
            self.client.get_orders, GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=200)
        )
        for raw in opened:
            o = self._to_order(raw)
            if raw.client_order_id.startswith("stop-") and o.side == "sell":
                self._stops[o.symbol] = {"cid": o.id, "stop": _f(raw.stop_price)}
                o.reason = "stop-loss triggered at the broker"
            self._track(o)
        acct = await self.account()
        for sym, pos in acct.positions.items():
            if sym not in self._stops and (meta.get(sym) or {}).get("stop"):
                await self._place_stop(sym, pos.qty, meta[sym]["stop"])
                notes.append(f"re-placed the {sym} stop at {meta[sym]['stop']:,.2f}")
        return notes
