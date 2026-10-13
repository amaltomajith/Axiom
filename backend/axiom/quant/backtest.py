"""Backtesting with no lookahead, transaction costs, a buy-and-hold benchmark and an honest verdict.

Conventions
-----------
* A strategy returns a *position* series in [0, 1] (long/flat). The position at row t is decided
  from data up to and including the close of t and earns the return from t to t+1.
* `apply_strategy` enforces that by shifting the position one bar; strategies themselves must be
  causal (verified in tests by truncation invariance).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from math import erf, sqrt
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import indicators as ind

TRADING_DAYS = ind.TRADING_DAYS
StrategyFn = Callable[[pd.DataFrame], pd.Series]
Verdict = Literal["insufficient_data", "no_edge", "unproven", "edge_detected"]

# ----------------------------------------------------------------------------- strategies


def buy_and_hold(df: pd.DataFrame) -> pd.Series:
    return pd.Series(1.0, index=df.index)


def sma_cross(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> pd.Series:
    f, s = ind.sma(df["close"], fast), ind.sma(df["close"], slow)
    return ((f > s) & f.notna() & s.notna()).astype(float)


def macd_trend(df: pd.DataFrame) -> pd.Series:
    m = ind.macd(df["close"])
    return ((m["macd"] > m["signal"]) & m["signal"].notna()).astype(float)


def rsi_reversion(df: pd.DataFrame, entry: float = 30.0, exit_: float = 55.0) -> pd.Series:
    """Stateful: go long when RSI < entry, stay long until RSI > exit_."""
    r = ind.rsi(df["close"]).to_numpy()
    pos = np.zeros(len(r))
    holding = False
    for i, v in enumerate(r):
        if np.isnan(v):
            holding = False
        elif holding and v > exit_:
            holding = False
        elif not holding and v < entry:
            holding = True
        pos[i] = 1.0 if holding else 0.0
    return pd.Series(pos, index=df.index)


STRATEGIES: dict[str, StrategyFn] = {
    "sma_cross": sma_cross,
    "macd_trend": macd_trend,
    "rsi_reversion": rsi_reversion,
    "buy_and_hold": buy_and_hold,
}

# ----------------------------------------------------------------------------- engine


def apply_strategy(
    close: pd.Series, position: pd.Series, cost_bps: float = 5.0, slippage_bps: float = 5.0
) -> pd.Series:
    """Net daily returns of holding `position` (decided at close t, earned over t -> t+1)."""
    ret = close.pct_change().fillna(0.0)
    pos = position.reindex(close.index).fillna(0.0).shift(1).fillna(0.0)
    turnover = pos.diff().abs()
    turnover.iloc[0] = abs(pos.iloc[0])
    return pos * ret - turnover * (cost_bps + slippage_bps) / 1e4


@dataclass
class Metrics:
    total_return: float
    cagr: float
    ann_vol: float
    sharpe: float
    sortino: float
    max_drawdown: float
    hit_rate: float
    exposure: float
    n_days: int

    def to_dict(self) -> dict[str, float | int]:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def sharpe_ratio(returns: np.ndarray) -> float:
    sd = returns.std(ddof=1) if len(returns) > 1 else 0.0
    return float(returns.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else 0.0


def compute_metrics(returns: pd.Series, position: pd.Series | None = None) -> Metrics:
    r = returns.to_numpy(dtype=float)
    n = len(r)
    equity = np.cumprod(1 + r)
    total = float(equity[-1] - 1) if n else 0.0
    years = n / TRADING_DAYS
    cagr = float(equity[-1] ** (1 / years) - 1) if n and years > 0 and equity[-1] > 0 else -1.0
    downside = r[r < 0]
    dd_sd = float(np.sqrt((downside**2).sum() / n)) if n else 0.0
    peak = np.maximum.accumulate(equity) if n else equity
    held = r[r != 0]
    return Metrics(
        total_return=total,
        cagr=cagr,
        ann_vol=float(r.std(ddof=1) * np.sqrt(TRADING_DAYS)) if n > 1 else 0.0,
        sharpe=sharpe_ratio(r),
        sortino=float(r.mean() / dd_sd * np.sqrt(TRADING_DAYS)) if dd_sd > 0 else 0.0,
        max_drawdown=float((equity / peak - 1).min()) if n else 0.0,
        hit_rate=float((held > 0).mean()) if len(held) else 0.0,
        exposure=float(position.mean()) if position is not None and len(position) else 1.0,
        n_days=n,
    )


def paired_bootstrap_sharpe_diff(
    strategy: pd.Series,
    benchmark: pd.Series,
    n_boot: int = 1000,
    block: int = 10,
    seed: int = 7,
) -> tuple[float, float, float]:
    """Moving-block bootstrap of (Sharpe_strategy - Sharpe_benchmark); returns (point, lo95, hi95)."""
    s, b = strategy.to_numpy(float), benchmark.to_numpy(float)
    n = len(s)
    point = sharpe_ratio(s) - sharpe_ratio(b)
    if n < 2 * block:
        return point, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    diffs = np.empty(n_boot)
    for k in range(n_boot):
        starts = rng.integers(0, n - block + 1, size=n_blocks)
        idx = np.concatenate([np.arange(st, st + block) for st in starts])[:n]
        diffs[k] = sharpe_ratio(s[idx]) - sharpe_ratio(b[idx])
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return point, float(lo), float(hi)


def make_verdict(strategy: pd.Series, benchmark: pd.Series, min_days: int = 252) -> dict:
    n = len(strategy)
    point, lo, hi = paired_bootstrap_sharpe_diff(strategy, benchmark)
    if n < min_days:
        v: Verdict = "insufficient_data"
        msg = f"Only {n} trading days; need >= {min_days} for a meaningful verdict."
    elif np.isnan(lo):
        v, msg = "insufficient_data", "Sample too small to bootstrap."
    elif lo > 0:
        v, msg = "edge_detected", "Sharpe beat buy-and-hold with 95% bootstrap confidence."
    elif point <= 0:
        v, msg = "no_edge", "Strategy did not beat buy-and-hold on risk-adjusted terms."
    else:
        v, msg = "unproven", "Higher Sharpe than buy-and-hold, but not statistically distinguishable."
    return {
        "verdict": v,
        "message": msg,
        "sharpe_diff": round(point, 3),
        "sharpe_diff_ci95": [
            None if np.isnan(lo) else round(lo, 3),
            None if np.isnan(hi) else round(hi, 3),
        ],
    }


def run_backtest(
    df: pd.DataFrame, strategy: str | StrategyFn, cost_bps: float = 5.0, slippage_bps: float = 5.0
) -> dict:
    fn = STRATEGIES[strategy] if isinstance(strategy, str) else strategy
    name = strategy if isinstance(strategy, str) else getattr(strategy, "__name__", "custom")
    pos = fn(df)
    strat = apply_strategy(df["close"], pos, cost_bps, slippage_bps)
    bench = apply_strategy(df["close"], buy_and_hold(df), cost_bps, slippage_bps)
    return _package(name, df, strat, bench, pos)


def _package(name: str, df: pd.DataFrame, strat: pd.Series, bench: pd.Series, pos: pd.Series) -> dict:
    step = max(1, len(df) // 250)
    return {
        "strategy": name,
        "metrics": compute_metrics(strat, pos).to_dict(),
        "benchmark_metrics": compute_metrics(bench).to_dict(),
        **make_verdict(strat, bench),
        "equity_curve": [
            {"date": str(d)[:10], "strategy": round(float(s), 4), "benchmark": round(float(b), 4)}
            for d, s, b in zip(df.index, (1 + strat).cumprod(), (1 + bench).cumprod(), strict=True)
        ][::step],
        "assumptions": "long/flat, next-bar execution, costs+slippage applied on turnover",
    }


# ----------------------------------------------------------------------------- walk-forward ML


def feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]
    lr = ind.log_returns(close)
    m = ind.macd(close)
    return pd.DataFrame(
        {
            "r1": lr,
            "r2": lr.shift(1),
            "r3": lr.shift(2),
            "r5": lr.rolling(5).sum(),
            "rsi": ind.rsi(close) / 100 - 0.5,
            "vol20": lr.rolling(20).std(),
            "gap20": close / ind.sma(close, 20) - 1,
            "macd_h": m["hist"] / close,
        },
        index=df.index,
    )


def walk_forward_predictions(
    df: pd.DataFrame, min_train: int = 250, refit_every: int = 21, alpha: float = 1000.0
) -> tuple[pd.Series, pd.Series]:
    """Out-of-sample next-day return predictions from an expanding-window ridge.

    Returns (predictions, target). At decision row i the model is fit on rows j <= i-1: their
    targets (return j -> j+1 <= i) are known at the close of row i, so no future data leaks in.
    Predictions for rows i .. i+refit_every-1 come from that single fit.
    """
    feats = feature_frame(df)
    target = ind.log_returns(df["close"]).shift(-1)  # target[j] = return j -> j+1
    n = len(df)
    preds = pd.Series(np.nan, index=df.index)
    valid_rows = np.flatnonzero(feats.notna().all(axis=1).to_numpy())
    if len(valid_rows) == 0:
        return preds, target
    first = int(valid_rows[0])

    for i in range(first + min_train, n, refit_every):
        x, y = feats.iloc[first:i], target.iloc[first:i]
        ok = y.notna().to_numpy()
        if ok.sum() < 60:
            continue
        model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
        model.fit(x[ok], y[ok])
        block = feats.iloc[i : i + refit_every]
        preds.iloc[i : i + len(block)] = model.predict(block)
    return preds, target


def walk_forward_ridge(
    df: pd.DataFrame,
    min_train: int = 250,
    refit_every: int = 21,
    alpha: float = 1000.0,
    threshold: float = 0.0,
) -> dict:
    """Trade the out-of-sample ridge predictions (long if predicted return > threshold, else flat)
    and report skill + the standard bootstrap verdict against buy-and-hold."""
    preds, target = walk_forward_predictions(df, min_train, refit_every, alpha)
    oos = preds.dropna()
    if len(oos) < 30:
        return {
            "verdict": "insufficient_data",
            "message": "Not enough out-of-sample rows.",
            "n_oos": len(oos),
        }

    position = (preds > threshold).astype(float).where(preds.notna(), 0.0)
    realized = target.loc[oos.index]
    ok = realized.notna()
    pr, rr = oos[ok].to_numpy(), realized[ok].to_numpy()
    oos_r2 = float(1 - ((rr - pr) ** 2).sum() / (rr**2).sum())  # vs. a zero-return naive forecast
    hits = int((np.sign(pr) == np.sign(rr)).sum())
    n_eval = len(pr)
    # Null hypothesis = best constant guess. In an uptrending stock "always up" already scores >50%,
    # so skill must beat the majority-class base rate, not a coin flip.
    up_rate = float((rr > 0).mean())
    base_rate = max(up_rate, 1 - up_rate)
    z = (hits - n_eval * base_rate) / sqrt(n_eval * base_rate * (1 - base_rate))
    p_value = float(1 - 0.5 * (1 + erf(z / sqrt(2))))  # one-sided binomial test, normal approx

    window = df.loc[oos.index[0] :]
    strat = apply_strategy(df["close"], position).loc[window.index]
    bench = apply_strategy(df["close"], buy_and_hold(df)).loc[window.index]
    out = _package("walk_forward_ridge", window, strat, bench, position.loc[window.index])
    out["model_skill"] = {
        "oos_r2_vs_zero": round(oos_r2, 5),
        "directional_accuracy": round(hits / n_eval, 4),
        "naive_majority_accuracy": round(base_rate, 4),
        "directional_p_value_vs_naive": round(p_value, 4),
        "n_oos": n_eval,
        "interpretation": (
            "no predictive skill (OOS R2 <= 0)"
            if oos_r2 <= 0
            else "directional accuracy not better than always guessing the majority direction"
            if p_value > 0.05
            else "some out-of-sample skill; defer to the bootstrap verdict before trusting it"
        ),
    }
    return out
