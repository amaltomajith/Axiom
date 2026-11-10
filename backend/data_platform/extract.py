"""Extract from Axiom's operational database (SQLite or Postgres via axiom.db.Db) and load into raw.

Raw is an append-only change log: one row per (primary key, watermark) version. Staging keeps the newest
version per key. A re-run loads nothing new, so neither layer gains duplicates.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from axiom.db import Db

from .config import REDACTIONS, Layout, TableSpec
from .warehouse import Warehouse

META_SCHEMA = [("_loaded_at", "TIMESTAMP"), ("_source", "STRING"), ("_batch_id", "STRING")]
_CAST = {"FLOAT64": float, "INT64": int, "STRING": str, "DATE": str}


@dataclass(frozen=True)
class Batch:
    source: str  # e.g. "neon" or "sqlite:synthetic"; never a connection string
    batch_id: str
    loaded_at: str

    @classmethod
    def new(cls, source: str) -> Batch:
        now = datetime.now(UTC)
        return cls(source, now.strftime("%Y%m%dT%H%M%S%fZ"), now.isoformat())


def _coerce(row: dict[str, Any], spec: TableSpec) -> dict[str, Any]:
    out = {}
    for col, typ in spec.columns.items():
        v = row.get(col)
        if v is not None and col in spec.redact:
            v = REDACTIONS[spec.redact[col]](v)
        out[col] = None if v is None else _CAST[typ](v)
    return out


def raw_schema(spec: TableSpec) -> list[tuple[str, str]]:
    wm = [("_wm", "FLOAT64")] if spec.mode == "incremental" else []
    return [*spec.columns.items(), *wm, *META_SCHEMA]


def read_source(db: Db, spec: TableSpec, since: float | None) -> list[dict[str, Any]]:
    cols = ", ".join(spec.columns)
    if spec.mode == "snapshot":
        q, args = f"SELECT {cols} FROM {spec.name}", ()
    else:
        q = f"SELECT {cols}, {spec.watermark} AS _wm FROM {spec.name}"
        q, args = (q, ()) if since is None else (q + f" WHERE {spec.watermark} >= ?", (since,))
    with db.connect() as c:
        rows = [dict(r) for r in c.execute(q, args).fetchall()]
    out = []
    for r in rows:
        x = _coerce(r, spec)
        if spec.mode == "incremental":
            x["_wm"] = float(r["_wm"])
        out.append(x)
    return out


def source_count(db: Db, table: str) -> int:
    with db.connect() as c:
        return int(c.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])


@dataclass(frozen=True)
class TableLoad:
    table: str
    mode: str
    extracted: int
    loaded: int
    seconds: float


def load_table(
    wh: Warehouse, layout: Layout, spec: TableSpec, db: Db, batch: Batch, lookback_seconds: float
) -> TableLoad:
    t0 = time.monotonic()
    dest = layout.fq("raw", spec.name)
    desc = f"Raw copy of Axiom's `{spec.name}` table ({spec.mode} load). Source types; _-columns are load metadata."
    meta = {"_loaded_at": batch.loaded_at, "_source": batch.source, "_batch_id": batch.batch_id}

    if spec.mode == "snapshot":
        rows = read_source(db, spec, None)
        res = wh.load_rows(
            dest, [{**r, **meta} for r in rows], raw_schema(spec), truncate=True, description=desc
        )
        return TableLoad(spec.name, spec.mode, len(rows), res.rows, time.monotonic() - t0)

    newest = wh.max_watermark(dest)
    since = None if newest is None else newest - lookback_seconds
    rows = read_source(db, spec, since)
    have = set() if since is None else wh.versions_since(dest, spec.pk, since)
    fresh = [r for r in rows if (*(r[c] for c in spec.pk), r["_wm"]) not in have]
    res = wh.load_rows(
        dest, [{**r, **meta} for r in fresh], raw_schema(spec), truncate=False, description=desc
    )
    return TableLoad(spec.name, spec.mode, len(rows), res.rows, time.monotonic() - t0)
