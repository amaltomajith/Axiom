"""Data-quality checks: SQL files in sql/dq/, run after staging is rebuilt and before marts are.

Each file returns rows of (check_name, table_name, observed, passed, detail) and declares
`-- severity: critical|warn`. A critical failure stops the pipeline before the marts, so bad data never
reaches a dashboard; a warning is logged and recorded. Every result row is appended to mart.dq_results
with a load job (the sandbox has no DML).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .config import Layout
from .extract import Batch
from .models import SqlModel, models
from .warehouse import Warehouse

SEVERITIES = ("critical", "warn")
NOW = "CURRENT_TIMESTAMP()"
RESULT_SCHEMA = [
    ("run_at", "TIMESTAMP"),
    ("batch_id", "STRING"),
    ("env", "STRING"),
    ("check_name", "STRING"),
    ("table_name", "STRING"),
    ("severity", "STRING"),
    ("passed", "BOOL"),
    ("observed", "FLOAT64"),
    ("detail", "STRING"),
]


@dataclass(frozen=True)
class CheckResult:
    check_name: str
    table_name: str
    severity: str
    passed: bool
    observed: float | None
    detail: str


@dataclass(frozen=True)
class DqSummary:
    results: list[CheckResult]
    skipped: list[str]

    @property
    def critical_failures(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed and r.severity == "critical"]

    @property
    def warnings(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed and r.severity == "warn"]

    @property
    def ok(self) -> bool:
        return not self.critical_failures


def source_counts_literal(counts: dict[str, int]) -> str:
    """A BigQuery ARRAY<STRUCT> literal, so reconciliation can run as plain SQL."""
    if not counts:
        return "ARRAY<STRUCT<table_name STRING, n INT64>>[]"
    items = ", ".join(
        f"STRUCT({json.dumps(t)} AS table_name, {int(n)} AS n)" for t, n in sorted(counts.items())
    )
    return f"[{items}]"


def render(model: SqlModel, layout: Layout, source_counts: dict[str, int], now_sql: str = NOW) -> str:
    sql = layout.render(model.sql).replace("${now}", now_sql)
    return sql.replace("${source_counts}", source_counts_literal(source_counts))


def check_models() -> list[SqlModel]:
    ms = models("dq")
    bad = [m.path.name for m in ms if m.severity not in SEVERITIES]
    if bad:
        raise ValueError(f"dq files need '-- severity: critical|warn': {bad}")
    return ms


def run_checks(wh: Warehouse, layout: Layout, source_counts: dict[str, int], now_sql: str = NOW) -> DqSummary:
    results, skipped = [], []
    for m in check_models():
        if any(not wh.table_exists(layout.render(r)) for r in m.requires):
            skipped.append(m.name)
            continue
        for row in wh.query(render(m, layout, source_counts, now_sql)):
            results.append(
                CheckResult(
                    check_name=row["check_name"],
                    table_name=row["table_name"],
                    severity=m.severity or "critical",
                    passed=bool(row["passed"]),
                    observed=None if row["observed"] is None else float(row["observed"]),
                    detail=row["detail"] or "",
                )
            )
    return DqSummary(results, skipped)


def write_results(wh: Warehouse, layout: Layout, summary: DqSummary, batch: Batch) -> int:
    rows = [
        {"run_at": batch.loaded_at, "batch_id": batch.batch_id, "env": layout.env, **asdict(r)}
        for r in summary.results
    ]
    return wh.load_rows(
        layout.fq("mart", "dq_results"),
        rows,
        RESULT_SCHEMA,
        truncate=False,
        description="One row per data-quality check result per pipeline run (append-only).",
    ).rows
