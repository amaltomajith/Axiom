"""SEC EDGAR (free, keyless): filing index + XBRL company facts + optional risk-factor excerpt."""

from __future__ import annotations

import html
import re
from typing import Any

import httpx

from axiom.config import get_settings
from axiom.security import sanitize_untrusted

from . import ratelimit
from .cache import get_cache
from .market import DataError, normalize_ticker

SEC_TTL = 24 * 3600
TICKER_MAP_TTL = 7 * 24 * 3600
MAX_DOC_BYTES = 6_000_000

# concept fallbacks in preference order (us-gaap taxonomy)
CONCEPTS: dict[str, list[tuple[str, str]]] = {
    "revenue": [
        ("RevenueFromContractWithCustomerExcludingAssessedTax", "USD"),
        ("Revenues", "USD"),
        ("SalesRevenueNet", "USD"),
    ],
    "operating_income": [("OperatingIncomeLoss", "USD")],
    "net_income": [("NetIncomeLoss", "USD")],
    "eps_diluted": [("EarningsPerShareDiluted", "USD/shares")],
    "total_assets": [("Assets", "USD")],
    "total_liabilities": [("Liabilities", "USD")],
    "equity": [("StockholdersEquity", "USD")],
    "cash": [("CashAndCashEquivalentsAtCarryingValue", "USD")],
    "long_term_debt": [("LongTermDebtNoncurrent", "USD"), ("LongTermDebt", "USD")],
    "operating_cash_flow": [("NetCashProvidedByUsedInOperatingActivities", "USD")],
}


async def _get_json(url: str) -> Any:
    await ratelimit.SEC.acquire()
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": get_settings().sec_user_agent}) as c:
        r = await c.get(url)
    if r.status_code == 404:
        raise DataError("SEC has no data for this company at that endpoint.")
    if r.status_code in (403, 429):
        raise DataError("SEC rejected the request (check SEC_USER_AGENT / rate limit).")
    r.raise_for_status()
    return r.json()


async def ticker_to_cik(ticker: str) -> tuple[str, str]:
    """Return (10-digit zero-padded CIK, company name)."""
    t = normalize_ticker(ticker)
    cache = get_cache()
    mapping = cache.get("sec:tickers")
    if mapping is None:
        raw = await _get_json("https://www.sec.gov/files/company_tickers.json")
        mapping = {v["ticker"].upper(): [v["cik_str"], v["title"]] for v in raw.values()}
        cache.set("sec:tickers", mapping, TICKER_MAP_TTL)
    if t not in mapping:
        raise DataError(f"{t} not found in SEC ticker list (ETFs/foreign issuers may be absent).")
    cik, name = mapping[t]
    return f"{int(cik):010d}", name


def _annual_series(facts: dict, concepts: list[tuple[str, str]]) -> list[dict]:
    """Annual (10-K, FY) observations for the first concept that has data, newest first."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for name, unit in concepts:
        entries = gaap.get(name, {}).get("units", {}).get(unit, [])
        rows: dict[str, dict] = {}
        for e in entries:
            if e.get("form") == "10-K" and e.get("fp") == "FY":
                prev = rows.get(e["end"])
                if prev is None or e["filed"] > prev["filed"]:
                    rows[e["end"]] = e
        if rows:
            return sorted(rows.values(), key=lambda e: e["end"], reverse=True)
    return []


def summarize_facts(facts: dict) -> dict:
    out: dict[str, Any] = {}
    for key, concepts in CONCEPTS.items():
        s = _annual_series(facts, concepts)
        if not s:
            continue
        latest = s[0]
        entry: dict[str, Any] = {"fy_end": latest["end"], "value": latest["val"]}
        if len(s) > 1 and s[1]["val"]:
            entry["prior_value"] = s[1]["val"]
            entry["yoy_pct"] = round((latest["val"] / s[1]["val"] - 1) * 100, 1)
        out[key] = entry
    ratios: dict[str, float] = {}
    v = lambda k: out.get(k, {}).get("value")  # noqa: E731
    if v("revenue") and v("net_income") is not None:
        ratios["net_margin_pct"] = round(v("net_income") / v("revenue") * 100, 1)
    if v("revenue") and v("operating_income") is not None:
        ratios["operating_margin_pct"] = round(v("operating_income") / v("revenue") * 100, 1)
    if v("equity") and v("total_liabilities") is not None and v("equity") > 0:
        ratios["liabilities_to_equity"] = round(v("total_liabilities") / v("equity"), 2)
    if v("operating_cash_flow") is not None and v("net_income"):
        ratios["cash_conversion"] = round(v("operating_cash_flow") / v("net_income"), 2)
    return {"annual_facts": out, "ratios": ratios}


def _latest_filings(sub: dict, cik: str) -> list[dict]:
    recent = sub.get("filings", {}).get("recent", {})
    rows = list(
        zip(
            recent.get("form", []),
            recent.get("filingDate", []),
            recent.get("reportDate", []),
            recent.get("accessionNumber", []),
            recent.get("primaryDocument", []),
            strict=False,
        )
    )
    picked: list[dict] = []
    seen: dict[str, int] = {}
    limits = {"10-K": 1, "10-Q": 1, "8-K": 3}
    for form, filed, report, acc, doc in rows:
        if form in limits and seen.get(form, 0) < limits[form]:
            seen[form] = seen.get(form, 0) + 1
            picked.append(
                {
                    "form": form,
                    "filed": filed,
                    "period": report,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}",
                }
            )
    return picked


_TAGS = re.compile(r"<[^>]+>")
_ITEM_1A = re.compile(r"item\s*1a\.?\s*[\-–—:]?\s*risk\s*factors", re.IGNORECASE)
_ITEM_1B = re.compile(r"item\s*1b\.?\s*[\-–—:]?\s*unresolved", re.IGNORECASE)


def extract_risk_factors(doc_html: str, max_chars: int = 1800) -> str | None:
    """Best-effort: pick the longest Item 1A..Item 1B span (skips the table of contents)."""
    text = html.unescape(_TAGS.sub(" ", doc_html))
    text = re.sub(r"\s+", " ", text)
    starts = [m.start() for m in _ITEM_1A.finditer(text)]
    ends = [m.start() for m in _ITEM_1B.finditer(text)]
    best = ""
    for s in starts:
        e = next((x for x in ends if x > s), None)
        span = text[s : e if e else s + 20000]
        if len(span) > len(best):
            best = span
    if len(best) < 500:
        return None
    cleaned, suspicious = sanitize_untrusted(best, max_chars)
    return None if suspicious else cleaned  # drop the whole excerpt rather than show an injection


async def _fetch_doc_head(url: str) -> str:
    await ratelimit.SEC.acquire()
    chunks, size = [], 0
    async with (
        httpx.AsyncClient(
            timeout=60, headers={"User-Agent": get_settings().sec_user_agent}, follow_redirects=True
        ) as c,
        c.stream("GET", url) as r,
    ):
        r.raise_for_status()
        async for chunk in r.aiter_bytes():
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_DOC_BYTES:
                break
    return b"".join(chunks).decode("utf-8", errors="ignore")


async def get_filing_summary(ticker: str, include_risk_factors: bool = False) -> dict:
    t = normalize_ticker(ticker)
    cache = get_cache()
    key = f"sec:summary:{t}:{int(include_risk_factors)}"
    hit = cache.get(key)
    if hit is not None:
        return hit

    cik, name = await ticker_to_cik(t)
    sub = await _get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
    facts = await _get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    filings = _latest_filings(sub, cik)

    facts_summary = summarize_facts(facts)
    fy_ends = [v["fy_end"] for v in facts_summary["annual_facts"].values() if v.get("fy_end")]
    result: dict[str, Any] = {
        "meta": {
            "tool": "fetch_sec_filing_summary",
            "ticker": t,
            "as_of": max(fy_ends) if fy_ends else None,  # latest fiscal year end covered
            "provider": "SEC EDGAR",
        },
        "ticker": t,
        "company": name,
        "cik": cik,
        "source": "SEC EDGAR (XBRL company facts, annual 10-K figures)",
        "recent_filings": filings,
        **facts_summary,
        "untrusted_content": include_risk_factors,
    }
    if include_risk_factors:
        tenk = next((f for f in filings if f["form"] == "10-K"), None)
        try:
            excerpt = extract_risk_factors(await _fetch_doc_head(tenk["url"])) if tenk else None
        except httpx.HTTPError:
            excerpt = None
        result["risk_factors_excerpt"] = excerpt
    cache.set(key, result, SEC_TTL)
    return result
