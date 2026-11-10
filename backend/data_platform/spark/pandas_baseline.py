"""The same indicators computed the way the app does: Axiom's own functions, one series at a time, in pandas."""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from axiom.quant.indicators import realized_vol, rsi, sma

COLUMNS = ["sma20", "sma50", "sma200", "vol20", "rsi14"]


def indicators(df: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for name, g in df.sort_values(["series", "date"]).groupby("series", sort=False):
        c = g["close"].reset_index(drop=True)
        parts.append(
            pd.DataFrame(
                {
                    "series": name,
                    "date": g["date"].to_numpy(),
                    "close": c,
                    "sma20": sma(c, 20),
                    "sma50": sma(c, 50),
                    "sma200": sma(c, 200),
                    "vol20": realized_vol(c, 20),
                    "rsi14": rsi(c, 14),
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


def run(inp: Path, out: Path) -> dict[str, float]:
    t0 = time.perf_counter()
    df = pd.read_parquet(inp)
    t1 = time.perf_counter()
    res = indicators(df)
    t2 = time.perf_counter()
    res.to_parquet(out, index=False)
    t3 = time.perf_counter()
    return {
        "rows_out": len(res),
        "seconds_read": round(t1 - t0, 3),
        "seconds_compute": round(t2 - t1, 3),
        "seconds_write": round(t3 - t2, 3),
        "seconds_total": round(t3 - t0, 3),
    }
