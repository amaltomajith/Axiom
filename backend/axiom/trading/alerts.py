"""Watchlist alerts: a completed bar that is unusual enough to deserve a fresh look.

Two plain checks on the bar that just closed, against the bars before it:
  * volume at least `VOLUME_X` times the average of the previous 20 bars;
  * a range (true range) at least `RANGE_X` times the 14-bar ATR as it stood before this bar.

An alert never trades by itself. The live loop journals it and drops any desk review it had cached for
that symbol, so if a strategy wants to buy on this bar the four agents review it afresh.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from axiom.quant import indicators as ind

VOLUME_X = 2.5
RANGE_X = 2.5
BASE = 20


def detect(df: pd.DataFrame) -> dict[str, Any] | None:
    """The alert on the last bar of `df`, or None. Uses only that bar and the ones before it."""
    if len(df) < BASE + 15:
        return None
    last, prev = df.iloc[-1], df.iloc[:-1]
    out: dict[str, Any] = {}
    base_vol = float(prev["volume"].tail(BASE).mean())
    if base_vol > 0 and float(last["volume"]) >= VOLUME_X * base_vol:
        out["volume_x"] = round(float(last["volume"]) / base_vol, 1)
    atr = float(ind.atr(prev["high"], prev["low"], prev["close"]).iloc[-1])
    prev_close = float(prev["close"].iloc[-1])
    true_range = max(float(last["high"]) - float(last["low"]), abs(float(last["high"]) - prev_close),
                     abs(float(last["low"]) - prev_close))  # fmt: skip
    if atr > 0 and true_range >= RANGE_X * atr:
        out["range_x"] = round(true_range / atr, 1)
    if not out:
        return None
    move = 100 * (float(last["close"]) / prev_close - 1) if prev_close else 0.0
    return {**out, "move_pct": round(move, 2), "close": round(float(last["close"]), 6)}


def describe(symbol: str, a: dict[str, Any]) -> str:
    parts = []
    if "volume_x" in a:
        parts.append(f"volume was {a['volume_x']} times its {BASE}-bar average")
    if "range_x" in a:
        parts.append(f"the bar's range was {a['range_x']} times its usual size")
    return (
        f"Alert on {symbol}: {' and '.join(parts)}, with the price {a['move_pct']:+.2f}% on the bar. "
        "An alert does not trade. Any saved desk review for this symbol was dropped, so a new idea here is "
        "reviewed afresh."
    )
