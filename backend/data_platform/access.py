"""Dataset-level access for the two service accounts (see docs/gcp-governance.md). Safe to re-run.

    python -m data_platform.access --project <id>

The loader edits every raw/staging/mart dataset; the dashboard reader only reads the marts. BigQuery reports
these dataset roles by their legacy names: dataEditor = WRITER, dataViewer = READER. Re-run after a dataset
is dropped and recreated, since a new dataset starts with default access only.
"""

from __future__ import annotations

import argparse

LOADER = "axiom-elt-loader"
READER = "axiom-dashboard-reader"
LEGACY = {"roles/bigquery.dataEditor": "WRITER", "roles/bigquery.dataViewer": "READER"}
ENVS = ("prod", "dev")
LAYERS = ("raw", "staging", "mart")


def wanted(project: str) -> dict[str, list[tuple[str, str]]]:
    from .config import Layout

    out: dict[str, list[tuple[str, str]]] = {}
    for env in ENVS:
        layout = Layout(project, env)
        for layer in LAYERS:
            grants = [("roles/bigquery.dataEditor", f"{LOADER}@{project}.iam.gserviceaccount.com")]
            if layer == "mart":
                grants.append(("roles/bigquery.dataViewer", f"{READER}@{project}.iam.gserviceaccount.com"))
            out[layout.dataset(layer)] = grants
    return out


def apply(project: str) -> dict[str, list[tuple[str, str]]]:
    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    result: dict[str, list[tuple[str, str]]] = {}
    for dataset, grants in wanted(project).items():
        try:
            ds = client.get_dataset(f"{project}.{dataset}")
        except NotFound:
            continue
        entries = list(ds.access_entries)
        have = {(LEGACY.get(e.role, e.role), e.entity_id) for e in entries}
        missing = [(r, who) for r, who in grants if (LEGACY[r], who) not in have]
        if missing:
            entries += [
                bigquery.AccessEntry(role=r, entity_type="userByEmail", entity_id=w) for r, w in missing
            ]
            ds.access_entries = entries
            ds = client.update_dataset(ds, ["access_entries"])
        result[dataset] = sorted(
            (e.role, e.entity_id.split("@")[0])
            for e in ds.access_entries
            if str(e.entity_id).endswith(".iam.gserviceaccount.com")
        )
    return result


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m data_platform.access")
    ap.add_argument("--project", required=True)
    for dataset, sa in apply(ap.parse_args().project).items():
        print(dataset, sa)


if __name__ == "__main__":
    main()
