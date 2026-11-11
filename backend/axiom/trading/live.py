"""The live loop: fetch bars, rebuild signals when a bar completes, let the engine decide, repeat.

A watchdog guards the loop: three failed or hung ticks in a row halt new entries and flatten every position,
because an agent that cannot see the market must not keep risk on. The heartbeat is stored so the UI (and the
CLI) can tell a live agent from a dead one.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

import numpy as np
import pandas as pd

from axiom.config import get_settings
from axiom.data import market

from . import alerts
from .autonomy import AutonomyLadder
from .brain import Brain, RuleBrain
from .broker.alpaca import AlpacaPaperBroker
from .broker.base import Broker, BrokerError
from .broker.sim import SimBroker
from .contracts import ContractBook, outcomes_text
from .data import TIMEFRAME_SECONDS, fetch_intraday
from .engine import KILL_FILE, Engine
from .ledger import StoreLedger
from .replay import build_engine
from .strategies import SignalBook, bar_times
from .symbols import Symbol, parse_list

log = logging.getLogger("axiom.trader")
Fetcher = Callable[[Symbol], Awaitable[pd.DataFrame]]
WATCHDOG_FAILURES = 3
BARS = 400


def periods_per_year(symbols: list[Symbol], bar_seconds: float) -> int:
    crypto = all(s.is_crypto for s in symbols)
    if bar_seconds >= 86_400:
        return 365 if crypto else 252
    hours = 24 if crypto else 6.5
    return int(round((365 if crypto else 252) * hours * 3600 / bar_seconds))


def make_brain(kind: str, *, bar_seconds: float = 3600.0) -> Brain:
    if kind == "desk":
        from .desk import DeskBrain

        return DeskBrain.from_settings(bar_seconds=bar_seconds)
    if kind == "llm":
        from .llm_brain import LLMBrain

        return LLMBrain.from_settings()
    return RuleBrain()


class Trader:
    def __init__(
        self,
        engine: Engine,
        broker: Broker,
        symbols: list[Symbol],
        fetch: Fetcher,
        *,
        timeframe: str,
        interval: float,
    ):
        self.engine = engine
        self.broker = broker
        self.symbols = symbols
        self.fetch = fetch
        self.timeframe = timeframe
        self.interval = interval
        self.failures = 0
        self.last_tick: float | None = None
        self.last_error: str | None = None
        self.symbol_errors: dict[str, str] = {}
        self.alerts: dict[str, dict] = {}  # symbol -> the latest alert, with its bar time
        self.running = False
        self._stop = asyncio.Event()
        self.task: asyncio.Task | None = None

    # ------------------------------------------------------------ factory
    @classmethod
    def from_settings(cls, store=None, *, brain: Brain | None = None, fetch: Fetcher | None = None) -> Trader:
        from axiom.memory.store import get_store

        s = get_settings()
        symbols = parse_list(s.trader_symbols)
        tf = s.trader_timeframe if s.trader_timeframe in TIMEFRAME_SECONDS else "1Hour"
        keys = (s.alpaca_api_key, s.alpaca_secret_key)
        if s.trader_broker == "alpaca":
            if not all(keys):
                raise BrokerError(
                    "TRADER_BROKER=alpaca needs ALPACA_API_KEY and ALPACA_SECRET_KEY (paper keys)."
                )
            broker: Broker = AlpacaPaperBroker(*keys)  # type: ignore[arg-type]
        else:
            broker = SimBroker(
                s.trader_starting_cash, fill="immediate",
                fee_bps={"crypto": s.trader_crypto_cost_bps, "equity": s.trader_equity_cost_bps},
                slippage_bps=s.trader_slippage_bps,
            )  # fmt: skip
        if not all(keys) and tf != "1Day":
            dropped = [x.name for x in symbols if not x.is_crypto]
            symbols = [x for x in symbols if x.is_crypto]
            if dropped:
                log.warning(
                    "No Alpaca keys: intraday equity bars unavailable, trading crypto only (%s)", dropped
                )
        bar_s = TIMEFRAME_SECONDS[tf]
        ledger = StoreLedger(store or get_store(), "live")
        engine = build_engine(
            [x.name for x in symbols], session="live", broker=broker, ledger=ledger,
            brain=brain or make_brain(s.trader_brain, bar_seconds=bar_s), autonomy=s.trader_autonomy_start,  # type: ignore[arg-type]
            bar_seconds=bar_s, periods_per_year=periods_per_year(symbols, bar_s), kill_file=KILL_FILE,
            contracts=ContractBook(), ladder=AutonomyLadder(),
        )  # fmt: skip
        if getattr(engine.brain, "name", "") == "desk" and engine.brain.memory is None:
            # the desk's long-term memory: how its graded paper trades ended, by regime and strategy
            engine.brain.memory = lambda _symbol: outcomes_text(ledger.contracts())
        if getattr(engine.brain, "name", "") == "desk" and engine.brain.sink is None:
            engine.brain.sink = ledger.save_review  # every review's full transcript, kept across restarts
        if fetch is None:
            if tf == "1Day":

                async def fetch(sym: Symbol) -> pd.DataFrame:
                    df, _ = await market.fetch_ohlcv(sym.yahoo, BARS)
                    return df
            else:

                async def fetch(sym: Symbol) -> pd.DataFrame:
                    return await fetch_intraday(sym, tf, BARS, key=keys[0], secret=keys[1])

        return cls(engine, broker, symbols, fetch, timeframe=tf, interval=max(5, s.trader_interval_seconds))

    # -------------------------------------------------------------- start
    async def start(self) -> None:
        eng = self.engine
        now = time.time()
        if isinstance(self.broker, SimBroker):
            # A fresh simulated account each process start: forget positions it cannot have.
            eng.st["meta"], eng.st["pending"] = {}, []
        notes: list[str] = []
        if isinstance(self.broker, AlpacaPaperBroker):
            pre = await self.broker.preflight()
            if pre["trading_blocked"] or pre["account_blocked"]:
                raise BrokerError(f"The Alpaca paper account cannot trade: {pre}")
            notes = await self.broker.reconcile(eng.st["meta"])
        acct = await self.broker.account()
        eng.journal(
            "note",
            f"Autopilot started on the {self.broker.name} paper broker: {len(self.symbols)} symbols "
            f"({', '.join(x.name for x in self.symbols)}), {self.timeframe} bars, autonomy {eng.level}. "
            f"Equity {acct.equity:,.2f}." + (f" Reconciled: {'; '.join(notes)}." if notes else ""),
            ts=now,
            facts={"broker": self.broker.name, "equity": acct.equity, "timeframe": self.timeframe},
        )
        eng._save()

    # --------------------------------------------------------------- tick
    async def tick(self, now: float | None = None) -> dict:
        now = now or time.time()
        eng = self.engine
        eng.ledger.set_state("heartbeat", now)
        books = dict(eng.books)
        for sym in self.symbols:
            try:
                df = await self.fetch(sym)
                if df is None or len(df) < 30:
                    raise market.DataError(f"only {0 if df is None else len(df)} bars")
                old = books.get(sym.name)
                if old is None or old.ts[-1] != bar_times(df.index[-1:])[-1] or len(old) != len(df):
                    books[sym.name] = SignalBook(sym.name, df)
                self.symbol_errors.pop(sym.name, None)
            except Exception as e:
                self.symbol_errors[sym.name] = f"{type(e).__name__}: {e}"[:200]
        eng.set_books(books)
        if not books:
            raise market.DataError("no market data for any symbol")

        for name, b in books.items():  # mark prices so equity, stops and the daily loss use fresh data
            if isinstance(self.broker, SimBroker):
                self.broker.set_price(name, float(b.close[-1]), now)
        self._benchmark(books)

        decided: dict[str, float] = eng.ledger.get_state("last_decided") or {}
        index: dict[str, int] = {}
        for name, b in books.items():
            last_ts = float(b.ts[-1])
            if decided.get(name) == last_ts:
                continue  # one decision per completed bar
            if isinstance(self.broker, AlpacaPaperBroker) and not name.count("/"):
                if not await self.broker.market_open():
                    continue  # equities only decide while the market is open; stops stay at the broker
            index[name] = len(b) - 1
            decided[name] = last_ts
            self._alert(name, b, last_ts, now)
        decisions = await eng.step(now, index)
        for d in decisions:
            if d.reviewing:
                decided.pop(d.symbol, None)  # the desk is not done: decide this bar again on the next tick
        eng.ledger.set_state("last_decided", decided)
        self.last_tick = now
        return {"decided": list(index), "decisions": [d.model_dump() for d in decisions]}

    def _alert(self, name: str, book: SignalBook, bar_ts: float, now: float) -> None:
        """A volume or range spike on the bar that just closed: journal it once and force a fresh desk review."""
        a = alerts.detect(book.df)
        if a is None or self.alerts.get(name, {}).get("bar_ts") == bar_ts:
            return
        self.alerts[name] = {**a, "bar_ts": bar_ts, "ts": now}
        job = getattr(self.engine.brain, "jobs", {}).pop(name, None)
        if job is not None:
            job.task.cancel()
        self.engine.journal("note", alerts.describe(name, a), ts=now, symbol=name, facts={"alert": a})
        brain = self.engine.brain
        if hasattr(brain, "review_now"):
            if self.engine.eligible(name):
                brain.next_trigger[name] = "alert"  # a strategy wants in: the loop's own review runs this bar
            else:
                try:
                    self.engine.start_review(name, trigger="alert")
                except ValueError:  # the hourly cap, or a review already running
                    pass
        self.engine.emit("state")

    def _benchmark(self, books: dict[str, SignalBook]) -> None:
        led = self.engine.ledger
        start = led.get_state("bench_start")
        if not start or set(start.get("prices", {})) != set(books):
            eq = self.engine.st.get("day_start_equity") or get_settings().trader_starting_cash
            start = {"cash": eq, "prices": {n: float(b.close[-1]) for n, b in books.items()}}
            led.set_state("bench_start", start)
        rel = [float(b.close[-1]) / start["prices"][n] for n, b in books.items() if start["prices"].get(n)]
        self.engine.benchmark_value = start["cash"] * float(np.mean(rel)) if rel else None

    # ----------------------------------------------------------- watchdog
    async def _watchdog_trip(self, why: str) -> None:
        eng = self.engine
        if eng.st["halted"]:
            return
        eng.st["halted"] = f"watchdog: {why}"
        try:
            orders = await self.broker.flatten_all("watchdog")
        except Exception as e:  # the broker may be the thing that is down
            orders = []
            why += f"; flatten failed: {e}"
        eng.journal("halt", f"Watchdog tripped: {why}. Halted new entries and closed {len(orders)} position(s).",
                    ts=time.time(), facts={"why": why, "closed": len(orders)})  # fmt: skip
        eng._save()

    async def run_forever(self) -> None:
        self.running = True
        self._stop.clear()
        try:
            await self.start()
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(self.tick(), timeout=max(30.0, 3 * self.interval))
                    self.failures, self.last_error = 0, None
                except Exception as e:
                    self.failures += 1
                    self.last_error = f"{type(e).__name__}: {e}"[:300]
                    log.warning("tick failed (%d): %s", self.failures, self.last_error)
                    if self.failures == WATCHDOG_FAILURES:
                        await self._watchdog_trip(
                            f"{WATCHDOG_FAILURES} failed ticks in a row ({self.last_error})"
                        )
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
                except TimeoutError:
                    pass
        finally:
            self.running = False

    def launch(self) -> asyncio.Task:
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run_forever())
        return self.task

    async def stop(self) -> None:
        self._stop.set()
        if self.task is not None:
            try:
                await asyncio.wait_for(self.task, timeout=10)
            except (TimeoutError, asyncio.CancelledError):
                self.task.cancel()

    def status(self) -> dict:
        hb = self.engine.ledger.get_state("heartbeat")
        return {
            **self.engine.status(),
            "running": self.running,
            "broker": self.broker.name,
            "brain": self.engine.brain.name,
            "timeframe": self.timeframe,
            "interval_seconds": self.interval,
            "symbols": [x.name for x in self.symbols],
            "heartbeat": hb,
            "heartbeat_age_seconds": None if hb is None else round(time.time() - hb, 1),
            "failures": self.failures,
            "last_error": self.last_error,
            "broker_warning": getattr(self.broker, "stop_error", None),
            "symbol_errors": self.symbol_errors,
            "alerts": self.alerts,
            "benchmark_value": self.engine.benchmark_value,
        }
