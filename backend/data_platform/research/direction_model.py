"""Does a simple model predict the 5-day direction of exchange rates better than naive baselines?

    python -m data_platform.research.direction_model [--bqml --project <id>]

Data: Federal Reserve H.10 daily exchange rates, 24 currencies since 2000 (public domain, see
data_platform/spark/fx_data.py). The label is 1 when the rate is higher 5 trading days later. Rows where it is
exactly unchanged (pegs) are dropped. Features use only data up to the row's date, computed with Axiom's own
indicator functions.

Split by time, with an embargo: a row belongs to a period only if its 5-day label window ends inside it.
    train       2000-01-01 .. 2015-12-31   (fit)
    validation  2016-01-01 .. 2019-12-31   (choose regularisation)
    test        2020-01-01 .. latest       (evaluated once, after refitting on train + validation)

Baselines on the same test rows: the majority class of the training labels, and 5-day momentum (predict the
last 5-day move continues). Log loss is compared with a coin flip (ln 2 = 0.693).
With --bqml, the same features and split train a BigQuery ML logistic regression (the "twin").
Seeded and deterministic. Not wired into the agents.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from axiom.quant.indicators import realized_vol, rsi, sma

from .. import BACKEND_DIR

HORIZON = 5
VAL_START, TEST_START = pd.Timestamp("2016-01-01"), pd.Timestamp("2020-01-01")
FEATURES = ["ret_1", "ret_5", "ret_20", "dist_sma20", "dist_sma50", "dist_sma200", "rsi14", "vol20"]
C_GRID = (0.001, 0.01, 0.1, 1.0, 10.0)
SEED = 7
OUT = BACKEND_DIR / ".cache" / "research"


def series_features(close: pd.Series) -> pd.DataFrame:
    """Causal features for one series (index = trading days in order)."""
    logc = np.log(close)
    return pd.DataFrame(
        {
            "ret_1": logc.diff(1),
            "ret_5": logc.diff(5),
            "ret_20": logc.diff(20),
            "dist_sma20": close / sma(close, 20) - 1,
            "dist_sma50": close / sma(close, 50) - 1,
            "dist_sma200": close / sma(close, 200) - 1,
            "rsi14": rsi(close, 14),
            "vol20": realized_vol(close, 20),
        },
        index=close.index,
    )


def build(df: pd.DataFrame, feature_fn=series_features) -> pd.DataFrame:
    """One row per (series, date): features, the forward 5-day log return, its label and label end date."""
    parts = []
    for name, g in df.sort_values(["series", "date"]).groupby("series", sort=False):
        g = g.reset_index(drop=True)
        f = feature_fn(g["close"])
        logc = np.log(g["close"])
        f["fwd_ret"] = logc.shift(-HORIZON) - logc
        f["label_end"] = pd.to_datetime(g["date"]).shift(-HORIZON)
        f.insert(0, "date", pd.to_datetime(g["date"]))
        f.insert(0, "series", name)
        parts.append(f)
    out = pd.concat(parts, ignore_index=True)
    out = out.dropna(subset=[*FEATURES, "fwd_ret"])
    out = out[out["fwd_ret"] != 0].copy()
    out["y"] = (out["fwd_ret"] > 0).astype(int)
    return out.reset_index(drop=True)


def split(frame: pd.DataFrame) -> pd.Series:
    """'train', 'val', 'test', or 'embargo' (label window straddles a boundary; never used)."""
    s = pd.Series("embargo", index=frame.index)
    d, end = frame["date"], frame["label_end"]
    s[end < VAL_START] = "train"
    s[(d >= VAL_START) & (end < TEST_START)] = "val"
    s[d >= TEST_START] = "test"
    return s


def model(c: float):
    return make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=1000, random_state=SEED))


def non_overlapping(frame: pd.DataFrame) -> pd.Series:
    """Every 5th row per series, so 5-day label windows do not overlap (for honest error bars)."""
    return frame.groupby("series").cumcount() % HORIZON == 0


def evaluate(y: np.ndarray, p: np.ndarray, mask: np.ndarray) -> dict[str, float]:
    pred = (p > 0.5).astype(int)
    acc = accuracy_score(y, pred)
    n = int(mask.sum())
    acc_no = accuracy_score(y[mask], pred[mask])
    half = 1.96 * math.sqrt(acc_no * (1 - acc_no) / n)
    return {
        "accuracy": round(acc, 4),
        "accuracy_non_overlapping": round(acc_no, 4),
        "accuracy_95ci_non_overlapping": [round(acc_no - half, 4), round(acc_no + half, 4)],
        "log_loss": round(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1]), 4),
        "roc_auc": round(roc_auc_score(y, p), 4) if len(set(y)) > 1 else float("nan"),
    }


def month_bootstrap(te: pd.DataFrame, p: np.ndarray, base_rate: float, reps: int = 500) -> dict:
    """95% intervals from resampling whole calendar months of the test period (all currencies together),
    which keeps the strong same-day correlation between dollar exchange rates inside each block."""
    rng = np.random.default_rng(SEED)
    month = te["date"].dt.to_period("M").to_numpy()
    months = np.unique(month)
    idx = {m: np.flatnonzero(month == m) for m in months}
    y = te["y"].to_numpy()
    auc, gain, acc_gain = [], [], []
    for _ in range(reps):
        rows = np.concatenate([idx[m] for m in rng.choice(months, len(months))])
        yy, pp = y[rows], p[rows]
        auc.append(roc_auc_score(yy, pp))
        base = np.full(len(rows), base_rate)
        gain.append(log_loss(yy, base, labels=[0, 1]) - log_loss(yy, pp, labels=[0, 1]))
        acc_gain.append(((pp > 0.5) == yy).mean() - ((base > 0.5) == yy).mean())

    def ci(v: list[float]) -> list[float]:
        return [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)]

    return {
        "months": len(months),
        "reps": reps,
        "roc_auc_95ci": ci(auc),
        "log_loss_gain_vs_majority_95ci": ci(gain),
        "accuracy_gain_vs_majority_95ci": ci(acc_gain),
    }


def run(df: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    frame = build(df)
    frame["split"] = split(frame)
    tr, va, te = (frame[frame["split"] == k] for k in ("train", "val", "test"))
    Xtr, Xva, Xte = (x[FEATURES].to_numpy() for x in (tr, va, te))
    ytr, yva, yte = (x["y"].to_numpy() for x in (tr, va, te))

    val_loss = {c: log_loss(yva, model(c).fit(Xtr, ytr).predict_proba(Xva)[:, 1]) for c in C_GRID}
    best_c = min(val_loss, key=val_loss.get)
    trva = frame[frame["split"].isin(["train", "val"]) & (frame["label_end"] < TEST_START)]
    final = model(best_c).fit(trva[FEATURES].to_numpy(), trva["y"].to_numpy())
    p_model = final.predict_proba(Xte)[:, 1]

    base_rate = float(trva["y"].mean())
    mask = non_overlapping(te).to_numpy()
    sig = np.where(p_model > 0.5, 1, -1)
    results = {
        "rows": {k: int((frame["split"] == k).sum()) for k in ("train", "val", "test", "embargo")},
        "series": int(frame["series"].nunique()),
        "test_period": [str(te["date"].min().date()), str(te["date"].max().date())],
        "chosen_C": best_c,
        "val_log_loss_by_C": {str(c): round(v, 5) for c, v in val_loss.items()},
        "train_up_rate": round(base_rate, 4),
        "test_up_rate": round(float(yte.mean()), 4),
        "model": evaluate(yte, p_model, mask),
        "baseline_majority": evaluate(yte, np.full(len(yte), base_rate), mask),  # predicts the majority class
        "baseline_momentum": evaluate(yte, np.where(te["ret_5"].to_numpy() > 0, 0.51, 0.49), mask),
        "coinflip_log_loss": round(math.log(2), 4),
        "mean_5d_log_return_non_overlapping": {
            "model_signal": round(float((sig * te["fwd_ret"].to_numpy())[mask].mean()), 6),
            "always_long": round(float(te["fwd_ret"].to_numpy()[mask].mean()), 6),
        },
        "coefficients_standardised": dict(
            zip(FEATURES, np.round(final[-1].coef_[0], 4).tolist(), strict=True)
        ),
    }
    results["bootstrap_monthly_blocks"] = month_bootstrap(te, p_model, base_rate)
    frame["p_model"] = np.nan
    frame.loc[te.index, "p_model"] = p_model
    return results, frame


def bqml_twin(project: str, frame: pd.DataFrame) -> dict:
    """Same features and split in BigQuery ML (logistic_reg); evaluate on the same test rows."""
    from google.cloud import bigquery

    client = bigquery.Client(project=project, location="US")
    ds = f"{project}.axiom_research"
    d = bigquery.Dataset(ds)
    d.location, d.labels = "US", {"app": "axiom", "managed-by": "data-platform", "contains-pii": "no"}
    d.description = (
        "Research tables built from public-domain data (Federal Reserve H.10). Not used by the app."
    )
    client.create_dataset(d, exists_ok=True)
    table = f"{ds}.h10_direction"
    cols = ["series", "date", *FEATURES, "y", "split", "p_model"]
    up = frame[cols].copy()
    up["date"] = up["date"].dt.date
    cfg = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    client.load_table_from_dataframe(up, table, job_config=cfg).result()

    feats = ", ".join(FEATURES)
    model_id = f"{ds}.direction_logreg"
    client.query(
        f"""CREATE OR REPLACE MODEL `{model_id}`
        OPTIONS (model_type = 'logistic_reg', input_label_cols = ['y'], data_split_method = 'NO_SPLIT',
                 max_iterations = 50)  -- BQML standardises features itself; default L2 (none)
        AS SELECT {feats}, y FROM `{table}` WHERE split IN ('train', 'val')"""
    ).result()
    ev = next(
        iter(
            client.query(
                f"SELECT * FROM ML.EVALUATE(MODEL `{model_id}`, (SELECT {feats}, y FROM `{table}` WHERE split = 'test'))"
            ).result()
        )
    )
    agree = next(
        iter(
            client.query(
                f"""SELECT COUNT(*) AS n, COUNTIF(predicted_y = IF(p_model > 0.5, 1, 0)) AS same,
                    AVG(ABS((SELECT prob FROM UNNEST(predicted_y_probs) WHERE label = 1) - p_model)) AS mean_abs_p_diff
                FROM ML.PREDICT(MODEL `{model_id}`, (SELECT * FROM `{table}` WHERE split = 'test'))"""
            ).result()
        )
    )
    return {
        "model": model_id,
        "evaluate": {k: round(float(ev[k]), 4) for k in ("accuracy", "log_loss", "roc_auc")},
        "test_rows": agree["n"],
        "same_class_as_sklearn": round(agree["same"] / agree["n"], 4),
        "mean_abs_prob_diff": round(float(agree["mean_abs_p_diff"]), 5),
    }


def main() -> None:
    from data_platform.spark.fx_data import download_h10

    ap = argparse.ArgumentParser(prog="python -m data_platform.research.direction_model")
    ap.add_argument("--bqml", action="store_true")
    ap.add_argument("--project")
    a = ap.parse_args()
    df = download_h10(BACKEND_DIR / ".cache" / "spark" / "h10_pages")
    results, frame = run(df)
    if a.bqml:
        if not a.project:
            raise SystemExit("--project is required with --bqml")
        results["bqml_twin"] = bqml_twin(a.project, frame)
    OUT.mkdir(parents=True, exist_ok=True)
    Path(OUT / "direction_model.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
