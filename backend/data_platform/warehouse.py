"""The only module that talks to BigQuery. Batch load jobs and query jobs only: no streaming inserts and
no DML, both unavailable in the BigQuery sandbox (no billing account)."""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

DATASET_LABELS = {"app": "axiom", "managed-by": "data-platform", "contains-pii": "no"}


@dataclass(frozen=True)
class LoadResult:
    table: str
    rows: int
    bytes: int = 0


class Warehouse(Protocol):
    def ensure_dataset(self, dataset_id: str, description: str) -> None: ...
    def table_exists(self, table: str) -> bool: ...
    def load_rows(
        self,
        table: str,
        rows: list[dict[str, Any]],
        schema: list[tuple[str, str]],
        *,
        truncate: bool,
        description: str = "",
        range_partition_field: str | None = None,
        cluster_fields: list[str] | None = None,
    ) -> LoadResult: ...
    def query(self, sql: str) -> list[dict[str, Any]]: ...
    def query_to_table(
        self,
        sql: str,
        dest: str,
        *,
        description: str = "",
        range_partition_field: str | None = None,
        cluster_fields: list[str] | None = None,
    ) -> LoadResult: ...
    def dry_run_bytes(self, sql: str) -> int: ...
    def count(self, table: str) -> int: ...
    def max_watermark(self, table: str) -> float | None: ...
    def describe_columns(self, table: str, docs: dict[str, str]) -> int: ...
    def versions_since(self, table: str, pk: list[str], since: float) -> set[tuple]: ...


class BigQueryWarehouse:
    def __init__(self, project: str, location: str = "US", credentials: Any = None):
        import os

        from google.cloud import bigquery

        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project)  # quiets google.auth's project lookup
        self.bq = bigquery
        self.client = bigquery.Client(project=project, location=location, credentials=credentials)
        self.project, self.location = project, location

    def ensure_dataset(self, dataset_id: str, description: str) -> None:
        """Look the dataset up first: the least-privilege loader may edit datasets but not create them."""
        from google.api_core.exceptions import NotFound

        try:
            ds = self.client.get_dataset(f"{self.project}.{dataset_id}")
        except NotFound:
            ds = self.bq.Dataset(f"{self.project}.{dataset_id}")
            ds.location, ds.description, ds.labels = self.location, description, dict(DATASET_LABELS)
            ds = self.client.create_dataset(ds)
        if ds.labels != DATASET_LABELS or ds.description != description:
            ds.labels, ds.description = dict(DATASET_LABELS), description
            self.client.update_dataset(ds, ["labels", "description"])

    def table_exists(self, table: str) -> bool:
        from google.api_core.exceptions import NotFound

        try:
            self.client.get_table(table)
            return True
        except NotFound:
            return False

    def _schema(self, schema: list[tuple[str, str]]) -> list[Any]:
        return [
            self.bq.SchemaField(n, t, mode="REQUIRED" if n.startswith("_") else "NULLABLE") for n, t in schema
        ]

    def _shape(self, cfg: Any, range_partition_field: str | None, cluster_fields: list[str] | None) -> None:
        if range_partition_field:
            # Integer-range partitions on a day number (UNIX_DATE), 30 days each, years 1970-2069. Not native
            # date partitions: the sandbox forces a 60-day expiry on time partitions, which silently drops
            # every partition older than 60 days (measured: 9,000 bars in, 294 kept). Range partitions have
            # no partition expiry, and filters on the day number still prune.
            cfg.range_partitioning = self.bq.RangePartitioning(
                field=range_partition_field, range_=self.bq.PartitionRange(start=0, end=36_500, interval=30)
            )
        if cluster_fields:
            cfg.clustering_fields = cluster_fields

    def _drop_if_reshaped(
        self, table: str, range_field: str | None, cluster_fields: list[str] | None
    ) -> None:
        """WRITE_TRUNCATE cannot change a table's partitioning or clustering. Staging and mart tables are
        rebuilt from raw on every run, so dropping one whose shape changed loses nothing."""
        from google.api_core.exceptions import NotFound

        try:
            t = self.client.get_table(table)
        except NotFound:
            return
        has_range = t.range_partitioning.field if t.range_partitioning else None
        if (
            t.time_partitioning
            or has_range != range_field
            or (t.clustering_fields or None) != (cluster_fields or None)
        ):
            self.client.delete_table(table)

    def _describe(self, table: str, description: str) -> None:
        if description:
            t = self.client.get_table(table)
            if t.description != description:
                t.description = description
                self.client.update_table(t, ["description"])

    def load_rows(
        self,
        table,
        rows,
        schema,
        *,
        truncate,
        description="",
        range_partition_field=None,
        cluster_fields=None,
    ):
        cfg = self.bq.LoadJobConfig(
            schema=self._schema(schema),
            source_format=self.bq.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition="WRITE_TRUNCATE" if truncate else "WRITE_APPEND",
        )
        self._shape(cfg, range_partition_field, cluster_fields)
        if not rows and not truncate:
            if not self.table_exists(table):  # create the empty table so later SQL can reference it
                self.client.create_table(self.bq.Table(table, schema=self._schema(schema)))
            self._describe(table, description)
            return LoadResult(table, 0)
        body = "\n".join(json.dumps(r, default=str) for r in rows).encode("utf-8")
        job = self.client.load_table_from_file(io.BytesIO(body), table, job_config=cfg)
        job.result()
        self._describe(table, description)
        return LoadResult(table, int(job.output_rows or 0), len(body))

    def query(self, sql):
        return [dict(r.items()) for r in self.client.query(sql).result()]

    def query_to_table(self, sql, dest, *, description="", range_partition_field=None, cluster_fields=None):
        cfg = self.bq.QueryJobConfig(destination=dest, write_disposition="WRITE_TRUNCATE")
        self._shape(cfg, range_partition_field, cluster_fields)
        self._drop_if_reshaped(dest, range_partition_field, cluster_fields)
        job = self.client.query(sql, job_config=cfg)
        job.result()
        self._describe(dest, description)
        return LoadResult(dest, self.count(dest), int(job.total_bytes_processed or 0))

    def dry_run_bytes(self, sql):
        job = self.client.query(sql, job_config=self.bq.QueryJobConfig(dry_run=True, use_query_cache=False))
        return int(job.total_bytes_processed or 0)

    def count(self, table):
        return int(self.client.get_table(table).num_rows or 0)

    def describe_columns(self, table, docs):
        t = self.client.get_table(table)
        new = [
            self.bq.SchemaField.from_api_repr({**f.to_api_repr(), "description": docs[f.name]})
            if f.name in docs and f.description != docs[f.name]
            else f
            for f in t.schema
        ]
        changed = sum(a is not b for a, b in zip(new, t.schema, strict=True))
        if changed:
            t.schema = new
            self.client.update_table(t, ["schema"])
        return changed

    def max_watermark(self, table):
        if not self.table_exists(table):
            return None
        rows = self.query(f"SELECT MAX(_wm) AS m FROM `{table}`")
        return None if rows[0]["m"] is None else float(rows[0]["m"])

    def versions_since(self, table, pk, since):
        if not self.table_exists(table):
            return set()
        cols = ", ".join(f"`{c}`" for c in pk)
        rows = self.query(f"SELECT DISTINCT {cols}, _wm FROM `{table}` WHERE _wm >= {float(since)!r}")
        return {(*(r[c] for c in pk), float(r["_wm"])) for r in rows}


@dataclass
class FakeWarehouse:
    """In-memory stand-in for unit tests: load jobs and the few lookups the extractor runs. It cannot run
    BigQuery SQL: `responder` answers queries (e.g. canned check results) and query_to_table only records
    that a model was built. The SQL itself is covered by the integration tests against real BigQuery."""

    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    datasets: dict[str, str] = field(default_factory=dict)
    loads: list[LoadResult] = field(default_factory=list)
    built: list[str] = field(default_factory=list)
    column_docs: dict[str, dict[str, str]] = field(default_factory=dict)
    responder: Callable[[str], list[dict[str, Any]]] | None = None

    def ensure_dataset(self, dataset_id, description):
        self.datasets[dataset_id] = description

    def table_exists(self, table):
        return table in self.tables

    def load_rows(
        self,
        table,
        rows,
        schema,
        *,
        truncate,
        description="",
        range_partition_field=None,
        cluster_fields=None,
    ):
        names = {n for n, _ in schema}
        bad = [sorted(set(r) - names) for r in rows if set(r) - names]
        if bad:
            raise ValueError(f"{table}: columns not in schema: {bad[0]}")
        if truncate or table not in self.tables:
            self.tables[table] = []
        self.tables[table].extend(json.loads(json.dumps(r, default=str)) for r in rows)
        res = LoadResult(table, len(rows))
        self.loads.append(res)
        return res

    def query(self, sql):
        if self.responder is None:
            raise NotImplementedError("FakeWarehouse cannot run SQL; pass a responder")
        return self.responder(sql)

    def query_to_table(self, sql, dest, **_):
        self.built.append(dest)
        self.tables.setdefault(dest, [])
        return LoadResult(dest, 0)

    def dry_run_bytes(self, sql):
        return 0

    def count(self, table):
        return len(self.tables.get(table, []))

    def describe_columns(self, table, docs):
        self.column_docs[table] = dict(docs)
        return len(docs)

    def max_watermark(self, table):
        wms = [r["_wm"] for r in self.tables.get(table, [])]
        return max(wms) if wms else None

    def versions_since(self, table, pk, since):
        return {
            (*(r[c] for c in pk), float(r["_wm"])) for r in self.tables.get(table, []) if r["_wm"] >= since
        }
