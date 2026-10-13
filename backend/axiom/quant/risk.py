"""Risk metrics and position sizing. Deterministic; the LLM never computes these."""

from __future__ import annotations

import numpy as np
import pandas as pd


def historical_var_cvar(returns: pd.Series, level: float = 0.95) -> dict:
    r = returns.dropna().to_numpy(dtype=float)
    if len(r) < 30:
        return {"error": "insufficient_history", "n": len(r)}
    cutoff = np.quantile(r, 1 - level)
    tail = r[r <= cutoff]
    return {
        "level": level,
        "var_1d": round(float(-cutoff), 4),
        "cvar_1d": round(float(-tail.mean()), 4),
        "n": len(r),
    }


def size_position(
    equity: float,
    price: float,
    atr: float,
    risk_per_trade: float = 0.01,
    stop_atr_mult: float = 2.0,
    max_position_pct: float = 0.20,
) -> dict:
    """Fixed-fractional sizing: risk `risk_per_trade` of equity if the ATR stop is hit,
    capped by `max_position_pct` of equity. Reports which constraint bound."""
    if min(equity, price, atr) <= 0:
        raise ValueError("equity, price and atr must be positive")
    stop_distance = stop_atr_mult * atr
    by_risk = int((equity * risk_per_trade) // stop_distance)
    by_cap = int((equity * max_position_pct) // price)
    shares = max(0, min(by_risk, by_cap))
    return {
        "shares": shares,
        "notional": round(shares * price, 2),
        "position_pct": round(shares * price / equity, 4),
        "stop_price": round(price - stop_distance, 2),
        "risk_amount": round(shares * stop_distance, 2),
        "risk_pct_of_equity": round(shares * stop_distance / equity, 4),
        "binding_constraint": "risk_per_trade" if by_risk <= by_cap else "max_position_pct",
    }


def check_limits(
    positions: dict[str, float],
    equity: float,
    max_position_pct: float = 0.20,
    max_gross_pct: float = 1.0,
) -> list[str]:
    """Return human-readable violations for notional exposures keyed by ticker."""
    issues = []
    for t, notional in positions.items():
        if notional / equity > max_position_pct + 1e-9:
            issues.append(f"{t} is {notional / equity:.0%} of equity (limit {max_position_pct:.0%})")
    gross = sum(abs(v) for v in positions.values()) / equity
    if gross > max_gross_pct + 1e-9:
        issues.append(f"gross exposure {gross:.0%} exceeds {max_gross_pct:.0%}")
    return issues
