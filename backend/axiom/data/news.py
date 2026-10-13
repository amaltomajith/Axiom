"""Company news (Finnhub if keyed, else yfinance) + a transparent lexicon sentiment baseline.

Finnhub's /news-sentiment is premium-only, so we compute a simple, auditable score ourselves and
label it low-confidence. Headlines are sanitised and injection-flagged before reaching any LLM.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta

import httpx
from defusedxml import ElementTree as ET

from axiom.config import get_settings
from axiom.security import sanitize_untrusted

from . import ratelimit
from .cache import get_cache
from .market import DataError, normalize_ticker

NEWS_TTL = 15 * 60

POSITIVE = {
    "beat", "beats", "surge", "surges", "soar", "soars", "upgrade", "upgraded", "growth", "record",
    "strong", "gain", "gains", "profit", "profits", "rally", "outperform", "raises", "raised",
    "buyback", "expands", "wins", "approval", "approved", "exceeds", "jump", "jumps", "boost",
}  # fmt: skip
NEGATIVE = {
    "miss", "misses", "fall", "falls", "plunge", "plunges", "downgrade", "downgraded", "decline",
    "loss", "losses", "weak", "drop", "drops", "crash", "cut", "cuts", "lawsuit", "investigation",
    "recall", "probe", "fraud", "layoffs", "warning", "warns", "slump", "sued", "bankruptcy",
}  # fmt: skip
NEGATORS = {"not", "no", "never", "without", "fails", "failed", "unlikely"}
_TOKEN = re.compile(r"[a-z']+")


def lexicon_score(text: str) -> float:
    """Score in [-1, 1]: (pos - neg) / (pos + neg), flipping a hit preceded by a negator."""
    tokens = _TOKEN.findall(text.lower())
    pos = neg = 0
    for i, tok in enumerate(tokens):
        if tok in POSITIVE or tok in NEGATIVE:
            negated = any(t in NEGATORS for t in tokens[max(0, i - 3) : i])
            is_pos = (tok in POSITIVE) != negated
            pos += is_pos
            neg += not is_pos
    return 0.0 if pos + neg == 0 else (pos - neg) / (pos + neg)


def _label(score: float) -> str:
    return "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"


async def _finnhub(ticker: str, days: int, key: str) -> list[dict]:
    await ratelimit.FINNHUB.acquire()
    end = datetime.now(UTC).date()
    start = end - timedelta(days=days)
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            "https://finnhub.io/api/v1/company-news",
            params={"symbol": ticker, "from": start.isoformat(), "to": end.isoformat(), "token": key},
        )
    body = r.json()
    if not isinstance(body, list):
        raise DataError(f"Finnhub: {body}")
    return [
        {
            "headline": a.get("headline"),
            "summary": a.get("summary"),
            "source": a.get("source"),
            "url": a.get("url"),
            "date": datetime.fromtimestamp(a.get("datetime", 0), UTC).strftime("%Y-%m-%d"),
        }
        for a in body
    ]


async def _google_news_rss(ticker: str, days: int) -> list[dict]:
    """Keyless fallback. Titles look like 'Headline - Publisher'."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(
            "https://news.google.com/rss/search",
            params={"q": f"{ticker} stock when:{days}d", "hl": "en-US", "gl": "US", "ceid": "US:en"},
            headers={"User-Agent": "Mozilla/5.0"},
        )
    r.raise_for_status()
    out = []
    for item in ET.fromstring(r.content).iter("item"):
        title = item.findtext("title") or ""
        headline, _, publisher = title.rpartition(" - ")
        pub = item.findtext("pubDate") or ""
        try:
            date = datetime.strptime(pub[:16], "%a, %d %b %Y").strftime("%Y-%m-%d")
        except ValueError:
            date = ""
        out.append(
            {
                "headline": headline or title,
                "summary": "",
                "source": publisher or (item.findtext("source") or ""),
                "url": item.findtext("link"),
                "date": date,
            }
        )
    return out


def _yfinance_news(ticker: str) -> list[dict]:
    import yfinance as yf

    out = []
    for item in yf.Ticker(ticker).news or []:
        c = item.get("content", item)
        out.append(
            {
                "headline": c.get("title"),
                "summary": c.get("summary") or "",
                "source": (c.get("provider") or {}).get("displayName") or c.get("publisher"),
                "url": (c.get("canonicalUrl") or {}).get("url") or c.get("link"),
                "date": (c.get("pubDate") or "")[:10],
            }
        )
    return out


async def get_news_sentiment(ticker: str, days: int = 7, limit: int = 8) -> dict:
    t = normalize_ticker(ticker)
    days = max(1, min(days, 30))
    cache = get_cache()
    key = f"news:{t}:{days}"
    raw = cache.get(key)
    provider = "finnhub"
    if raw is None:
        raw = []
        key_ = get_settings().finnhub_api_key
        if key_:
            try:
                raw = await _finnhub(t, days, key_)
            except (DataError, httpx.HTTPError):
                raw = []
        if not raw:
            provider = "google_news_rss"
            try:
                raw = await _google_news_rss(t, days)
            except Exception:
                raw = []
        if not raw:
            provider = "yfinance"
            try:
                raw = await asyncio.to_thread(_yfinance_news, t)
            except Exception:
                raw = []
        if not raw:
            raise DataError(f"No news source returned articles for {t}.")
        cache.set(key, {"provider": provider, "items": raw}, NEWS_TTL)
    else:
        provider, raw = raw["provider"], raw["items"]

    items, flagged = [], 0
    for a in raw[:limit]:
        headline, bad1 = sanitize_untrusted(a.get("headline"), 200)
        summary, bad2 = sanitize_untrusted(a.get("summary"), 280)
        if not headline:
            continue
        suspicious = bad1 or bad2
        flagged += suspicious
        if suspicious:
            # Defence in depth: the model never sees text that looks like an instruction aimed at it.
            headline = f"[REDACTED: suspected prompt injection in a headline from {a.get('source') or 'unknown source'}]"
            summary = ""
        score = 0.0 if suspicious else lexicon_score(f"{headline}. {summary}")
        items.append(
            {
                "headline": headline,
                "summary": summary,
                "source": a.get("source"),
                "date": a.get("date"),
                "lexicon_score": round(score, 2),
                "label": _label(score),
                "injection_suspected": suspicious,
            }
        )

    scores = [i["lexicon_score"] for i in items if not i["injection_suspected"]]
    net = sum(scores) / len(scores) if scores else 0.0
    dates = [i["date"] for i in items if i.get("date")]
    return {
        "meta": {
            "tool": "get_company_news_sentiment",
            "ticker": t,
            "as_of": max(dates) if dates else None,
            "provider": provider,
        },
        "ticker": t,
        "provider": provider,
        "n_articles": len(items),
        "net_sentiment": round(net, 2),
        "net_label": _label(net),
        "sentiment_method": "keyword lexicon with negation; low-confidence baseline, read headlines",
        "untrusted_content": True,
        "injection_flagged": flagged,
        "items": items,
    }
