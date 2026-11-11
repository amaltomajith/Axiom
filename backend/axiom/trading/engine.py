"""The engine: one decision path, driven by the Time Machine (history) or the live loop (now).

Each `step(now, index)`:
  1. records fills since the last tick (including stops the broker triggered),
  2. honours the kill switch (flatten and stop) and the daily loss limit (halt and flatten),
  3. for each symbol with a new bar: re-ranks the tournament when due, enforces the stop, asks the brain,
     sends the intent through the Risk Kernel, then submits, queues it for approval, or journals the block.

Nothing here knows whether the broker is simulated or Alpaca, or whether the ledger is memory or database.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from axiom.config import BACKEND_DIR

from . import journal_text as jt
from .brain import Brain, Decision, MarketView
from .broker.base import Broker
from .models import (
    AUTONOMY_LEVELS,
    AccountState,
    Autonomy,
    Order,
    OrderIntent,
    OrderRequest,
    RiskVerdict,
    new_id,
)
from .risk import RiskContext, RiskKernel, daily_loss_breached, daily_pl_pct
from .strategies import SignalBook
from .symbols import Symbol, parse
from .tournament import Ranking, TournamentConfig, rank

KILL_FILE = BACKEND_DIR / "KILL"


@dataclass
class EngineConfig:
    symbols: list[Symbol]
    session: str = "live"
    bar_seconds: float = 86_400
    max_data_age_seconds: float = 4 * 86_400
    stop_atr_mult: float = 2.0
    tournament: TournamentConfig = field(default_factory=TournamentConfig)
    cost_bps: dict[str, float] = field(default_factory=lambda: {"crypto": 30.0, "equity": 10.0})
    autonomy: Autonomy = "AUTONOMOUS"
    kill_file: Path | None = None  # live only: the CLI and humans can drop this file to kill the agent


def order_id(session: str, symbol: str, ts: float, side: str) -> str:
    """Deterministic client order id: a replay is reproducible, and a retried submit is idempotent."""
    return "ax-" + hashlib.sha1(f"{session}|{symbol}|{ts:.3f}|{side}".encode()).hexdigest()[:20]


def utc_day(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


class Engine:
    def __init__(
        self,
        cfg: EngineConfig,
        broker: Broker,
        ledger,
        kernel: RiskKernel,
        brain: Brain,
        *,
        contracts=None,
        autonomy=None,
    ):
        self.cfg = cfg
        self.broker = broker
        self.ledger = ledger
        self.kernel = kernel
        self.brain = brain
        self.contracts = contracts  # ContractBook (trade contracts), optional
        self.autonomy = autonomy  # AutonomyLadder, optional
        self.books: dict[str, SignalBook] = {}
        self.rankings: dict[str, Ranking] = {}
        self.benchmark_value: float | None = None
        self.listeners: list[Callable[[dict], None]] = []
        self.last_decisions: dict[str, dict] = {}
        saved = ledger.get_state("engine") or {}
        # Rankings are rebuilt on the next completed bar; until then show the regimes from before the restart.
        self.saved_regimes: dict[str, dict] = dict(ledger.get_state("regimes") or {})
        self.st: dict[str, Any] = {
            "day": None,
            "day_start_equity": None,
            "trades_today": 0,
            "halted": None,
            "last_stopout": {},
            "meta": {},  # symbol -> strategy, contract, entry facts of the open position
            "pending": [],  # SUPERVISED entries waiting for a human
            "last_block": {},
            "autonomy": cfg.autonomy,
            "kill_noted": False,
            **saved,
        }

    # ------------------------------------------------------------------ events
    def emit(self, kind: str, **data: Any) -> None:
        ev = {"type": kind, "ts": time.time(), **data}
        for fn in list(self.listeners):
            try:
                fn(ev)
            except Exception:  # a broken listener must never stop trading or stops
                pass

    def journal(
        self, kind: str, text: str, *, ts: float, symbol: str | None = None, facts: dict | None = None
    ):
        e = self.ledger.append_journal(kind, text, ts=ts, symbol=symbol, facts=facts)
        self.emit("journal", entry=e.model_dump())
        return e

    def regimes(self) -> dict[str, dict]:
        """Market regime per symbol from the latest strategy check, or the saved one right after a restart."""
        return {**self.saved_regimes, **{sym: r.regime for sym, r in self.rankings.items()}}

    def _save(self) -> None:
        self.ledger.set_state("engine", self.st)
        if self.rankings:
            self.ledger.set_state("regimes", self.regimes())

    # ------------------------------------------------------------- properties
    @property
    def killed(self) -> bool:
        return bool(self.ledger.get_state("killed")) or bool(
            self.cfg.kill_file and self.cfg.kill_file.exists()
        )

    @property
    def level(self) -> Autonomy:
        return self.st["autonomy"]

    def set_books(self, books: dict[str, SignalBook]) -> None:
        self.books = books

    # ------------------------------------------------------------ human levers
    async def kill(
        self, reason: str = "human pressed the kill switch", now: float | None = None
    ) -> list[Order]:
        now = now or time.time()
        self.ledger.set_state("killed", True)
        orders = await self.broker.flatten_all(f"kill switch: {reason}")
        for o in orders:
            self._remember_exit(o.symbol, "kill switch")
            self.ledger.save_order(o)
        self.st["pending"] = []
        self.st["kill_noted"] = True
        self.journal(
            "kill", jt.kill(reason, len(orders)), ts=now, facts={"reason": reason, "closed": len(orders)}
        )
        self._save()
        self.emit("state")
        return orders

    async def resume(self, who: str = "human", now: float | None = None) -> None:
        now = now or time.time()
        self.ledger.set_state("killed", False)
        if self.cfg.kill_file and self.cfg.kill_file.exists():
            self.cfg.kill_file.unlink()
        self.st["kill_noted"] = False
        if self.st["halted"] and self.st["halted"].startswith("watchdog"):
            self.st["halted"] = None  # a human has looked; the daily loss halt still waits for the next day
        self.journal("resume", jt.resume(who), ts=now)
        self._save()
        self.emit("state")

    def set_autonomy(self, level: Autonomy, why: str, now: float | None = None) -> None:
        if level not in AUTONOMY_LEVELS or level == self.level:
            return
        old = self.level
        self.st["autonomy"] = level
        self.journal("autonomy", jt.autonomy(old, level, why), ts=now or time.time(),
                     facts={"from": old, "to": level, "why": why})  # fmt: skip
        if level != "SUPERVISED":
            self.st["pending"] = []
        self._save()
        self.emit("state")

    async def approve(self, pending_id: str, now: float | None = None) -> dict:
        now = now or time.time()
        item = next((p for p in self.st["pending"] if p["id"] == pending_id), None)
        if item is None:
            raise KeyError(pending_id)
        self.st["pending"] = [p for p in self.st["pending"] if p["id"] != pending_id]
        intent = OrderIntent(**{**item["intent"], "source": "human"})
        acct = await self.broker.account()
        price = (await self.broker.last_price(intent.symbol)) or item["verdict"]["price"]
        verdict = self.kernel.review(intent, acct, self._ctx(intent.symbol, price, now, acct, data_age=0.0))
        if not verdict.approved:
            self.journal("blocked", jt.blocked(intent, verdict, approved_by_human=True), ts=now,
                         symbol=intent.symbol, facts=_vfacts(intent, verdict))  # fmt: skip
            self._save()
            return {"ok": False, "reason": verdict.reason}
        dec = Decision(**item["decision"])
        order = await self._submit_entry(intent, verdict, dec, now, acct)
        self._save()
        return {"ok": True, "order": order.model_dump()}

    def reject(self, pending_id: str, now: float | None = None) -> None:
        item = next((p for p in self.st["pending"] if p["id"] == pending_id), None)
        if item is None:
            raise KeyError(pending_id)
        self.st["pending"] = [p for p in self.st["pending"] if p["id"] != pending_id]
        self.journal("note", f"A human rejected the proposed {item['intent']['symbol']} entry.",
                     ts=now or time.time(), symbol=item["intent"]["symbol"])  # fmt: skip
        self._save()

    # ----------------------------------------------- requests from MCP tools
    async def propose(self, symbol: str, *, strategy: str | None = None, size_fraction: float = 1.0,
                      reason: str = "", now: float | None = None) -> dict:  # fmt: skip
        """An entry asked for from outside the loop (an MCP client). It gets no shortcut: the strategy must
        have qualified and be signalling now, the kernel sizes it, and Supervised mode queues it for a human."""
        now = now or time.time()
        book, r = self.books.get(symbol), self.rankings.get(symbol)
        if book is None or r is None:
            raise ValueError(f"{symbol} has no market data or tournament yet; is the Autopilot watching it?")
        acct = await self.broker.account()
        if symbol in acct.positions:
            raise ValueError(f"{symbol} is already held; one position per symbol")
        if any(p["intent"]["symbol"] == symbol for p in self.st["pending"]):
            raise ValueError(f"an entry for {symbol} is already waiting for approval")
        live = [s.strategy for s in r.qualified if float(book.signals[s.strategy][-1]) == 1.0]
        strategy = strategy or (live[0] if live else None)
        if strategy not in live:
            raise ValueError(
                f"{strategy or 'no strategy'} is not both qualified and signalling long on {symbol} "
                f"(eligible now: {', '.join(live) or 'none'})"
            )
        price, atr = float(book.close[-1]), float(book.atr[-1])
        std = next(s for s in r.qualified if s.strategy == strategy)
        dec = Decision(
            symbol=symbol, ts=now, action="enter_long", strategy=strategy, source="desk",
            confidence=round(min(0.8, 0.5 + 0.05 * max(0.0, std.sharpe)), 2),
            reason=f"Requested through an MCP order tool: {reason.strip()[:300] or 'no reason given'}",
            expected_move_pct=round(100 * 2 * atr / price, 2) if price else None,
            size_factor=size_fraction if size_fraction < 1.0 else None,
        )  # fmt: skip
        intent = OrderIntent(
            symbol=symbol, action="enter_long", stop_price=round(price - self.cfg.stop_atr_mult * atr, 6),
            reason=dec.reason, strategy=strategy, confidence=dec.confidence, source="desk",
        )  # fmt: skip
        ctx = self._ctx(symbol, price, now, acct, data_age=now - float(book.ts[-1]))
        verdict = self.kernel.review(intent, acct, ctx)
        if verdict.approved and dec.size_factor is not None:
            intent.requested_qty = _scaled(verdict.qty, dec.size_factor, parse(symbol).kind)
            verdict = self.kernel.review(intent, acct, ctx)
        out = {"symbol": symbol, "strategy": strategy, "verdict": verdict.model_dump()}
        if not verdict.approved:
            self.journal("blocked", jt.blocked(intent, verdict), ts=now, symbol=symbol,
                         facts=_vfacts(intent, verdict))  # fmt: skip
            self._save()
            return {**out, "status": "blocked", "reason": verdict.reason}
        if verdict.needs_approval:
            item = {"id": new_id("p-"), "created_at": now, "intent": intent.model_dump(),
                    "verdict": verdict.model_dump(), "decision": dec.model_dump()}  # fmt: skip
            self.st["pending"].append(item)
            self.journal("proposal", jt.proposal(intent, verdict), ts=now, symbol=symbol,
                         facts=_vfacts(intent, verdict))  # fmt: skip
            self.emit("pending", item=item)
            self._save()
            return {**out, "status": "pending_approval", "pending_id": item["id"]}
        order = await self._submit_entry(intent, verdict, dec, now, acct)
        self._save()
        return {**out, "status": "submitted" if order.status != "rejected" else "rejected",
                "order": order.model_dump()}  # fmt: skip

    async def tighten_stop(self, symbol: str, stop_price: float, now: float | None = None) -> dict:
        """Raise a position's stop. A stop can be moved up to lock in less risk, never down."""
        now = now or time.time()
        pos = (await self.broker.account()).positions.get(symbol)
        if pos is None:
            raise ValueError(f"no open {symbol} position")
        old = pos.stop_price if pos.stop_price is not None else self.st["meta"].get(symbol, {}).get("stop")
        price = (await self.broker.last_price(symbol)) or pos.market_price
        if old is not None and stop_price <= old:
            raise ValueError(
                f"a stop can only be tightened: {stop_price:,.2f} is not above the current {old:,.2f}"
            )
        if stop_price >= price:
            raise ValueError(f"the stop {stop_price:,.2f} must stay below the price {price:,.2f}")
        await self.broker.set_stop(symbol, stop_price)
        self.st["meta"].setdefault(symbol, {})["stop"] = stop_price
        was = "nothing" if old is None else jt.money(old)
        self.journal(
            "note",
            f"Tightened the {symbol} stop-loss from {was} to {jt.money(stop_price)} "
            f"(price {jt.money(price)}). Stops only ever move up.",
            ts=now, symbol=symbol, facts={"old_stop": old, "stop_price": stop_price, "price": price},
        )  # fmt: skip
        self._save()
        self.emit("state")
        return {"ok": True, "symbol": symbol, "old_stop": old, "stop_price": stop_price}

    async def close_position(self, symbol: str, reason: str, now: float | None = None) -> dict:
        now = now or time.time()
        if symbol not in (await self.broker.account()).positions:
            raise ValueError(f"no open {symbol} position")
        order = await self._exit(symbol, reason.strip()[:200] or "closed through an MCP tool", now)
        for o in await self.broker.poll():
            self._on_fill(o, now)
        self._save()
        return {"ok": order is not None, "order": order.model_dump() if order else None}

    # ------------------------------------------------------------------- day
    async def roll_day(self, now: float, acct: AccountState | None = None) -> None:
        day = utc_day(now)
        if self.st["day"] == day:
            return
        acct = acct or await self.broker.account()
        self.st.update(day=day, day_start_equity=acct.equity, trades_today=0)
        if self.st["halted"]:
            self.journal("resume", jt.new_day_unhalt(self.st["halted"]), ts=now)
            self.st["halted"] = None

    # ------------------------------------------------------------------ step
    async def step(self, now: float, index: dict[str, int]) -> list[Decision]:
        for o in await self.broker.poll():
            self._on_fill(o, now)
        acct = await self.broker.account()
        await self.roll_day(now, acct)
        self.ledger.snapshot(now, round(acct.equity, 2), round(acct.cash, 2),
                             None if self.benchmark_value is None else round(self.benchmark_value, 2))  # fmt: skip

        if self.killed:
            if acct.positions:
                for o in await self.broker.flatten_all("kill switch engaged"):
                    self._remember_exit(o.symbol, "kill switch")
                    self.ledger.save_order(o)
            if not self.st["kill_noted"]:
                self.journal("kill", jt.kill("kill switch found engaged", len(acct.positions)), ts=now)
                self.st["kill_noted"] = True
            self._save()
            return []

        lim = self.kernel.limits
        if not self.st["halted"] and daily_loss_breached(
            acct.equity, self.st["day_start_equity"], lim.daily_loss_limit_pct
        ):
            pl = daily_pl_pct(acct.equity, self.st["day_start_equity"])
            self.st["halted"] = f"daily loss limit ({pl:.2%} today, limit -{lim.daily_loss_limit_pct:.2%})"
            orders = await self.broker.flatten_all("daily loss limit")
            for o in orders:
                self._remember_exit(o.symbol, "daily loss limit")
                self.ledger.save_order(o)
            self.st["pending"] = []
            self.journal("halt", jt.halt(pl, lim.daily_loss_limit_pct, len(orders)), ts=now,
                         facts={"daily_pl_pct": round(pl, 4), "closed": len(orders)})  # fmt: skip
            if self.autonomy is not None:
                self.autonomy.on_halt(self, now)
            acct = await self.broker.account()

        if self.contracts is not None:
            await self.contracts.check_invalidations(self, acct, now, index)

        decisions: list[Decision] = []
        for sym, i in index.items():
            book = self.books[sym]
            price, atr = float(book.close[i]), float(book.atr[i])
            r = self.rankings.get(sym)
            tc = self.cfg.tournament
            due = r is None or book.ts[i] - r.at_ts >= tc.refit_every * self.cfg.bar_seconds - 1
            if i >= tc.window - 1 and due:
                prev_best = r.best.strategy if r and r.best else None
                r = self.rankings[sym] = rank(book, i, self.cfg.cost_bps[parse(sym).kind], tc)
                new_best = r.best.strategy if r.best else None
                if new_best != prev_best:
                    self.journal("tournament", jt.tournament(r), ts=now, symbol=sym,
                                 facts={"best": new_best, "previous": prev_best})  # fmt: skip
            pos = acct.positions.get(sym)
            if pos is not None and pos.stop_price is not None and price <= pos.stop_price:
                await self._exit(
                    sym, f"stop-loss at {pos.stop_price:,.2f} hit (close {price:,.2f})", now, stop=True
                )
                acct = await self.broker.account()
                continue
            view = MarketView(
                symbol=sym, kind=parse(sym).kind, ts=now, price=price, atr=atr, ranking=r,
                signals_now={k: float(v[i]) for k, v in book.signals.items()},
                signals_prev={k: float(v[i - 1]) for k, v in book.signals.items()} if i > 0 else {},
                position=pos, held_strategy=self.st["meta"].get(sym, {}).get("strategy"),
            )  # fmt: skip
            dec = await self.brain.decide(view)
            decisions.append(dec)
            self.last_decisions[sym] = dec.model_dump()
            self._journal_flags(sym, dec, now)
            if dec.action in ("hold", "stay_flat"):
                if dec.action == "stay_flat":
                    self.st["last_block"].pop(sym, None)
                    if dec.veto and self.st.setdefault("last_veto", {}).get(sym) != dec.strategy:
                        self.st["last_veto"][sym] = dec.strategy
                        self.journal("veto", jt.veto(dec), ts=now, symbol=sym,
                                     facts={"strategy": dec.strategy, "confidence": dec.confidence,
                                            "source": dec.source, **_desk(dec)})  # fmt: skip
                continue
            self.st.setdefault("last_veto", {}).pop(sym, None)
            if dec.action == "exit":
                if pos is not None:
                    await self._exit(sym, dec.reason, now)
                    acct = await self.broker.account()
                continue
            intent = OrderIntent(
                symbol=sym, action="enter_long", stop_price=round(price - self.cfg.stop_atr_mult * atr, 6),
                reason=dec.reason, strategy=dec.strategy, confidence=dec.confidence, source=dec.source,
            )  # fmt: skip
            verdict = self.kernel.review(
                intent, acct, self._ctx(sym, price, now, acct, data_age=now - book.ts[i])
            )
            if verdict.approved and dec.size_factor is not None and dec.size_factor < 1.0:
                # The desk asked for less. The kernel's own size is the ceiling; a request can only go under it.
                intent.requested_qty = _scaled(verdict.qty, dec.size_factor, parse(sym).kind)
                verdict = self.kernel.review(
                    intent, acct, self._ctx(sym, price, now, acct, data_age=now - book.ts[i])
                )
            if not verdict.approved:
                if verdict.blocked_by == "R12" and self.level == "SHADOW" and self.contracts is not None:
                    self.contracts.open_shadow(self, intent, verdict, dec, now)
                    continue
                if self.st["last_block"].get(sym) != verdict.blocked_by:
                    self.st["last_block"][sym] = verdict.blocked_by
                    self.journal("blocked", jt.blocked(intent, verdict), ts=now, symbol=sym,
                                 facts=_vfacts(intent, verdict))  # fmt: skip
                continue
            self.st["last_block"].pop(sym, None)
            if verdict.needs_approval:
                if not any(p["intent"]["symbol"] == sym for p in self.st["pending"]):
                    item = {"id": new_id("p-"), "created_at": now, "intent": intent.model_dump(),
                            "verdict": verdict.model_dump(), "decision": dec.model_dump()}  # fmt: skip
                    self.st["pending"].append(item)
                    self.journal("proposal", jt.proposal(intent, verdict) + (jt.reviewed(dec) if dec.desk else ""),
                                 ts=now, symbol=sym,
                                 facts={**_vfacts(intent, verdict), **_desk(dec)})  # fmt: skip
                    self.emit("pending", item=item)
                continue
            await self._submit_entry(intent, verdict, dec, now, acct)
            acct = await self.broker.account()
        self._save()
        self.emit("tick", now=now)
        return decisions

    # -------------------------------------------------------------- helpers
    def _ctx(self, sym: str, price: float, now: float, acct: AccountState, *, data_age: float) -> RiskContext:
        return RiskContext(
            now=now, price=price, kind=parse(sym).kind,
            day_start_equity=self.st["day_start_equity"] or acct.equity, killed=self.killed,
            halted=self.st["halted"], trades_today=self.st["trades_today"],
            last_stopout=self.st["last_stopout"].get(sym), bar_seconds=self.cfg.bar_seconds,
            data_age_seconds=max(0.0, data_age), max_data_age_seconds=self.cfg.max_data_age_seconds,
            autonomy=self.level, broker_is_paper=self.broker.is_paper,
        )  # fmt: skip

    async def _submit_entry(
        self, intent: OrderIntent, v: RiskVerdict, dec: Decision, now: float, acct: AccountState
    ) -> Order:
        contract = None
        if self.contracts is not None:
            contract = self.contracts.open(self, intent, v, dec, now)
            intent.contract_id = contract["id"]
        req = OrderRequest(symbol=intent.symbol, side="buy", qty=v.qty, stop_price=intent.stop_price,
                           reason=intent.reason[:200],
                           client_order_id=order_id(self.cfg.session, intent.symbol, now, "buy"))  # fmt: skip
        order = await self.broker.submit(req)
        self.ledger.save_order(order)
        if order.status == "rejected":
            self.journal("note", f"The broker rejected the {intent.symbol} buy: {order.error}.", ts=now,
                         symbol=intent.symbol)  # fmt: skip
            if contract is not None:
                self.contracts.cancel(self, contract, "the broker rejected the order", now)
            return order
        self.st["trades_today"] += 1
        self.st["meta"][intent.symbol] = {
            "strategy": intent.strategy, "contract_id": intent.contract_id, "entry_ts": now,
            "entry_price": v.price, "stop": intent.stop_price, "qty": v.qty, "source": intent.source,
            "confidence": intent.confidence, "bench_at_entry": self.benchmark_value,
        }  # fmt: skip
        facts = {**_vfacts(intent, v), "order_id": order.id, "contract_id": intent.contract_id,
                 "equity": round(acct.equity, 2), "expected_move_pct": dec.expected_move_pct,
                 "horizon_bars": dec.horizon_bars, **_desk(dec)}  # fmt: skip
        text = jt.entry(intent, v, dec, acct.equity)
        narrate = getattr(self.brain, "narrate", None)
        if narrate is not None and dec.source in ("llm", "desk"):
            plain, accepted, bad = await narrate(text, facts)
            facts["template"] = text
            facts["rewrite"] = "accepted" if accepted else ("discarded" if bad else "not used")
            if bad:
                facts["rewrite_unsupported"] = bad
            text = plain
        self.journal("entry", text, ts=now, symbol=intent.symbol, facts=facts)
        self.emit("order", order=order.model_dump())
        return order

    def _journal_flags(self, sym: str, dec: Decision, now: float) -> None:
        seen: list[str] = self.st.setdefault("flags_seen", [])
        for f in dec.flags:
            key = f"{sym}|{f}"
            if key in seen:
                continue
            seen.append(key)
            del seen[:-100]
            self.journal("flag", f, ts=now, symbol=sym, facts={"source": dec.source})

    def _remember_exit(self, sym: str, reason: str) -> None:
        self.st["meta"].setdefault(sym, {})["exit_reason"] = reason

    async def _exit(self, sym: str, reason: str, now: float, *, stop: bool = False) -> Order | None:
        self._remember_exit(sym, reason)
        if stop:
            self.st["last_stopout"][sym] = now
        order = await self.broker.close(sym, reason)
        if order is not None:
            self.ledger.save_order(order)
            self.emit("order", order=order.model_dump())
        return order

    def _on_fill(self, o: Order, now: float) -> None:
        self.ledger.save_order(o)
        self.emit("order", order=o.model_dump())
        if o.status == "rejected":
            self.journal(
                "note", f"Order {o.id} for {o.symbol} was rejected: {o.error}.", ts=now, symbol=o.symbol
            )
            return
        if o.side != "sell" or o.filled_qty <= 0:
            return
        meta = self.st["meta"].pop(o.symbol, {})
        reason = meta.get("exit_reason") or o.reason or "exit"
        if o.reason.startswith("stop-loss"):
            reason = o.reason
            self.st["last_stopout"][o.symbol] = now
        bench_ret = None
        if meta.get("bench_at_entry") and self.benchmark_value:
            bench_ret = self.benchmark_value / meta["bench_at_entry"] - 1
        entry_px = meta.get("entry_price")
        ret = (o.filled_avg_price / entry_px - 1) if entry_px and o.filled_avg_price else None
        facts = {
            "order_id": o.id, "qty": o.filled_qty, "exit_price": o.filled_avg_price, "entry_price": entry_px,
            "realized_pl": o.realized_pl, "return_pct": None if ret is None else round(100 * ret, 2),
            "benchmark_return_pct": None if bench_ret is None else round(100 * bench_ret, 2),
            "strategy": meta.get("strategy"), "reason": reason, "contract_id": meta.get("contract_id"),
            "held_seconds": None if meta.get("entry_ts") is None else now - meta["entry_ts"],
        }  # fmt: skip
        kind = "stop" if reason.startswith("stop-loss") else "exit"
        self.journal(kind, jt.exit_(o, facts), ts=now, symbol=o.symbol, facts=facts)
        if self.contracts is not None and meta.get("contract_id"):
            self.contracts.close(self, meta["contract_id"], facts, now)

    def status(self) -> dict:
        return {
            "session": self.cfg.session,
            "killed": self.killed,
            "halted": self.st["halted"],
            "autonomy": self.level,
            "day": self.st["day"],
            "day_start_equity": self.st["day_start_equity"],
            "trades_today": self.st["trades_today"],
            "pending": self.st["pending"],
            "positions_meta": self.st["meta"],
            "limits": self.kernel.limits.to_dict(),
            "rankings": {s: r.to_dict() for s, r in self.rankings.items()},
            "last_decisions": self.last_decisions,
        }


def _desk(dec: Decision) -> dict:
    return {"desk": dec.desk, "size_factor": dec.size_factor} if dec.desk else {}


def _scaled(qty: float, factor: float, kind: str) -> float:
    """A smaller size than the kernel's: whole shares for equities (never below one), six decimals for crypto."""
    if kind == "equity":
        return float(max(1, math.floor(qty * factor)))
    return max(1e-6, math.floor(qty * factor * 1e6) / 1e6)


def _vfacts(intent: OrderIntent, v: RiskVerdict) -> dict:
    return {
        "symbol": intent.symbol, "strategy": intent.strategy, "source": intent.source,
        "confidence": intent.confidence, "price": round(v.price, 6), "qty": v.qty, "stop_price": intent.stop_price,
        "notional": v.notional, "risk_amount": v.risk_amount, "blocked_by": v.blocked_by,
        "checks": [c.model_dump() for c in v.checks],
    }  # fmt: skip
