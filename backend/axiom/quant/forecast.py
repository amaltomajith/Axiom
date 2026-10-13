"""Calibrated uncertainty cones (historical simulation), checked by walk-forward coverage.

The cone is deliberately drift-neutral: centred on the last close with empirical k-day return
quantiles (demeaned). We do not claim directional skill the data cannot support.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import log_returns

DEFAULT_QUANTILES = (0.1, 0.25, 0.5, 0.75, 0.9)


def _kday_returns(lr: np.ndarray, k: int) -> np.ndarray:
    if len(lr) < k:
        return np.array([])
    c = np.concatenate([[0.0], np.cumsum(lr)])
    return c[k:] - c[:-k]


def _ewma_sigma(lr: np.ndarray, lam: float = 0.94) -> np.ndarray:
    """sigma[t] = conditional vol of lr[t], known before day t (uses returns up to t-1);
    sigma[len] is the one-step-ahead forecast."""
    var = np.empty(len(lr) + 1)
    var[0] = np.var(lr[: min(len(lr), 20)]) or 1e-8
    for t in range(len(lr)):
        var[t + 1] = lam * var[t] + (1 - lam) * lr[t] ** 2
    return np.sqrt(var)


def forecast_cone(
    close: pd.Series,
    horizon: int = 14,
    quantiles: tuple[float, ...] = DEFAULT_QUANTILES,
    window: int = 504,
) -> dict:
    lr = log_returns(close).dropna().to_numpy()[-window:]
    last = float(close.iloc[-1])
    if len(lr) < max(60, horizon * 3):
        return {"error": "insufficient_history", "n_returns": len(lr)}
    # Filtered historical simulation: standardise returns by EWMA vol, resample the standardised
    # shocks, rescale by today's vol forecast. Adapts the cone width to the current vol regime.
    sigma = _ewma_sigma(lr)
    z = lr / sigma[:-1]
    z = z - z.mean()
    sigma_next = float(sigma[-1])
    steps = []
    for k in range(1, horizon + 1):
        kr = _kday_returns(z, k) * sigma_next
        qs = np.quantile(kr, quantiles)
        steps.append(
            {
                "step": k,
                **{
                    f"p{round(q * 100)}": round(last * float(np.exp(v)), 2)
                    for q, v in zip(quantiles, qs, strict=True)
                },
            }
        )
    return {
        "last_close": round(last, 2),
        "horizon_days": horizon,
        "method": "filtered_historical_simulation_zero_drift",
        "window_returns": len(lr),
        "cone": steps,
    }


def coverage_check(
    close: pd.Series,
    horizon: int = 14,
    lo_q: float = 0.1,
    hi_q: float = 0.9,
    start: int = 300,
    stride: int = 3,
) -> dict:
    """Walk-forward: fraction of realised horizon-day closes inside the [lo_q, hi_q] band."""
    lo_key, hi_key = f"p{round(lo_q * 100)}", f"p{round(hi_q * 100)}"
    hits = total = 0
    for t in range(start, len(close) - horizon, stride):
        cone = forecast_cone(close.iloc[: t + 1], horizon, (lo_q, hi_q))
        if "error" in cone:
            continue
        end = cone["cone"][-1]
        actual = float(close.iloc[t + horizon])
        hits += int(end[lo_key] <= actual <= end[hi_key])
        total += 1
    nominal = hi_q - lo_q
    cov = hits / total if total else float("nan")
    return {
        "nominal_coverage": round(nominal, 2),
        "empirical_coverage": None if total == 0 else round(cov, 3),
        "n_checks": total,
        "well_calibrated": bool(total >= 30 and abs(cov - nominal) < 0.08),
    }
