"""Analysis services shared by the MCP server and the HTTP API.

Every function returns a compact, JSON-serialisable summary (never raw bar arrays): the numbers are
computed deterministically here so an LLM only has to interpret, not calculate. Each result carries
`meta` so a claim can be traced back to the exact call, data provider and as-of date.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from axiom.data import market
from axiom.data.cache import get_cache
from axiom.quant import backtest as bt
from axiom.quant import forecast as fc
from axiom.quant import indicators as ind
from axiom.quant import regime as rg
from axiom.quant import risk as rk

PEER_FALLBACK = {
    "AAPL": ["MSFT", "GOOGL", "AMZN"],
    "MSFT": ["AAPL", "GOOGL", "AMZN"],
    "GOOGL": ["MSFT", "META", "AAPL"],
    "AMZN": ["MSFT", "GOOGL", "WMT"],
    "META": ["GOOGL", "SNAP", "PINS"],
    "NVDA": ["AMD", "AVGO", "INTC"],
    "AMD": ["NVDA", "INTC", "AVGO"],
    "TSLA": ["F", "GM", "RIVN"],
}


def _meta(tool: str, ticker: str, df: pd.DataFrame, provider: str) -> dict[str, Any]:
    return {
        "tool": tool,
        "ticker": ticker,
        "as_of": df.index[-1].strftime("%Y-%m-%d"),
        "provider": provider,
        "n_bars": len(df),
        "note": "daily bars; not real-time",
    }


def _pct(a: float, b: float) -> float:
    return round((a / b - 1) * 100, 2)


async def price_summary(ticker: str, days: int = 252) -> dict:
    t = market.normalize_ticker(ticker)
    df, provider = await market.fetch_ohlcv(t, max(days, 260))
    close = df["close"]
    last = float(close.iloc[-1])

    def ret(n: int) -> float | None:
        return _pct(last, float(close.iloc[-n - 1])) if len(close) > n else None

    window = df.iloc[-252:]
    hi, lo = float(window["high"].max()), float(window["low"].min())
    return {
        "meta": _meta("get_price_summary", t, df, provider),
        "last_close": round(last, 2),
        "returns_pct": {
            "1d": ret(1),
            "5d": ret(5),
            "1m": ret(21),
            "3m": ret(63),
            "6m": ret(126),
            "1y": ret(252),
        },
        "range_52w": {
            "high": round(hi, 2),
            "low": round(lo, 2),
            "pct_below_high": _pct(last, hi),
            "pct_above_low": _pct(last, lo),
        },
        "avg_volume_20d": int(df["volume"].iloc[-20:].mean()),
    }


def _signal_notes(s: dict, last: float) -> list[str]:
    notes = []
    if (r := s.get("rsi14")) is not None:
        notes.append(
            f"RSI {r:.0f}: " + ("overbought (>70)" if r > 70 else "oversold (<30)" if r < 30 else "neutral")
        )
    for key in ("sma50", "sma200"):
        if s.get(key):
            notes.append(f"price {'above' if last > s[key] else 'below'} {key.upper()}")
    if s.get("sma50") and s.get("sma200"):
        notes.append(
            "SMA50 above SMA200 (golden-cross regime)"
            if s["sma50"] > s["sma200"]
            else "SMA50 below SMA200 (death-cross regime)"
        )
    if (h := s.get("macd_hist")) is not None:
        notes.append(f"MACD histogram {'positive' if h > 0 else 'negative'}")
    if (b := s.get("bb_pct_b")) is not None:
        notes.append(
            "near/above upper Bollinger band"
            if b > 0.95
            else "near/below lower Bollinger band"
            if b < 0.05
            else "inside Bollinger bands"
        )
    return notes


async def indicators(ticker: str) -> dict:
    t = market.normalize_ticker(ticker)
    df, provider = await market.fetch_ohlcv(t, 400)
    snap = ind.indicator_snapshot(df)
    return {
        "meta": _meta("get_indicators", t, df, provider),
        "values": snap,
        "reading": _signal_notes(snap, float(df["close"].iloc[-1])),
        "caveat": "Indicators describe the past; they are not forecasts and have weak standalone edge.",
    }


async def regime(ticker: str) -> dict:
    t = market.normalize_ticker(ticker)
    df, provider = await market.fetch_ohlcv(t, 500)
    return {"meta": _meta("get_regime", t, df, provider), **rg.classify(df["close"])}


async def risk_metrics(ticker: str) -> dict:
    t = market.normalize_ticker(ticker)
    df, provider = await market.fetch_ohlcv(t, 756)
    close = df["close"]
    equity = close / close.cummax()
    return {
        "meta": _meta("get_risk_metrics", t, df, provider),
        "historical_var_cvar_95": rk.historical_var_cvar(close.pct_change(), 0.95),
        "annualized_vol_20d": None
        if ind.realized_vol(close).dropna().empty
        else round(float(ind.realized_vol(close).dropna().iloc[-1]), 4),
        "annualized_vol_full": round(float(ind.log_returns(close).std() * np.sqrt(ind.TRADING_DAYS)), 4),
        "max_drawdown_window": round(float(equity.min() - 1), 4),
        "current_drawdown": round(float(equity.iloc[-1] - 1), 4),
    }


def _thin_curve(result: dict, points: int = 24) -> dict:
    curve = result.pop("equity_curve", [])
    if curve:
        step = max(1, len(curve) // points)
        result["equity_curve_sampled"] = curve[::step]
    return result


async def backtest(
    ticker: str, strategy: str = "sma_cross", bars: int = 1000, full_curve: bool = False
) -> dict:
    t = market.normalize_ticker(ticker)
    if strategy not in bt.STRATEGIES:
        raise market.DataError(f"Unknown strategy {strategy!r}. Choose one of {sorted(bt.STRATEGIES)}.")
    df, provider = await market.fetch_ohlcv(t, bars)
    out = bt.run_backtest(df, strategy)
    if not full_curve:
        _thin_curve(out)
    return {"meta": _meta("run_backtest", t, df, provider), **out}


async def walk_forward(ticker: str, bars: int = 1250, full_curve: bool = False) -> dict:
    t = market.normalize_ticker(ticker)
    df, provider = await market.fetch_ohlcv(t, bars)
    out = bt.walk_forward_ridge(df)
    if not full_curve:
        _thin_curve(out)
    return {"meta": _meta("run_walk_forward_model", t, df, provider), **out}


async def forecast_cone(ticker: str, horizon: int = 14) -> dict:
    t = market.normalize_ticker(ticker)
    horizon = max(1, min(int(horizon), 60))
    df, provider = await market.fetch_ohlcv(t, 800)
    cone = fc.forecast_cone(df["close"], horizon)
    return {
        "meta": _meta("get_forecast_cone", t, df, provider),
        **cone,
        "calibration": fc.coverage_check(df["close"], min(horizon, 14)),
        "caveat": "Zero-drift uncertainty band, not a price target. No directional skill is claimed.",
    }


async def position_size(
    ticker: str,
    equity: float,
    risk_per_trade: float = 0.01,
    stop_atr_mult: float = 2.0,
    max_position_pct: float = 0.20,
) -> dict:
    t = market.normalize_ticker(ticker)
    if not (0 < risk_per_trade <= 0.05):
        raise market.DataError("risk_per_trade must be in (0, 0.05].")
    df, provider = await market.fetch_ohlcv(t, 120)
    atr = float(ind.atr(df["high"], df["low"], df["close"]).dropna().iloc[-1])
    price = float(df["close"].iloc[-1])
    sizing = rk.size_position(equity, price, atr, risk_per_trade, stop_atr_mult, max_position_pct)
    return {
        "meta": _meta("size_position", t, df, provider),
        "price": round(price, 2),
        "atr14": round(atr, 3),
        "inputs": {
            "equity": equity,
            "risk_per_trade": risk_per_trade,
            "stop_atr_mult": stop_atr_mult,
            "max_position_pct": max_position_pct,
        },
        **sizing,
    }


async def peer_comparison(ticker: str, peers: list[str] | None = None) -> dict:
    t = market.normalize_ticker(ticker)
    names = [market.normalize_ticker(p) for p in (peers or PEER_FALLBACK.get(t, []))][:5]
    rows = []
    for sym in [t, *names]:
        try:
            df, _ = await market.fetch_ohlcv(sym, 300)
        except market.DataError as e:
            rows.append({"ticker": sym, "error": str(e)})
            continue
        c = df["close"]
        rows.append(
            {
                "ticker": sym,
                "last_close": round(float(c.iloc[-1]), 2),
                "ret_3m_pct": _pct(float(c.iloc[-1]), float(c.iloc[-64])) if len(c) > 64 else None,
                "ret_1y_pct": _pct(float(c.iloc[-1]), float(c.iloc[-253])) if len(c) > 253 else None,
                "vol_annualized": round(float(ind.log_returns(c).std() * np.sqrt(ind.TRADING_DAYS)), 3),
                "rsi14": ind.indicator_snapshot(df)["rsi14"],
            }
        )
    return {
        "meta": {
            "tool": "get_peer_comparison",
            "ticker": t,
            "peers": names,
            "note": "daily bars; not real-time",
        },
        "rows": rows,
    }


def clear_cache() -> int:
    return get_cache().clear()
