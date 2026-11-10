"""PySpark job: SMA 20/50/200, 20-day annualised volatility and Wilder RSI 14 per series.

    spark-submit indicators_job.py <input.parquet> <output dir> <metrics.json>

Runs inside the Spark container and deliberately does not import Axiom: it is an independent implementation,
compared against axiom/quant/indicators.py by bench.py. Definitions match Axiom's:
- SMA(n): mean of the last n closes, NULL until n closes exist.
- vol20: sample std (ddof 1) of the last 20 daily log returns x sqrt(252), NULL until 20 returns exist.
- RSI14: Wilder smoothing seeded with the simple mean of the first 14 gains/losses; first value at row 14.
SMA and volatility are window functions. Wilder's RSI is recursive, so it runs per series in applyInPandas.
"""

from __future__ import annotations

import json
import math
import sys
import time

import numpy as np
import pandas as pd

RSI_PERIOD = 14
TRADING_DAYS = 252


def wilder_rsi_values(close: np.ndarray, period: int = RSI_PERIOD) -> np.ndarray:
    out = np.full(len(close), np.nan)
    delta = np.diff(close)
    if len(delta) < period:
        return out
    gains, losses = np.maximum(delta, 0.0), np.maximum(-delta, 0.0)

    def value(g: float, lo: float) -> float:
        if lo == 0:
            return 100.0 if g > 0 else 50.0
        return 100.0 - 100.0 / (1.0 + g / lo)

    g, lo = gains[:period].mean(), losses[:period].mean()
    out[period] = value(g, lo)
    for i in range(period, len(delta)):
        g = (g * (period - 1) + gains[i]) / period
        lo = (lo * (period - 1) + losses[i]) / period
        out[i + 1] = value(g, lo)
    return out


def _rsi_group(pdf: pd.DataFrame) -> pd.DataFrame:
    pdf = pdf.sort_values("date")
    return pd.DataFrame(
        {
            "series": pdf["series"].to_numpy(),
            "date": pdf["date"].to_numpy(),
            "rsi14": wilder_rsi_values(pdf["close"].to_numpy(dtype=float)),
        }
    )


def main(inp: str, out: str, metrics_path: str) -> None:
    from pyspark.sql import SparkSession, Window
    from pyspark.sql import functions as F

    t0 = time.perf_counter()
    spark = SparkSession.builder.appName("axiom-indicators").getOrCreate()
    t1 = time.perf_counter()

    df = spark.read.parquet(inp)
    w = Window.partitionBy("series").orderBy("date")

    def last(n: int):
        return w.rowsBetween(-(n - 1), Window.currentRow)

    def sma(n: int):
        return F.when(F.count("close").over(last(n)) == n, F.avg("close").over(last(n)))

    with_ret = df.withColumn("lr", F.log(F.col("close") / F.lag("close").over(w)))
    vol = F.when(
        F.count("lr").over(last(20)) == 20, F.stddev_samp("lr").over(last(20)) * math.sqrt(TRADING_DAYS)
    )
    windowed = with_ret.select(
        "series",
        "date",
        "close",
        sma(20).alias("sma20"),
        sma(50).alias("sma50"),
        sma(200).alias("sma200"),
        vol.alias("vol20"),
    )
    rsi = (
        df.select("series", "date", "close")
        .groupBy("series")
        .applyInPandas(_rsi_group, schema="series string, date date, rsi14 double")
    )
    result = windowed.join(rsi, ["series", "date"])
    result.write.mode("overwrite").parquet(out)
    t2 = time.perf_counter()

    rows = spark.read.parquet(out).count()
    metrics = {
        "spark_version": spark.version,
        "default_parallelism": spark.sparkContext.defaultParallelism,
        "rows_out": rows,
        "seconds_session_start": round(t1 - t0, 3),
        "seconds_compute_and_write": round(t2 - t1, 3),
    }
    with open(metrics_path, "w") as f:
        json.dump(metrics, f)
    spark.stop()


if __name__ == "__main__":
    main(*sys.argv[1:4])
