"""The Time Machine: the live engine replayed over history through a simulated broker.

It is the backtest. Same `Engine.step`, same kernel, same brain; only the broker (SimBroker, next-bar-open
fills with fees and slippage) and the clock (bar timestamps) differ. Decisions at bar t only ever see bars <= t.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from axiom.config import get_settings

from .brain import Brain, RuleBrain
from .broker.sim import SimBroker
from .contracts import ContractBook
from .engine import Engine, EngineConfig, utc_day
from .ledger import MemoryLedger
from .models import Autonomy, Bar, new_id
from .risk import RiskKernel, RiskLimits
from .strategies import SignalBook
from .symbols import parse
from .tournament import TournamentConfig


@dataclass
class ReplayResult:
    session: str
    engine: Engine
    broker: SimBroker
    ledger: MemoryLedger
    books: dict[str, SignalBook]
    start_ts: float
    end_ts: float
    start_cash: float


def infer_bar_seconds(df: pd.DataFrame) -> float:
    d = np.diff(pd.DatetimeIndex(df.index).as_unit("s").asi8)
    return float(np.median(d)) if len(d) else 86_400.0


def build_engine(
    symbols: list[str],
    *,
    session: str,
    broker,
    ledger,
    brain: Brain | None = None,
    autonomy: Autonomy = "AUTONOMOUS",
    bar_seconds: float = 86_400,
    periods_per_year: int = 252,
    contracts=None,
    ladder=None,
    kill_file=None,
) -> Engine:
    s = get_settings()
    syms = [parse(x) for x in symbols]
    kernel = RiskKernel(RiskLimits.from_settings(s, [x.name for x in syms]))
    cfg = EngineConfig(
        symbols=syms,
        session=session,
        bar_seconds=bar_seconds,
        max_data_age_seconds=bar_seconds * 3 + (3 * 86_400 if bar_seconds >= 86_400 else 0),
        stop_atr_mult=s.trader_stop_atr_mult,
        tournament=TournamentConfig(periods_per_year=periods_per_year),
        cost_bps={
            "crypto": s.trader_crypto_cost_bps + s.trader_slippage_bps,
            "equity": s.trader_equity_cost_bps + s.trader_slippage_bps,
        },
        autonomy=autonomy,
        kill_file=kill_file,
    )
    return Engine(cfg, broker, ledger, kernel, brain or RuleBrain(), contracts=contracts, autonomy=ladder)


def equal_weight_benchmark(
    books: dict[str, SignalBook], start_ts: float, cash: float
) -> Callable[[float], float]:
    """Buy-and-hold of every symbol in equal dollar amounts from `start_ts`, marked at the last close <= ts."""
    starts = {}
    for s, b in books.items():
        i = int(np.searchsorted(b.ts, start_ts))
        starts[s] = b.close[min(i, len(b) - 1)]

    def value(ts: float) -> float:
        rel = []
        for s, b in books.items():
            i = int(np.searchsorted(b.ts, ts, side="right")) - 1
            if i >= 0 and b.ts[i] >= start_ts:
                rel.append(b.close[i] / starts[s])
            else:
                rel.append(1.0)
        return cash * float(np.mean(rel))

    return value


async def run_replay(
    frames: dict[str, pd.DataFrame],
    *,
    brain: Brain | None = None,
    session: str | None = None,
    start_cash: float | None = None,
    warmup: int | None = None,
    autonomy: Autonomy = "AUTONOMOUS",
    on_progress: Callable[[int, int, float], None] | None = None,
    delay: float = 0.0,
    contracts=None,
    ladder=None,
    should_stop: Callable[[], bool] | None = None,
) -> ReplayResult:
    s = get_settings()
    start_cash = start_cash or s.trader_starting_cash
    session = session or f"replay:{new_id()}"
    books = {parse(k).name: SignalBook(parse(k).name, df) for k, df in frames.items()}
    any_df = next(iter(frames.values()))
    bar_seconds = infer_bar_seconds(any_df)
    crypto_only = all(parse(k).is_crypto for k in books)
    periods = 365 if crypto_only and bar_seconds >= 86_400 else 252
    if bar_seconds < 86_400:
        periods = int(
            round((365 if crypto_only else 252) * min(24 if crypto_only else 6.5, 86_400 / bar_seconds))
        )
    warm = warmup if warmup is not None else 252
    starts = [b.ts[min(warm, len(b) - 1)] for b in books.values()]
    start_ts = float(max(starts))
    broker = SimBroker(
        start_cash,
        fill="next_open",
        fee_bps={"crypto": s.trader_crypto_cost_bps, "equity": s.trader_equity_cost_bps},
        slippage_bps=s.trader_slippage_bps,
    )
    ledger = MemoryLedger(session)
    engine = build_engine(
        list(books), session=session, broker=broker, ledger=ledger, brain=brain, autonomy=autonomy,
        bar_seconds=bar_seconds, periods_per_year=periods,
        contracts=contracts if contracts is not None else ContractBook(), ladder=ladder,
    )  # fmt: skip
    engine.set_books(books)
    bench = equal_weight_benchmark(books, start_ts, start_cash)
    all_ts = np.unique(np.concatenate([b.ts for b in books.values()]))
    all_ts = all_ts[all_ts >= start_ts]
    n = len(all_ts)
    for k, ts in enumerate(all_ts):
        if should_stop and should_stop():
            break
        ts = float(ts)
        if engine.st["day"] != utc_day(ts):
            await engine.roll_day(ts)
        index: dict[str, int] = {}
        for sym, b in books.items():
            i = b.index_at(ts)
            if i is None:
                continue
            row = b.df.iloc[i]
            broker.on_bar(sym, Bar(ts=ts, open=row.open, high=row.high, low=row.low, close=row.close))
            index[sym] = i
        engine.benchmark_value = bench(ts)
        await engine.step(ts, index)
        if on_progress:
            on_progress(k + 1, n, ts)
        if delay:
            await asyncio.sleep(delay)
    end_ts = float(all_ts[-1]) if n else start_ts
    return ReplayResult(session, engine, broker, ledger, books, start_ts, end_ts, start_cash)
