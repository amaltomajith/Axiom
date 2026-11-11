"""Walk-forward strategy tournament: "picks or adapts a strategy".

Every `refit_every` bars, each strategy is scored on the trailing `window` bars of one symbol, net of costs,
against buy-and-hold over the same bars. Only strategies that clear the gate may open trades; if none do, the
agent stays in cash for that symbol. Uses only bars <= t, so a ranking can never see the future.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from axiom.quant.backtest import apply_strategy, sharpe_ratio
from axiom.quant.regime import classify

from .strategies import TRADING_STRATEGIES, SignalBook


@dataclass(frozen=True)
class TournamentConfig:
    window: int = 252
    refit_every: int = 21
    min_sharpe: float = 0.5  # annualised, net of costs
    max_drawdown: float = -0.30
    min_trades: int = 2
    periods_per_year: int = 252


@dataclass
class Standing:
    strategy: str
    sharpe: float
    total_return: float
    max_drawdown: float
    trades: int
    qualified: bool
    why: str


@dataclass
class Ranking:
    symbol: str
    at_index: int
    at_ts: float
    benchmark_sharpe: float
    benchmark_return: float
    regime: dict
    standings: list[Standing] = field(default_factory=list)

    @property
    def qualified(self) -> list[Standing]:
        return [s for s in self.standings if s.qualified]

    @property
    def best(self) -> Standing | None:
        q = self.qualified
        return q[0] if q else None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "at_ts": self.at_ts,
            "benchmark_sharpe": round(self.benchmark_sharpe, 3),
            "benchmark_return": round(self.benchmark_return, 4),
            "regime": self.regime,
            "standings": [
                {**s.__dict__, "sharpe": round(s.sharpe, 3), "total_return": round(s.total_return, 4),
                 "max_drawdown": round(s.max_drawdown, 4)}
                for s in self.standings
            ],
        }  # fmt: skip


def _scaled_sharpe(r: np.ndarray, periods_per_year: int) -> float:
    return sharpe_ratio(r) * np.sqrt(periods_per_year / 252)  # sharpe_ratio annualises with 252


def rank(book: SignalBook, t: int, cost_bps: float, cfg: TournamentConfig) -> Ranking:
    """Score every strategy on bars (t - window, t]. Requires t >= window."""
    lo = max(0, t - cfg.window + 1)
    close = pd.Series(book.close[lo : t + 1])
    bench = apply_strategy(close, pd.Series(1.0, index=close.index), cost_bps / 2, cost_bps / 2).to_numpy()
    b_eq = np.cumprod(1 + bench)
    out = Ranking(
        symbol=book.symbol,
        at_index=t,
        at_ts=float(book.ts[t]),
        benchmark_sharpe=_scaled_sharpe(bench, cfg.periods_per_year),
        benchmark_return=float(b_eq[-1] - 1),
        regime=classify(close),
    )
    for name in TRADING_STRATEGIES:
        pos = pd.Series(book.signals[name][lo : t + 1])
        r = apply_strategy(close, pos, cost_bps / 2, cost_bps / 2).to_numpy()
        eq = np.cumprod(1 + r)
        dd = float((eq / np.maximum.accumulate(eq) - 1).min())
        trades = int((np.diff(np.concatenate([[0.0], pos.to_numpy()])) > 0).sum())
        sh = _scaled_sharpe(r, cfg.periods_per_year)
        reasons = []
        if sh < cfg.min_sharpe:
            reasons.append(f"Sharpe {sh:.2f} < {cfg.min_sharpe}")
        if dd < cfg.max_drawdown:
            reasons.append(f"drawdown {dd:.0%} worse than {cfg.max_drawdown:.0%}")
        if trades < cfg.min_trades:
            reasons.append(f"{trades} trades < {cfg.min_trades}")
        if eq[-1] <= 1:
            reasons.append("lost money")
        out.standings.append(
            Standing(name, sh, float(eq[-1] - 1), dd, trades, not reasons, "; ".join(reasons) or "qualified")
        )
    out.standings.sort(key=lambda s: (s.qualified, s.sharpe), reverse=True)
    return out
