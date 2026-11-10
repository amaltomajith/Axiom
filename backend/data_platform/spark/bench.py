"""Correctness check and pandas-vs-PySpark timing.

    python -m data_platform.spark.bench [--sizes 1000,4000] [--cpus 8] [--memory 6g] [--repeats 2]

1. Downloads the H.10 exchange rates (public domain, see fx_data.py) and builds synthetic GBM sets for scale.
2. For each dataset: runs Axiom's pandas indicators on the host, and the PySpark job in Docker
   (local mode, CPU and memory limited by `docker run`). Wall time includes JVM start-up.
3. Compares Spark's output with Axiom's, column by column: max abs difference and identical NULL positions.
Writes backend/.cache/spark/bench.json and prints it.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .. import BACKEND_DIR
from . import fx_data, pandas_baseline

IMAGE = "axiom-spark:4.1.4"
JOB_DIR = Path(__file__).resolve().parent
WORK = BACKEND_DIR / ".cache" / "spark"
N_DAYS = 2520  # ten years of business days per synthetic series


def build_image() -> None:
    subprocess.run(["docker", "build", "-q", "-t", IMAGE, str(JOB_DIR)], check=True, capture_output=True)


def run_spark(name: str, cpus: int, memory: str) -> dict:
    out, metrics = f"/data/{name}_spark", f"/data/{name}_spark_metrics.json"
    cmd = [
        "docker", "run", "--rm", "--user", "root",  # Spark chmods its output; Windows bind mounts refuse non-root
        f"--cpus={cpus}", f"--memory={memory}",
        "-v", f"{WORK.as_posix()}:/data", "-v", f"{JOB_DIR.as_posix()}:/job:ro",
        IMAGE, "/opt/spark/bin/spark-submit", "--master", f"local[{cpus}]",
        "--driver-memory", "4g", "--conf", f"spark.sql.shuffle.partitions={cpus * 2}",
        "--conf", "spark.ui.enabled=false",
        "/job/indicators_job.py", f"/data/{name}.parquet", out, metrics,
    ]  # fmt: skip
    t0 = time.perf_counter()
    subprocess.run(cmd, check=True, capture_output=True)
    wall = time.perf_counter() - t0
    m = json.loads((WORK / f"{name}_spark_metrics.json").read_text())
    return {**m, "seconds_container_wall": round(wall, 3)}


def compare(name: str) -> dict:
    """Spark vs Axiom on every row: max abs diff per column and whether NULLs sit in the same places."""
    key = ["series", "date"]
    a = pd.read_parquet(WORK / f"{name}_pandas.parquet").sort_values(key, ignore_index=True)
    b = pd.read_parquet(WORK / f"{name}_spark").sort_values(key, ignore_index=True)
    a["date"], b["date"] = pd.to_datetime(a["date"]), pd.to_datetime(b["date"])
    assert len(a) == len(b) and (a[key].to_numpy() == b[key].to_numpy()).all(), "row sets differ"
    out = {"rows_compared": len(a)}
    for col in pandas_baseline.COLUMNS:
        x, y = a[col].to_numpy(dtype=float), b[col].to_numpy(dtype=float)
        same_nulls = bool((np.isnan(x) == np.isnan(y)).all())
        both = ~np.isnan(x) & ~np.isnan(y)
        out[col] = {
            "max_abs_diff": float(np.abs(x[both] - y[both]).max()) if both.any() else 0.0,
            "max_rel_diff": float((np.abs(x[both] - y[both]) / np.maximum(np.abs(x[both]), 1e-300)).max())
            if both.any()
            else 0.0,
            "same_null_positions": same_nulls,
            "non_null": int(both.sum()),
        }
    return out


def prepare(sizes: list[int]) -> dict[str, int]:
    WORK.mkdir(parents=True, exist_ok=True)
    sets = {"h10": fx_data.download_h10(WORK / "h10_pages")}
    for n in sizes:
        sets[f"syn{n}"] = fx_data.synthetic(n, N_DAYS)
    for name, df in sets.items():
        df.to_parquet(WORK / f"{name}.parquet", index=False)
    return {name: len(df) for name, df in sets.items()}


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m data_platform.spark.bench")
    ap.add_argument("--sizes", default="1000,4000", help="synthetic series counts (x 2520 days each)")
    ap.add_argument("--cpus", type=int, default=8)
    ap.add_argument("--memory", default="6g")
    ap.add_argument("--repeats", type=int, default=2, help="timed runs per engine; the best is reported")
    a = ap.parse_args()

    build_image()
    rows = prepare([int(s) for s in a.sizes.split(",") if s])
    report = {
        "machine": {
            "host": platform.processor() or platform.machine(),
            "host_logical_cpus": os.cpu_count(),
            "docker_limits": {"cpus": a.cpus, "memory": a.memory},
            "pandas": pd.__version__,
            "image": IMAGE,
        },
        "datasets": {},
    }
    for name, n in rows.items():
        pandas_runs = [
            pandas_baseline.run(WORK / f"{name}.parquet", WORK / f"{name}_pandas.parquet")
            for _ in range(a.repeats)
        ]
        spark_runs = [run_spark(name, a.cpus, a.memory) for _ in range(a.repeats)]
        series = int(pd.read_parquet(WORK / f"{name}.parquet", columns=["series"])["series"].nunique())
        report["datasets"][name] = {
            "rows": n,
            "series": series,
            "pandas_best": min(pandas_runs, key=lambda r: r["seconds_total"]),
            "spark_best": min(spark_runs, key=lambda r: r["seconds_container_wall"]),
            "pandas_all_total": [r["seconds_total"] for r in pandas_runs],
            "spark_all_wall": [r["seconds_container_wall"] for r in spark_runs],
            "correctness": compare(name),
        }
        print(json.dumps({name: report["datasets"][name]}), flush=True)
    (WORK / "bench.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
