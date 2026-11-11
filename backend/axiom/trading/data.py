"""Market data for the trader, as frames shaped like `market.fetch_ohlcv` (DatetimeIndex; open..volume).

Daily history (backtests, Time Machine) comes from the existing cached fetcher (Yahoo spelling for crypto).
Intraday bars for the live loop come from Alpaca's market data API (crypto needs no keys).
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta

import pandas as pd

from axiom.data import market

from .symbols import Symbol

TIMEFRAME_SECONDS = {"1Min": 60, "5Min": 300, "15Min": 900, "1Hour": 3600, "1Day": 86_400}


async def fetch_daily(symbols: list[Symbol], bars: int = 1500) -> dict[str, pd.DataFrame]:
    async def one(s: Symbol) -> tuple[str, pd.DataFrame]:
        df, _ = await market.fetch_ohlcv(s.yahoo, bars)
        return s.name, df

    pairs = await asyncio.gather(*(one(s) for s in symbols))
    return dict(pairs)


def _alpaca_timeframe(tf: str):
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    return {
        "1Min": TimeFrame(1, TimeFrameUnit.Minute),
        "5Min": TimeFrame(5, TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
        "1Day": TimeFrame(1, TimeFrameUnit.Day),
    }[tf]


def _bars_frame(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise market.DataError(f"No bars for {symbol}.")
    df = raw.xs(symbol, level="symbol") if isinstance(raw.index, pd.MultiIndex) else raw
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    idx = pd.DatetimeIndex(df.index)
    df.index = idx.tz_convert("UTC").tz_localize(None) if idx.tz is not None else idx
    return df.sort_index()


def _fetch_alpaca_sync(
    sym: Symbol, timeframe: str, limit: int, key: str | None, secret: str | None
) -> pd.DataFrame:
    start = datetime.now(UTC) - timedelta(
        seconds=TIMEFRAME_SECONDS[timeframe] * limit * (1 if sym.is_crypto else 3)
    )
    tf = _alpaca_timeframe(timeframe)
    if sym.is_crypto:
        from alpaca.data.historical import CryptoHistoricalDataClient
        from alpaca.data.requests import CryptoBarsRequest

        client = CryptoHistoricalDataClient(key, secret) if key and secret else CryptoHistoricalDataClient()
        raw = client.get_crypto_bars(
            CryptoBarsRequest(symbol_or_symbols=[sym.name], timeframe=tf, start=start)
        ).df
    else:
        if not (key and secret):
            raise market.DataError("Alpaca keys are needed for equity bars.")
        from alpaca.data.enums import DataFeed
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest

        client = StockHistoricalDataClient(key, secret)
        req = StockBarsRequest(symbol_or_symbols=[sym.name], timeframe=tf, start=start, feed=DataFeed.IEX)
        raw = client.get_stock_bars(req).df
    return _bars_frame(raw, sym.name).tail(limit)


async def fetch_intraday(
    sym: Symbol,
    timeframe: str = "1Hour",
    limit: int = 400,
    *,
    key: str | None = None,
    secret: str | None = None,
) -> pd.DataFrame:
    """Recent bars from Alpaca, oldest first. Only completed bars: the still-forming last bar is dropped."""
    df = await asyncio.to_thread(_fetch_alpaca_sync, sym, timeframe, limit + 1, key, secret)
    now = pd.Timestamp(datetime.now(UTC)).tz_localize(None)
    step = pd.Timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    return df[df.index + step <= now].tail(limit)


# Instructions aimed at a trading agent, on top of the research app's generic injection patterns.
_TRADER_INJECTION = re.compile(
    "|".join(
        f"(?:{p})"
        for p in [
            r"\bignore (all |any |the |your )?(rules|limits|risk|guardrails|stops?|instructions)\b",
            r"\b(disable|turn off|remove|bypass|override) (the |your |all )?"
            r"(stop|stops|stop-loss|kill switch|risk|limits?|kernel|guardrails)\b",
            r"\b(buy|sell|short) (\d[\d,]*|all|everything|max(imum)?)\s*(shares|units|coins|contracts|lots)?"
            r".{0,20}\b(now|immediately|at once)\b",
            r"\b(buy|sell) \d[\d,]{3,} (shares|units|coins)\b",
            r"\b(all[- ]in|max(imum)? leverage|use (full )?margin)\b",
            r"\b(ai|agents?|bots?|assistants?|models?)\b.{0,30}\bmust\b",
        ]
    ),
    re.IGNORECASE,
)


def looks_like_trader_injection(text: str) -> bool:
    return bool(_TRADER_INJECTION.search(text or ""))


def _news_item(
    headline: str | None, summary: str | None, source: str | None, date: str | None
) -> dict | None:
    from axiom.security import sanitize_untrusted

    h, bad1 = sanitize_untrusted(headline, 200)
    s, bad2 = sanitize_untrusted(summary, 280)
    if not h:
        return None
    flagged = bad1 or bad2 or looks_like_trader_injection(f"{h} {s}")
    return {
        "headline": f"[REDACTED: suspected prompt injection from {source or 'unknown source'}]"
        if flagged
        else h,
        "summary": "" if flagged else s,
        "source": source,
        "date": date,
        "injection_suspected": flagged,
        "excerpt": h[:80] if flagged else None,  # for the journal flag only; never shown to the model
    }


def _alpaca_news_sync(sym: Symbol, limit: int, hours: int, key: str, secret: str) -> list[dict]:
    from alpaca.data.historical.news import NewsClient
    from alpaca.data.requests import NewsRequest

    req = NewsRequest(
        symbols=sym.alpaca_position if sym.is_crypto else sym.name,
        start=datetime.now(UTC) - timedelta(hours=hours),
        limit=limit,
    )
    news = NewsClient(key, secret).get_news(req)
    out = []
    for a in news.data.get("news", [])[:limit]:
        item = _news_item(a.headline, a.summary, a.source, a.created_at.isoformat() if a.created_at else None)
        if item:
            out.append(item)
    return out


async def fetch_news(
    sym: Symbol, *, key: str | None = None, secret: str | None = None, limit: int = 8, hours: int = 48
) -> list[dict]:
    """Recent headlines, sanitized: anything that looks like an instruction is redacted and flagged.
    Alpaca News with keys; otherwise the research app's news fallback chain. Never raises."""
    try:
        if key and secret:
            return await asyncio.to_thread(_alpaca_news_sync, sym, limit, hours, key, secret)
        from axiom.data.news import get_news_sentiment

        res = await get_news_sentiment(
            sym.yahoo if sym.is_crypto else sym.name, days=max(1, hours // 24), limit=limit
        )
        out = []
        for a in res.get("items", []):
            item = _news_item(a.get("headline"), a.get("summary"), a.get("source"), a.get("date"))
            if item:
                item["injection_suspected"] = item["injection_suspected"] or bool(
                    a.get("injection_suspected")
                )
                out.append(item)
        return out
    except Exception:
        return []
