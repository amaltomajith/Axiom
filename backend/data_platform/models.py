"""SQL files as models: a .sql file whose result becomes a table (staging, mart) or a set of check results
(dq). Header comments carry the metadata, so the runner stays generic:

    -- description: what the table holds (also written to BigQuery as the table description)
    -- requires: ${raw}.price_bars       skip this model when that table does not exist
    -- partition_by: date_key            integer-range partition column (day number)
    -- cluster_by: ticker, date
    -- severity: critical | warn         dq checks only
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import SQL_DIR

_DIRECTIVE = re.compile(r"^--\s*(description|requires|partition_by|cluster_by|severity):\s*(.+?)\s*$", re.M)


@dataclass(frozen=True)
class SqlModel:
    path: Path
    layer: str
    name: str
    sql: str
    description: str = ""
    requires: list[str] = field(default_factory=list)
    partition_by: str | None = None
    cluster_by: list[str] = field(default_factory=list)
    severity: str | None = None

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
            severity=(meta.get("severity") or [None])[0],
        )


def models(layer: str) -> list[SqlModel]:
    return [SqlModel.read(p, layer) for p in sorted((SQL_DIR / layer).glob("*.sql"))]
