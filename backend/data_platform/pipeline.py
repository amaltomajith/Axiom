"""One ELT run: extract + load raw, rebuild staging and marts, reconcile row counts. Logs one JSON line per
step so a scheduler's log shows start, rows per table, checks and duration."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from axiom.db import Db

from . import SQL_DIR
from .config import Config, Layout
from .extract import Batch, TableLoad, load_table, source_count
from .warehouse import Warehouse

log = logging.getLogger("data_platform")

LAYER_DESCRIPTIONS = {
    "raw": "Axiom operational tables loaded as-is by batch load jobs, plus load metadata. Append-only change log.",
    "staging": "Typed, deduplicated tables: one row per primary key (newest version). Rebuilt each run.",
    "mart": "Analytics tables for dashboards: scorecard, tool latency, LLM usage, price indicators.",
}

_DIRECTIVE = re.compile(r"^--\s*(description|requires|partition_by|cluster_by):\s*(.+?)\s*$", re.M)


def event(name: str, **fields: Any) -> None:
    log.info(json.dumps({"event": name, **fields}, default=str))


@dataclass(frozen=True)
class SqlModel:
    """A .sql file whose result becomes a table. Header comments carry its metadata."""

    path: Path
    layer: str
    name: str
    sql: str
    description: str = ""
    requires: list[str] = field(default_factory=list)
    partition_by: str | None = None
    cluster_by: list[str] = field(default_factory=list)

    @classmethod
    def read(cls, path: Path, layer: str) -> SqlModel:
        sql = path.read_text(encoding="utf-8")
        meta: dict[str, list[str]] = {}
        for k, v in _DIRECTIVE.findall(sql):
            meta.setdefault(k, []).append(v)
        return cls(
            path=path,
            layer=layer,
            name=re.sub(r"^\d+_", "", path.stem),
            sql=sql,
            description=" ".join(meta.get("description", [])),
            requires=meta.get("requires", []),
            partition_by=(meta.get("partition_by") or [None])[0],
            cluster_by=[c.strip() for v in meta.get("cluster_by", []) for c in v.split(",")],
        )


def models(layer: str) -> list[SqlModel]:
    return [SqlModel.read(p, layer) for p in sorted((SQL_DIR / layer).glob("*.sql"))]


@dataclass
class RunReport:
    env: str
    source: str
    batch_id: str
    loads: list[TableLoad] = field(default_factory=list)
    built: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    reconciliation: dict[str, dict[str, int]] = field(default_factory=dict)
    price_failures: list[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def reconciled(self) -> bool:
        return all(v["source"] == v["warehouse"] for v in self.reconciliation.values())


def build(wh: Warehouse, layout: Layout, model: SqlModel) -> int | None:
    missing = [r for r in (layout.render(x) for x in model.requires) if not wh.table_exists(r)]
    if missing:
        event("model_skipped", model=f"{model.layer}.{model.name}", missing=missing)
        return None
    t0 = time.monotonic()
    res = wh.query_to_table(
        layout.render(model.sql),
        layout.fq(model.layer, model.name),
        description=model.description,
        partition_field=model.partition_by,
        cluster_fields=model.cluster_by or None,
    )
    event(
        "model_built",
        model=f"{model.layer}.{model.name}",
        rows=res.rows,
        bytes_processed=res.bytes,
        seconds=round(time.monotonic() - t0, 2),
    )
    return res.rows


def run(
    wh: Warehouse,
    layout: Layout,
    cfg: Config,
    db: Db,
    *,
    source_label: str,
    with_prices: bool = True,
    transform: bool = True,
) -> RunReport:
    t0 = time.monotonic()
    batch = Batch.new(source_label)
    rep = RunReport(layout.env, source_label, batch.batch_id)
    event("run_start", env=layout.env, project=layout.project, source=source_label, batch_id=batch.batch_id)

    for layer in ("raw", "staging", "mart"):
        wh.ensure_dataset(layout.dataset(layer), LAYER_DESCRIPTIONS[layer])

    for spec in cfg.tables.values():
        tl = load_table(wh, layout, spec, db, batch, cfg.lookback_seconds)
        rep.loads.append(tl)
        event(
            "table_loaded", **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in asdict(tl).items()}
        )

    if with_prices and cfg.prices:
        from .prices import load_prices

        t1 = time.monotonic()
        res, failed = load_prices(wh, layout, cfg, db, batch)
        rep.price_failures = failed
        event("prices_loaded", rows=res.rows, failed_tickers=failed, seconds=round(time.monotonic() - t1, 2))

    if transform:
        for layer in ("staging", "mart"):
            for m in models(layer):
                n = build(wh, layout, m)
                if n is None:
                    rep.skipped.append(f"{layer}.{m.name}")
                else:
                    rep.built[f"{layer}.{m.name}"] = n

        for spec in cfg.tables.values():
            target = layout.fq("raw" if spec.redact else "staging", spec.name)
            rep.reconciliation[spec.name] = {
                "source": source_count(db, spec.name),
                "warehouse": wh.count(target),
            }
        event("reconciled", ok=rep.reconciled, tables=rep.reconciliation)

    rep.seconds = round(time.monotonic() - t0, 2)
    event(
        "run_end",
        seconds=rep.seconds,
        rows_loaded=sum(x.loaded for x in rep.loads),
        reconciled=rep.reconciled,
    )
    return rep
