"""Technical indicators with textbook definitions (pure functions over pandas Series).

All functions are causal: the value at index t uses only data at or before t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period, min_periods=period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    """EMA seeded with the SMA of the first `period` values (standard charting convention)."""
    values = close.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    if len(values) < period:
        return pd.Series(out, index=close.index)
    alpha = 2.0 / (period + 1)
    out[period - 1] = values[:period].mean()
    for i in range(period, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return pd.Series(out, index=close.index)


def _wilder(values: np.ndarray, period: int) -> np.ndarray:
    """Wilder's smoothing: first value is the simple mean of `period` observations,
    afterwards avg_t = (avg_{t-1} * (period - 1) + x_t) / period."""
    out = np.full(len(values), np.nan)
    if len(values) < period:
        return out
    out[period - 1] = values[:period].mean()
    for i in range(period, len(values)):
        out[i] = (out[i - 1] * (period - 1) + values[i]) / period
    return out


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI. First defined value is at index `period`."""
    delta = close.diff().to_numpy(dtype=float)
    gains = np.where(delta > 0, delta, 0.0)[1:]
    losses = np.where(delta < 0, -delta, 0.0)[1:]
    avg_gain = _wilder(gains, period)
    avg_loss = _wilder(losses, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
        out = 100.0 - 100.0 / (1.0 + rs)
    out = np.where((avg_loss == 0) & (avg_gain > 0), 100.0, out)
    out = np.where((avg_loss == 0) & (avg_gain == 0), 50.0, out)
    out = np.where(np.isnan(avg_gain), np.nan, out)
    return pd.Series(np.concatenate([[np.nan], out]), index=close.index)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    macd_line = ema(close, fast) - ema(close, slow)
    valid = macd_line.dropna()
    signal_line = pd.Series(np.nan, index=close.index)
    if len(valid) >= signal:
        signal_line.loc[valid.index] = ema(valid.reset_index(drop=True), signal).to_numpy()
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": macd_line - signal_line})


def bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = sma(close, period)
    std = close.rolling(period, min_periods=period).std(ddof=0)  # population std, per Bollinger
    upper, lower = mid + num_std * std, mid - num_std * std
    return pd.DataFrame(
        {"mid": mid, "upper": upper, "lower": lower, "pct_b": (close - lower) / (upper - lower)}
    )


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    tr.iloc[0] = high.iloc[0] - low.iloc[0]
    return pd.Series(_wilder(tr.to_numpy(dtype=float), period), index=close.index)


def log_returns(close: pd.Series) -> pd.Series:
    return np.log(close / close.shift(1))


def realized_vol(close: pd.Series, window: int = 20) -> pd.Series:
    """Annualised rolling volatility of daily log returns."""
    return log_returns(close).rolling(window, min_periods=window).std(ddof=1) * np.sqrt(TRADING_DAYS)


def volume_trend(volume: pd.Series, recent: int = 5, base: int = 20) -> float:
    """Ratio of recent average volume to the preceding baseline (>1 means rising participation)."""
    if len(volume) < recent + base:
        return float("nan")
    return float(volume.iloc[-recent:].mean() / volume.iloc[-(recent + base) : -recent].mean())


def indicator_snapshot(df: pd.DataFrame) -> dict[str, float | str | None]:
    """Latest indicator values for an OHLCV frame (columns: open, high, low, close, volume)."""

    def last(s: pd.Series) -> float | None:
        v = s.dropna()
        return round(float(v.iloc[-1]), 4) if len(v) else None

    close = df["close"]
    m, b = macd(close), bollinger(close)
    return {
        "close": last(close),
        "sma20": last(sma(close, 20)),
        "sma50": last(sma(close, 50)),
        "sma200": last(sma(close, 200)),
        "rsi14": last(rsi(close)),
        "macd": last(m["macd"]),
        "macd_signal": last(m["signal"]),
        "macd_hist": last(m["hist"]),
        "bb_pct_b": last(b["pct_b"]),
        "bb_width": last((b["upper"] - b["lower"]) / b["mid"]),
        "atr14": last(atr(df["high"], df["low"], close)),
        "vol20_annualized": last(realized_vol(close)),
        "volume_ratio_5v20": None if np.isnan(v := volume_trend(df["volume"])) else round(v, 3),
    }
