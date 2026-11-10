"""Leakage tests for the research direction model (data_platform/research/direction_model.py)."""

import numpy as np
import pandas as pd

from data_platform.research import direction_model as dm
from data_platform.spark.fx_data import synthetic

KEY = ["series", "date"]


def future_sensitive(df: pd.DataFrame, cutoff, feature_fn=dm.series_features) -> set[str]:
    """Feature columns whose values on or before `cutoff` change when every close after it is changed."""
    later = pd.to_datetime(df["date"]) > cutoff
    shocked = df.copy()
    shocked.loc[later, "close"] *= np.random.default_rng(1).uniform(0.5, 1.5, later.sum())
    a = dm.build(df, feature_fn)
    b = dm.build(shocked, feature_fn)
    a, b = a[a["date"] <= cutoff], b[b["date"] <= cutoff]
    m = a.merge(b, on=KEY, suffixes=("", "_b"))
    assert len(m) == len(a) > 0
    return {c for c in dm.FEATURES if not np.allclose(m[c], m[f"{c}_b"], rtol=0, atol=0)}


def test_features_use_only_the_past():
    df = synthetic(3, 600)
    assert future_sensitive(df, pd.Timestamp(df["date"].iloc[450])) == set()


def test_the_check_catches_a_leaky_feature():
    def leaky(close):
        f = dm.series_features(close)
        f["ret_1"] = np.log(close).shift(-1) - np.log(close)  # tomorrow's return: a classic leak
        return f

    df = synthetic(3, 600)
    assert future_sensitive(df, pd.Timestamp(df["date"].iloc[450]), leaky) == {"ret_1"}


def test_label_is_exactly_five_days_ahead():
    df = synthetic(2, 300)
    f = dm.build(df)
    for name, g in df.groupby("series"):
        c = g.set_index(pd.to_datetime(g["date"]))["close"]
        rows = f[f["series"] == name]
        future = c.shift(-dm.HORIZON).reindex(rows["date"]).to_numpy()
        now = c.reindex(rows["date"]).to_numpy()
        assert (rows["y"].to_numpy() == (future > now)).all()
        assert (
            rows["label_end"].to_numpy() == c.index.to_series().shift(-dm.HORIZON).reindex(rows["date"])
        ).all()


def test_no_label_window_crosses_a_split_boundary():
    f = dm.build(synthetic(2, 6800))  # 2000 to 2026
    s = dm.split(f)
    assert (f.loc[s == "train", "label_end"] < dm.VAL_START).all()
    assert (f.loc[s == "val", "date"] >= dm.VAL_START).all()
    assert (f.loc[s == "val", "label_end"] < dm.TEST_START).all()
    assert (f.loc[s == "test", "date"] >= dm.TEST_START).all()
    assert (s == "embargo").sum() == 2 * 2 * dm.HORIZON  # 5 rows before each boundary, per series


def test_pure_noise_shows_no_skill():
    """A random walk is unpredictable: any real 'skill' here would mean a leak in the pipeline."""
    res, _ = dm.run(synthetic(10, 6800))
    assert abs(res["model"]["roc_auc"] - 0.5) < 0.03, res["model"]
    assert res["model"]["log_loss"] > 0.68, res["model"]
