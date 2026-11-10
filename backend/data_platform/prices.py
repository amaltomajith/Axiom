"""Daily bars for the tickers Axiom has researched, fetched with Axiom's own market-data code.

The provider (yfinance by default) revises adjusted history after splits and dividends, so each run
replaces the raw window instead of appending to it. The data goes to a private dataset only: no free
source here clearly permits redistribution, so it must never be published or committed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from axiom.data import market
from axiom.db import Db

from .config import Config, Layout
from .extract import META_SCHEMA, Batch
from .warehouse import LoadResult, Warehouse

log = logging.getLogger("data_platform")


def tickers_to_fetch(db: Db, benchmark: str) -> list[str]:
    with db.connect() as c:
        rows = c.execute("SELECT ticker FROM theses UNION SELECT ticker FROM watchlist").fetchall()
    return sorted({r["ticker"] for r in rows} | {benchmark})


async def fetch_bars(tickers: list[str], bars: int) -> tuple[list[dict[str, Any]], list[str]]:
    rows, failed = [], []
    for t in tickers:
        try:
            df, provider = await market.fetch_ohlcv(t, bars)
        except market.DataError as e:
            log.warning("price fetch failed for %s: %s", t, e)
            failed.append(t)
            continue
        for ts, r in df.iterrows():
            rows.append(
                {
                    "ticker": t,
                    "date": ts.strftime("%Y-%m-%d"),
                    **{
                        k: None if r[k] != r[k] else float(r[k])
                        for k in ("open", "high", "low", "close", "volume")
                    },
                    "provider": provider,
                }
            )
    return rows, failed


def load_prices(
    wh: Warehouse, layout: Layout, cfg: Config, db: Db, batch: Batch
) -> tuple[LoadResult, list[str]]:
    p = cfg.prices
    tickers = tickers_to_fetch(db, p["benchmark"])
    rows, failed = asyncio.run(fetch_bars(tickers, int(p["bars"])))
    target = layout.fq("raw", "price_bars")
    if failed and wh.table_exists(target):
        # Replace the window only on a complete fetch: a provider outage must not wipe good history.
        log.warning(
            "price load skipped, previous window kept: %d of %d tickers failed", len(failed), len(tickers)
        )
        return LoadResult(target, 0), failed
    meta = {"_loaded_at": batch.loaded_at, "_source": batch.source, "_batch_id": batch.batch_id}
    schema = [*p["columns"].items(), *META_SCHEMA]
    res = wh.load_rows(
        target,
        [{**r, **meta} for r in rows],
        schema,
        truncate=True,
        description="Daily OHLCV from Axiom's market-data layer (yfinance/Twelve Data). Private: not licensed for redistribution.",
    )
    return res, failed
