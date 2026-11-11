"""A simulated paper broker: the Time Machine's exchange and the offline demo's broker.

`fill="next_open"` (backtests) fills market orders at the next bar's open, so a decision made on bar t's
close can never trade at that close. `fill="immediate"` (live sim) fills at the last price. Every fill pays
fees and slippage. Protective stops are held by the broker and trigger on the bar's low; a gap through the
stop fills at the open, which is worse, as it would be in reality.
"""

from __future__ import annotations

import math
import time
from typing import Literal

from ..models import AccountState, Bar, Order, OrderRequest, Position
from ..symbols import parse


class SimBroker:
    name = "sim"
    is_paper = True

    def __init__(
        self,
        starting_cash: float = 100_000.0,
        *,
        fill: Literal["next_open", "immediate"] = "next_open",
        fee_bps: dict[str, float] | None = None,
        slippage_bps: float = 5.0,
    ):
        self.cash = float(starting_cash)
        self.fill = fill
        self.fee_bps = fee_bps or {"crypto": 25.0, "equity": 5.0}
        self.slippage_bps = slippage_bps
        self.positions: dict[str, Position] = {}
        self.marks: dict[str, float] = {}
        self.now: float = time.time()
        self._pending: list[Order] = []
        self._events: list[Order] = []
        self.orders: dict[str, Order] = {}
        self.fees_paid = 0.0

    # ----------------------------------------------------------------- feed
    def on_bar(self, symbol: str, bar: Bar) -> list[Order]:
        """Advance one symbol by one bar: fill pending orders at the open, then trigger stops, then mark."""
        self.now = bar.ts
        filled: list[Order] = []
        for o in [o for o in self._pending if o.symbol == symbol]:
            self._pending.remove(o)
            self._execute(o, bar.open)
            filled.append(o)
        pos = self.positions.get(symbol)
        if pos is not None and pos.stop_price is not None and bar.low <= pos.stop_price:
            px = min(bar.open, pos.stop_price)  # gapped through: the open is the first price available
            o = Order(id=f"stop-{symbol}-{int(bar.ts)}", symbol=symbol, side="sell", qty=pos.qty,
                      reason="stop-loss triggered at the broker", submitted_at=bar.ts)  # fmt: skip
            self.orders[o.id] = o
            self._execute(o, px)
            filled.append(o)
        self.marks[symbol] = bar.close
        if symbol in self.positions:
            self.positions[symbol].market_price = bar.close
        return filled

    def set_price(self, symbol: str, price: float, ts: float | None = None) -> None:
        self.marks[symbol] = price
        if ts is not None:
            self.now = ts
        if symbol in self.positions:
            self.positions[symbol].market_price = price

    # -------------------------------------------------------------- protocol
    async def account(self) -> AccountState:
        return self.account_now()

    def account_now(self) -> AccountState:
        mv = sum(p.qty * p.market_price for p in self.positions.values())
        return AccountState(
            equity=self.cash + mv,
            cash=self.cash,
            positions={s: p.model_copy() for s, p in self.positions.items()},
            is_paper=True,
            broker=self.name,
        )

    async def submit(self, req: OrderRequest) -> Order:
        return self.submit_now(req)

    def submit_now(self, req: OrderRequest) -> Order:
        if req.client_order_id in self.orders:  # idempotent: a retried submit returns the first order
            return self.orders[req.client_order_id]
        o = Order(id=req.client_order_id, symbol=req.symbol, side=req.side, qty=req.qty,
                  stop_price=req.stop_price, reason=req.reason, submitted_at=self.now)  # fmt: skip
        self.orders[o.id] = o
        if req.side == "sell" and req.symbol not in self.positions:
            o.status, o.error = "rejected", "no position to sell"
            self._events.append(o)
            return o
        if self.fill == "immediate" and req.symbol in self.marks:
            self._execute(o, self.marks[req.symbol])
        else:
            self._pending.append(o)
        return o

    async def close(self, symbol: str, reason: str = "") -> Order | None:
        return self.close_now(symbol, reason)

    def close_now(self, symbol: str, reason: str = "") -> Order | None:
        self._pending = [o for o in self._pending if o.symbol != symbol]
        pos = self.positions.get(symbol)
        if pos is None:
            return None
        o = Order(id=f"close-{symbol}-{int(self.now)}-{len(self.orders)}", symbol=symbol, side="sell",
                  qty=pos.qty, reason=reason, submitted_at=self.now)  # fmt: skip
        self.orders[o.id] = o
        if self.fill == "immediate":
            self._execute(o, self.marks.get(symbol, pos.market_price))
        else:
            self._pending.append(o)
        return o

    async def flatten_all(self, reason: str = "") -> list[Order]:
        self._pending = []
        return [o for s in list(self.positions) if (o := self.close_now(s, reason)) is not None]

    async def poll(self) -> list[Order]:
        out, self._events = self._events, []
        return out

    async def last_price(self, symbol: str) -> float | None:
        return self.marks.get(symbol)

    # ------------------------------------------------------------- internals
    def _execute(self, o: Order, ref_price: float) -> None:
        kind = parse(o.symbol).kind
        slip = self.slippage_bps / 1e4
        px = ref_price * (1 + slip) if o.side == "buy" else ref_price * (1 - slip)
        fee_rate = self.fee_bps.get(kind, 5.0) / 1e4
        qty = o.qty
        if o.side == "buy":
            affordable = self.cash / (px * (1 + fee_rate))
            if qty > affordable:  # a gap up can make the planned size unaffordable: fill what cash allows
                qty = math.floor(affordable) if kind == "equity" else math.floor(affordable * 1e6) / 1e6
            if qty <= 0:
                o.status, o.error = "rejected", "insufficient cash"
                self._events.append(o)
                return
            fee = qty * px * fee_rate
            self.cash -= qty * px + fee
            prev = self.positions.get(o.symbol)
            if prev is None:
                self.positions[o.symbol] = Position(symbol=o.symbol, qty=qty, avg_entry=px, market_price=px,
                                                    stop_price=o.stop_price, opened_at=self.now)  # fmt: skip
            else:
                total = prev.qty + qty
                prev.avg_entry = (prev.avg_entry * prev.qty + px * qty) / total
                prev.qty = total
                prev.stop_price = o.stop_price or prev.stop_price
        else:
            pos = self.positions.get(o.symbol)
            if pos is None:
                o.status, o.error = "rejected", "no position to sell"
                self._events.append(o)
                return
            qty = min(qty, pos.qty)
            fee = qty * px * fee_rate
            self.cash += qty * px - fee
            o.realized_pl = round((px - pos.avg_entry) * qty - fee, 2)
            pos.qty -= qty
            if pos.qty <= 1e-9:
                del self.positions[o.symbol]
        self.fees_paid += fee
        o.fee = round(fee, 4)
        o.filled_qty, o.filled_avg_price = qty, px
        o.status = "filled" if abs(qty - o.qty) < 1e-9 else "partially_filled"
        o.filled_at = self.now
        self._events.append(o)
