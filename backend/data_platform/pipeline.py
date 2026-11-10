"""One ELT run: load raw, rebuild staging, run data-quality checks, and only if no critical check failed,
rebuild the marts. Logs one JSON line per step, so a scheduler's log shows the start, rows per table, check
results and duration."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import yaml

from axiom.db import Db

from . import PKG_DIR
from .config import Config, Layout
from .dq import DqSummary, run_checks, write_results
from .extract import Batch, TableLoad, load_table, source_count
from .models import SqlModel, models
from .warehouse import Warehouse

__all__ = ["RunReport", "build", "models", "run"]

log = logging.getLogger("data_platform")

LAYER_DESCRIPTIONS = {
    "raw": "Axiom operational tables loaded as-is by batch load jobs, plus load metadata. Append-only change log.",
    "staging": "Typed, deduplicated tables: one row per primary key (newest version). Rebuilt each run.",
    "mart": "Analytics tables for dashboards (scorecard, tool latency, LLM usage, price indicators) and dq_results.",
}


def event(name: str, **fields: Any) -> None:
    log.info(json.dumps({"event": name, **fields}, default=str))


@dataclass
class RunReport:
    env: str
    source: str
    batch_id: str
    loads: list[TableLoad] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)
    built: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    reconciliation: dict[str, dict[str, int]] = field(default_factory=dict)
    dq_failed_critical: list[str] = field(default_factory=list)
    dq_warnings: list[str] = field(default_factory=list)
    price_failures: list[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def reconciled(self) -> bool:
        return bool(self.reconciliation) and all(
            v["source"] == v["warehouse"] for v in self.reconciliation.values()
        )

    @property
    def ok(self) -> bool:
        return not self.dq_failed_critical


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
        range_partition_field=model.partition_by,
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


def apply_column_docs(wh: Warehouse, layout: Layout) -> int:
    """Write column descriptions from column_docs.yaml onto every documented table that exists."""
    docs = yaml.safe_load((PKG_DIR / "column_docs.yaml").read_text(encoding="utf-8"))
    n = 0
    for layer, tables in docs.items():
        for table, cols in tables.items():
            fq = layout.fq(layer, table)
            if wh.table_exists(fq):
                n += wh.describe_columns(fq, cols)
    return n


def _build_layer(wh: Warehouse, layout: Layout, layer: str, rep: RunReport) -> None:
    for m in models(layer):
        n = build(wh, layout, m)
        if n is None:
            rep.skipped.append(f"{layer}.{m.name}")
        else:
            rep.built[f"{layer}.{m.name}"] = n


def _record_dq(rep: RunReport, dq: DqSummary) -> None:
    label = "{0.check_name}:{0.table_name} ({0.detail})".format
    rep.dq_failed_critical = [label(r) for r in dq.critical_failures]
    rep.dq_warnings = [label(r) for r in dq.warnings]
    for r in dq.results:
        if r.check_name == "row_count_reconciliation" and r.table_name in rep.source_counts:
            n = rep.source_counts[r.table_name]
            rep.reconciliation[r.table_name] = {"source": n, "warehouse": n + int(r.observed or 0)}


def run(
    wh: Warehouse,
    layout: Layout,
    cfg: Config,
    db: Db,
    *,
    source_label: str,
    with_prices: bool = True,
    transform: bool = True,
    now_sql: str | None = None,
) -> RunReport:
    t0 = time.monotonic()
    batch = Batch.new(source_label)
    rep = RunReport(layout.env, source_label, batch.batch_id)
    event("run_start", env=layout.env, project=layout.project, source=source_label, batch_id=batch.batch_id)

    for layer in ("raw", "staging", "mart"):
        wh.ensure_dataset(layout.dataset(layer), LAYER_DESCRIPTIONS[layer])

    for spec in cfg.tables.values():
        tl = load_table(wh, layout, spec, db, batch, cfg.lookback_seconds)
        rep.source_counts[spec.name] = source_count(
            db, spec.name
        )  # right after extraction, for reconciliation
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
        _build_layer(wh, layout, "staging", rep)

        t1 = time.monotonic()
        dq = run_checks(wh, layout, rep.source_counts, **({"now_sql": now_sql} if now_sql else {}))
        write_results(wh, layout, dq, batch)
        _record_dq(rep, dq)
        event(
            "dq_checked",
            checks=len(dq.results),
            passed=sum(r.passed for r in dq.results),
            critical_failures=rep.dq_failed_critical,
            warnings=rep.dq_warnings,
            skipped=dq.skipped,
            seconds=round(time.monotonic() - t1, 2),
        )

        if dq.ok:
            _build_layer(wh, layout, "mart", rep)
        else:
            event("marts_not_built", reason="critical data-quality failure", failures=rep.dq_failed_critical)
        event("column_docs_applied", columns_updated=apply_column_docs(wh, layout))

    rep.seconds = round(time.monotonic() - t0, 2)
    event(
        "run_end",
        ok=rep.ok,
        seconds=rep.seconds,
        rows_loaded=sum(x.loaded for x in rep.loads),
        reconciled=rep.reconciled,
    )
    return rep
