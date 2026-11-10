"""Find out, by trying, what this BigQuery project allows (sandbox projects have no billing account).

    python -m data_platform.sandbox_probe --project axiom-data-514305

Creates a throwaway dataset `axiom_probe`, runs one tiny statement per feature, prints ALLOWED or BLOCKED
with the error, reads the dataset's default table expiration, then deletes the dataset. A few KB scanned.
"""

from __future__ import annotations

import argparse
import io
import json

from google.cloud import bigquery


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--location", default="US")
    a = ap.parse_args()
    c = bigquery.Client(project=a.project, location=a.location)
    ds_id = f"{a.project}.axiom_probe"
    c.delete_dataset(ds_id, delete_contents=True, not_found_ok=True)
    ds = bigquery.Dataset(ds_id)
    ds.location = a.location
    ds = c.create_dataset(ds)
    exp = ds.default_table_expiration_ms
    print(json.dumps({"dataset_default_table_expiration_days": None if exp is None else exp / 86_400_000}))
    t = f"{ds_id}.t"
    results = {}

    def attempt(name, fn):
        try:
            fn()
            results[name] = "ALLOWED"
        except Exception as e:  # report whatever the API says
            results[name] = f"BLOCKED: {type(e).__name__}: {str(e).splitlines()[0][:220]}"
        print(f"{name:<34} {results[name]}")

    def load():
        body = "\n".join(json.dumps({"id": i, "x": float(i), "y": i % 2}) for i in range(20)).encode()
        cfg = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            schema=[
                bigquery.SchemaField(n, ty) for n, ty in (("id", "INT64"), ("x", "FLOAT64"), ("y", "INT64"))
            ],
        )
        c.load_table_from_file(io.BytesIO(body), t, job_config=cfg).result()

    def q(sql):
        return lambda: c.query(sql).result()

    def query_to_dest():
        cfg = bigquery.QueryJobConfig(destination=f"{ds_id}.dest", write_disposition="WRITE_TRUNCATE")
        c.query(f"SELECT * FROM `{t}`", job_config=cfg).result()

    def streaming():
        errs = c.insert_rows_json(t, [{"id": 99, "x": 1.0, "y": 1}])
        if errs:
            raise RuntimeError(errs)

    attempt("load job (NDJSON)", load)
    attempt("query job -> destination table", query_to_dest)
    attempt(
        "DDL: CREATE OR REPLACE TABLE AS", q(f"CREATE OR REPLACE TABLE `{ds_id}.ctas` AS SELECT * FROM `{t}`")
    )
    attempt("DDL: CREATE OR REPLACE VIEW", q(f"CREATE OR REPLACE VIEW `{ds_id}.v` AS SELECT id FROM `{t}`"))
    attempt("DML: INSERT", q(f"INSERT INTO `{t}` (id, x, y) VALUES (100, 1.0, 0)"))
    attempt(
        "DML: MERGE",
        q(
            f"MERGE `{t}` T USING (SELECT 1 AS id, 9.0 AS x, 1 AS y) S ON T.id = S.id "
            "WHEN MATCHED THEN UPDATE SET x = S.x WHEN NOT MATCHED THEN INSERT (id, x, y) VALUES (S.id, S.x, S.y)"
        ),
    )
    attempt("streaming insert (insertAll)", streaming)
    attempt(
        "BigQuery ML: CREATE MODEL",
        q(
            f"CREATE OR REPLACE MODEL `{ds_id}.m` OPTIONS (model_type='logistic_reg', input_label_cols=['y']) "
            f"AS SELECT x, y FROM `{t}`"
        ),
    )
    c.delete_dataset(ds_id, delete_contents=True, not_found_ok=True)
    print(json.dumps({"results": results}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
