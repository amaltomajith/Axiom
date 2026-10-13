"""OHLCV market data: Twelve Data (if keyed) with a keyless yfinance fallback, cached."""

from __future__ import annotations

import asyncio
import math
import re

import httpx
import pandas as pd

from axiom.config import get_settings

from . import ratelimit
from .cache import get_cache

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
OHLCV_TTL = 10 * 60
MAX_BARS = 5000
# Every caller asks for a different window (60..800 bars). Fetch one canonical window per ticker and slice
# it, so a single analysis costs one upstream request instead of eight (free tiers are tiny and shared).
CANONICAL_BARS = 1500


class DataError(Exception):
    """A data source failed or returned nothing usable (message is safe to show an agent)."""


def normalize_ticker(ticker: str) -> str:
    t = (ticker or "").strip().upper()
    if not TICKER_RE.match(t):
        raise DataError(f"Invalid ticker {ticker!r}; expected letters/digits/.- up to 10 chars.")
    return t


def _to_frame(records: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame.from_records(records)
    if df.empty:
        raise DataError("No price data returned.")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df[["open", "high", "low", "close", "volume"]].astype(float).dropna(subset=["close"])
    return df[~df.index.duplicated(keep="last")]


async def _twelvedata(ticker: str, bars: int, key: str) -> list[dict]:
    await ratelimit.TWELVEDATA.acquire()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            "https://api.twelvedata.com/time_series",
            params={"symbol": ticker, "interval": "1day", "outputsize": bars, "apikey": key},
        )
    if r.status_code == 429:
        raise DataError("Twelve Data rate limit reached.")
    body = r.json()
    if body.get("status") == "error":
        raise DataError(f"Twelve Data: {body.get('message', 'unknown error')}")
    return [
        {
            "date": v["datetime"],
            "open": v["open"],
            "high": v["high"],
            "low": v["low"],
            "close": v["close"],
            "volume": v.get("volume") or 0,
        }
        for v in body.get("values", [])
    ]


def _yfinance_sync(ticker: str, bars: int) -> list[dict]:
    import yfinance as yf

    years = max(1, math.ceil(bars / 240) + 1)
    hist = yf.Ticker(ticker).history(period=f"{min(years, 20)}y", interval="1d", auto_adjust=True)
    if hist is None or hist.empty:
        return []
    hist = hist.tail(bars)
    return [
        {
            "date": idx.strftime("%Y-%m-%d"),
            "open": r.Open,
            "high": r.High,
            "low": r.Low,
            "close": r.Close,
            "volume": r.Volume,
        }
        for idx, r in hist.iterrows()
    ]


async def fetch_ohlcv(ticker: str, bars: int = 504) -> tuple[pd.DataFrame, str]:
    """Return (frame, provider). Frame index is a sorted DatetimeIndex of daily bars."""
    t = normalize_ticker(ticker)
    bars = max(30, min(int(bars), MAX_BARS))
    fetch_bars = max(bars, CANONICAL_BARS)
    cache = get_cache()
    key = f"ohlcv:{t}:{fetch_bars}"
    hit = cache.get(key)
    if hit is not None:
        return _to_frame(hit["records"]).tail(bars), hit["provider"]

    settings = get_settings()
    records: list[dict] = []
    provider = ""
    errors: list[str] = []
    if settings.twelvedata_api_key:
        try:
            records, provider = await _twelvedata(t, fetch_bars, settings.twelvedata_api_key), "twelvedata"
        except (DataError, httpx.HTTPError) as e:
            errors.append(str(e))
    if not records:
        try:
            records = await asyncio.to_thread(_yfinance_sync, t, fetch_bars)
            provider = "yfinance"
        except Exception as e:  # yfinance raises assorted errors; surface as DataError
            errors.append(f"yfinance: {e}")
    if not records:
        raise DataError(f"No data for {t}. " + " | ".join(errors))

    cache.set(key, {"records": records, "provider": provider}, OHLCV_TTL)
    return _to_frame(records).tail(bars), provider
