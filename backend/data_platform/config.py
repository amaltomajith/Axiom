"""Typed view of tables.yaml plus the dataset layout for an environment."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import PKG_DIR

LAYERS = ("raw", "staging", "mart")
REDACTIONS = {"before_colon": lambda v: str(v).split(":", 1)[0]}


@dataclass(frozen=True)
class TableSpec:
    name: str
    mode: str  # incremental | snapshot
    pk: list[str]
    columns: dict[str, str]
    watermark: str | None = None
    redact: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in ("incremental", "snapshot"):
            raise ValueError(f"{self.name}: mode must be incremental or snapshot, got {self.mode!r}")
        if self.mode == "incremental" and not self.watermark:
            raise ValueError(f"{self.name}: incremental tables need a watermark")
        missing = [c for c in self.pk if c not in self.columns]
        if missing:
            raise ValueError(f"{self.name}: pk columns {missing} not in columns")
        unknown = {c: r for c, r in self.redact.items() if c not in self.columns or r not in REDACTIONS}
        if unknown:
            raise ValueError(f"{self.name}: bad redact rules {unknown} (rules: {sorted(REDACTIONS)})")


@dataclass(frozen=True)
class Config:
    tables: dict[str, TableSpec]
    lookback_seconds: float
    prices: dict[str, Any] = field(default_factory=dict)


def load_config(path: Path | None = None) -> Config:
    raw = yaml.safe_load((path or PKG_DIR / "tables.yaml").read_text(encoding="utf-8"))
    tables = {
        name: TableSpec(
            name=name,
            mode=t["mode"],
            pk=list(t["pk"]),
            columns=dict(t["columns"]),
            watermark=t.get("watermark"),
            redact=dict(t.get("redact") or {}),
        )
        for name, t in raw["tables"].items()
    }
    return Config(
        tables=tables, lookback_seconds=float(raw.get("lookback_seconds", 0)), prices=raw.get("prices", {})
    )


@dataclass(frozen=True)
class Layout:
    """Dataset names for one environment: `prod` -> axiom_raw/axiom_staging/axiom_mart, `dev` -> axiomdev_*."""

    project: str
    env: str

    def dataset(self, layer: str) -> str:
        if layer not in LAYERS:
            raise ValueError(layer)
        prefix = "axiom" if self.env == "prod" else f"axiom{self.env}"
        return f"{prefix}_{layer}"

    def fq(self, layer: str, table: str = "") -> str:
        base = f"{self.project}.{self.dataset(layer)}"
        return f"{base}.{table}" if table else base

    def render(self, sql: str) -> str:
        """SQL files reference `${raw}`, `${staging}`, `${mart}`; replace them with project.dataset."""
        for layer in LAYERS:
            sql = sql.replace("${" + layer + "}", self.fq(layer))
        return sql
