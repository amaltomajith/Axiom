"""The strategies the agent may trade, and a `SignalBook` that precomputes them for one symbol.

Every strategy is causal: its value at bar t uses bars <= t only. `tests/test_trading_engine.py` proves it by
truncation (the signal at t is identical whether or not later bars exist). That property is what lets the
engine compute signals once over a series and read them bar by bar without look-ahead.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from axiom.quant import indicators as ind
from axiom.quant.backtest import macd_trend, rsi_reversion, sma_cross

StrategyFn = Callable[[pd.DataFrame], pd.Series]


def donchian_breakout(df: pd.DataFrame, entry: int = 20, exit_: int = 10) -> pd.Series:
    """Long after a close above the prior `entry`-bar high; flat after a close below the prior `exit_`-bar low."""
    hi = df["high"].rolling(entry).max().shift(1)
    lo = df["low"].rolling(exit_).min().shift(1)
    close = df["close"].to_numpy()
    up, down = (df["close"] > hi).to_numpy(), (df["close"] < lo).to_numpy()
    pos = np.zeros(len(df))
    holding = False
    for i in range(len(df)):
        if holding and down[i]:
            holding = False
        elif not holding and up[i] and not np.isnan(close[i]):
            holding = True
        pos[i] = 1.0 if holding else 0.0
    return pd.Series(pos, index=df.index)


def bollinger_reversion(df: pd.DataFrame) -> pd.Series:
    """Long after a close below the lower band; flat once the close is back above the middle band."""
    b = ind.bollinger(df["close"])
    close = df["close"].to_numpy()
    lower, mid = b["lower"].to_numpy(), b["mid"].to_numpy()
    pos = np.zeros(len(df))
    holding = False
    for i in range(len(df)):
        if np.isnan(lower[i]):
            holding = False
        elif holding and close[i] > mid[i]:
            holding = False
        elif not holding and close[i] < lower[i]:
            holding = True
        pos[i] = 1.0 if holding else 0.0
    return pd.Series(pos, index=df.index)


TRADING_STRATEGIES: dict[str, StrategyFn] = {
    "sma_cross": sma_cross,
    "macd_trend": macd_trend,
    "rsi_reversion": rsi_reversion,
    "donchian_breakout": donchian_breakout,
    "bollinger_reversion": bollinger_reversion,
}

DESCRIPTIONS = {
    "sma_cross": "trend following: long while the 20-bar average is above the 50-bar average",
    "macd_trend": "momentum: long while MACD is above its signal line",
    "rsi_reversion": "mean reversion: buy when RSI(14) drops below 30, sell when it recovers above 55",
    "donchian_breakout": "breakout: buy a close above the 20-bar high, sell a close below the 10-bar low",
    "bollinger_reversion": "mean reversion: buy a close below the lower Bollinger band, sell above the middle",
}


@dataclass
class SignalBook:
    """Every strategy's position series plus ATR for one symbol, aligned to its bars."""

    symbol: str
    df: pd.DataFrame
    ts: np.ndarray = field(init=False)  # bar close times, unix seconds
    close: np.ndarray = field(init=False)
    atr: np.ndarray = field(init=False)
    signals: dict[str, np.ndarray] = field(init=False)

    def __post_init__(self) -> None:
        df = self.df
        self.ts = bar_times(df.index)
        self.close = df["close"].to_numpy(dtype=float)
        self.atr = ind.atr(df["high"], df["low"], df["close"]).to_numpy(dtype=float)
        self.signals = {n: fn(df).to_numpy(dtype=float) for n, fn in TRADING_STRATEGIES.items()}

    def __len__(self) -> int:
        return len(self.close)

    def index_at(self, ts: float) -> int | None:
        """Position of the bar that closes exactly at `ts`, if any."""
        i = int(np.searchsorted(self.ts, ts))
        return i if i < len(self.ts) and self.ts[i] == ts else None


def bar_times(index: pd.DatetimeIndex) -> np.ndarray:
    """Unix close time of each bar. Daily bars (midnight timestamps) close at 23:59:59 UTC of their date, so a
    crypto bar and an equity bar of the same day share one timestamp; intraday bars keep their own."""
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    secs = idx.as_unit("s").asi8  # pandas 3 may store us or ns: convert explicitly
    daily = bool(len(idx)) and bool((idx.normalize() == idx).all())
    return (secs + 86_399 if daily else secs).astype(float)
