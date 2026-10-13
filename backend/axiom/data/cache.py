"""Tiny TTL cache for JSON-serialisable values (shared by MCP server and API).

SQLite locally; the same Postgres as the Store when DATABASE_URL is set, so every serverless instance
shares one market-data and LLM-response cache (that sharing is what protects the free LLM quota).
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from axiom.config import get_settings
from axiom.db import Db, upsert_sql


class TTLCache:
    def __init__(self, path: Path | None = None, url: str | None = None):
        settings = get_settings()
        url = url if url is not None else (None if path else settings.database_url)
        self.db = Db(url=url, path=None if url else Path(path or settings.cache_db))
        self.path = self.db.path
        self.db.init_schema(
            "CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL, expires REAL NOT NULL)"
        )

    @property
    def ident(self) -> str:
        return self.db.ident

    def get(self, key: str) -> Any | None:
        with self.db.connect() as c:
            row = c.execute("SELECT v, expires FROM kv WHERE k = ?", (key,)).fetchone()
        if row is None or row["expires"] < time.time():
            return None
        return json.loads(row["v"])

    def set(self, key: str, value: Any, ttl: float) -> None:
        with self.db.connect() as c:
            c.execute(
                upsert_sql("kv", ["k", "v", "expires"], "k"), (key, json.dumps(value), time.time() + ttl)
            )
            if random.random() < 0.02:  # keep a size-limited free Postgres from filling with dead rows
                c.execute("DELETE FROM kv WHERE expires < ?", (time.time(),))

    def clear(self, prefix: str = "") -> int:
        with self.db.connect() as c:
            return c.execute("DELETE FROM kv WHERE k LIKE ?", (prefix + "%",)).rowcount

    async def get_or_set(self, key: str, ttl: float, producer: Callable[[], Awaitable[Any]]) -> Any:
        hit = self.get(key)
        if hit is not None:
            return hit
        value = await producer()
        self.set(key, value, ttl)
        return value


_cache: TTLCache | None = None


def get_cache() -> TTLCache:
    global _cache
    s = get_settings()
    ident = s.database_url or str(Path(s.cache_db))
    if _cache is None or _cache.ident != ident:
        _cache = TTLCache()
    return _cache
