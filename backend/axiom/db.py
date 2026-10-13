"""One tiny database seam for SQLite (local, zero setup) and Postgres (deployed, e.g. Neon free tier).

Callers write portable SQL with `?` placeholders and `ON CONFLICT` upserts. Postgres gets the same
statements with `%s`, and a connection per call (serverless instances come and go, so there is nothing
worth pooling). Rows are dict-like on both backends.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_REAL = re.compile(r"\bREAL\b")
_SCHEMA_LOCK_ID = 727_001  # arbitrary; serialises concurrent cold starts creating tables


def upsert_sql(table: str, cols: list[str], pk: str) -> str:
    """`INSERT ... ON CONFLICT (pk) DO UPDATE`, valid on both SQLite (>=3.24) and Postgres."""
    sets = ", ".join(f"{c}=excluded.{c}" for c in cols if c != pk)
    return (
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
        f"ON CONFLICT ({pk}) DO UPDATE SET {sets}"
    )


def is_postgres_url(url: str | None) -> bool:
    return bool(url) and url.split(":", 1)[0] in ("postgres", "postgresql")  # type: ignore[union-attr]


class _PgConn:
    """Gives psycopg the small slice of the sqlite3 connection API that Store and TTLCache use."""

    def __init__(self, conn: Any):
        self._c = conn

    def execute(self, sql: str, args: tuple | list = ()) -> Any:
        # Our SQL never contains a literal '?' or '%', so a plain replace is safe.
        # bool -> int: booleans live in INTEGER columns (SQLite stores them that way natively).
        a = [int(x) if isinstance(x, bool) else x for x in args]
        return self._c.execute(sql.replace("?", "%s") if a else sql, a or None)

    def executescript(self, script: str) -> None:
        self._c.execute(script)


class Db:
    def __init__(self, *, url: str | None = None, path: Path | None = None):
        self.url = url if is_postgres_url(url) else None
        self.path = Path(path) if path else None
        self.postgres = self.url is not None
        self._lock = threading.Lock()
        if not self.postgres:
            if self.path is None:
                raise ValueError("Db needs a Postgres url or a SQLite path")
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def ident(self) -> str:
        return self.url or str(self.path)

    def schema(self, ddl: str) -> str:
        """Adapt SQLite-flavoured DDL: REAL is only 4 bytes on Postgres, too small for timestamps."""
        return _REAL.sub("DOUBLE PRECISION", ddl) if self.postgres else ddl

    def init_schema(self, ddl: str) -> None:
        ddl = self.schema(ddl)
        with self.connect() as c:
            if self.postgres:
                c.executescript(f"SELECT pg_advisory_xact_lock({_SCHEMA_LOCK_ID});{ddl}")
            else:
                c.executescript(ddl)

    @contextmanager
    def connect(self) -> Iterator[Any]:
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row

            # prepare_threshold=None: poolers in transaction mode (Neon's -pooler host) reject prepared statements.
            raw = psycopg.connect(self.url, row_factory=dict_row, prepare_threshold=None, connect_timeout=10)
            try:
                yield _PgConn(raw)
                raw.commit()
            except BaseException:
                raw.rollback()
                raise
            finally:
                raw.close()
            return
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with self._lock:
                yield conn
                conn.commit()
        finally:
            conn.close()
