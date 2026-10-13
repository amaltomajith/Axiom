"""Plain-statistics market regime classification (no learned parameters)."""

from __future__ import annotations

from typing import Literal

import pandas as pd

from .indicators import realized_vol, sma

Trend = Literal["uptrend", "downtrend", "sideways", "insufficient_data"]
Vol = Literal["low", "normal", "high", "insufficient_data"]


def classify(close: pd.Series) -> dict[str, object]:
    """Trend: price vs SMA50 and SMA50 slope. Vol: current 20d vol percentile vs its own history."""
    trend: Trend = "insufficient_data"
    if len(close) >= 70:
        s50 = sma(close, 50)
        slope = (s50.iloc[-1] / s50.iloc[-11] - 1) if pd.notna(s50.iloc[-11]) else 0.0
        above = close.iloc[-1] > s50.iloc[-1]
        if above and slope > 0.005:
            trend = "uptrend"
        elif not above and slope < -0.005:
            trend = "downtrend"
        else:
            trend = "sideways"

    vol: Vol = "insufficient_data"
    pct = None
    rv = realized_vol(close).dropna()
    if len(rv) >= 60:
        pct = float((rv < rv.iloc[-1]).mean())
        vol = "high" if pct > 0.8 else "low" if pct < 0.2 else "normal"
    return {
        "trend": trend,
        "volatility": vol,
        "vol_percentile": None if pct is None else round(pct, 2),
        "current_vol_annualized": None if rv.empty else round(float(rv.iloc[-1]), 4),
    }
