"""Least privilege, proven by acting as each service account against real BigQuery (opt-in):

    AXIOM_BQ_INTEGRATION=1 AXIOM_GCP_PROJECT=<project> pytest tests/test_access_bq.py

Needs roles/iam.serviceAccountTokenCreator on both accounts for the caller (docs/gcp-governance.md).
Writes only a throwaway table in the dev raw dataset and deletes it.
"""

import os
import uuid

import pytest

PROJECT = os.environ.get("AXIOM_GCP_PROJECT")
pytestmark = pytest.mark.skipif(
    os.environ.get("AXIOM_BQ_INTEGRATION") != "1" or not PROJECT,
    reason="set AXIOM_BQ_INTEGRATION=1 and AXIOM_GCP_PROJECT",
)


def client_as(name: str):
    from google.cloud import bigquery

    from data_platform.access import impersonated

    return bigquery.Client(
        project=PROJECT, location="US", credentials=impersonated(f"{name}@{PROJECT}.iam.gserviceaccount.com")
    )


def allowed(fn) -> bool:
    from google.api_core.exceptions import Forbidden

    try:
        fn()
        return True
    except Forbidden:
        return False


def count(c, table: str):
    return lambda: list(c.query(f"SELECT COUNT(*) FROM `{PROJECT}.{table}`").result())


def load_one_row(c, table: str):
    from google.cloud import bigquery

    cfg = bigquery.LoadJobConfig(schema=[bigquery.SchemaField("x", "INT64")])
    return lambda: c.load_table_from_json([{"x": 1}], f"{PROJECT}.{table}", job_config=cfg).result()


def create_dataset(c):
    return lambda: c.create_dataset(f"{PROJECT}.axiomprobe_{uuid.uuid4().hex[:8]}")


def test_dashboard_reader_reads_marts_only():
    c = client_as("axiom-dashboard-reader")
    assert allowed(count(c, "axiom_mart.dq_results"))
    assert allowed(count(c, "axiom_mart.price_indicators"))
    assert not allowed(count(c, "axiom_raw.runs"))  # raw holds full traces; dashboards never need it
    assert not allowed(count(c, "axiom_staging.theses"))
    assert not allowed(load_one_row(c, f"axiom_mart.probe_{uuid.uuid4().hex[:8]}"))
    assert not allowed(create_dataset(c))


def test_loader_writes_axiom_datasets_but_cannot_create_new_ones():
    c = client_as("axiom-elt-loader")
    probe = f"axiomdev_raw.probe_{uuid.uuid4().hex[:8]}"
    assert allowed(count(c, "axiom_raw.runs"))
    assert allowed(load_one_row(c, probe))
    c.delete_table(f"{PROJECT}.{probe}")
    assert not allowed(create_dataset(c))
