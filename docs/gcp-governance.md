# GCP governance: Axiom data platform

Project `axiom-data-514305`, BigQuery sandbox (no billing account), location US. Checked on 2026-11-10.

## Who can do what

| Identity | Project role | Dataset roles | Used for |
|---|---|---|---|
| `axiom-elt-loader@axiom-data-514305.iam.gserviceaccount.com` | `roles/bigquery.jobUser` | `roles/bigquery.dataEditor` on `axiom_raw`, `axiom_staging`, `axiom_mart`, `axiomdev_raw`, `axiomdev_staging`, `axiomdev_mart` | The scheduled ELT run: load jobs, staging and mart rebuilds, `dq_results`, column descriptions |
| `axiom-dashboard-reader@axiom-data-514305.iam.gserviceaccount.com` | `roles/bigquery.jobUser` | `roles/bigquery.dataViewer` on `axiom_mart` and `axiomdev_mart` only | Dashboards. Cannot see raw or staging, cannot write anything |
| The project owner (a personal Google account) | Owner, plus `roles/iam.serviceAccountTokenCreator` on the two accounts | (inherited) | Setup, the opt-in integration tests, and acting as either account for checks |

Why these roles:
- `jobUser` lets an identity run query and load jobs. It gives no access to any data by itself.
- `dataEditor` and `dataViewer` are granted **per dataset**, not per project. A new dataset in the project is closed to both accounts until it's granted. BigQuery lists these dataset roles by their legacy names: `WRITER` = dataEditor, `READER` = dataViewer.
- The loader cannot create datasets. The datasets already exist, and the pipeline only creates one when it's missing. A brand-new environment is created once by the owner.
- No service-account keys exist. Nothing in the repo or on disk holds a key file.

How it was set up (the commands and their output are in `RESULTS.md`):

```
gcloud iam service-accounts create axiom-elt-loader --project axiom-data-514305
gcloud iam service-accounts create axiom-dashboard-reader --project axiom-data-514305
gcloud projects add-iam-policy-binding axiom-data-514305 --member serviceAccount:<sa> --role roles/bigquery.jobUser
python -m data_platform.access --project axiom-data-514305   # dataset grants; safe to re-run
```

Re-run `data_platform.access` after dropping and recreating a dataset, because a new dataset starts with default access only.

**Verified by acting as each account.** The owner mints short-lived tokens for the accounts (no key files).
- `pytest tests/test_access_bq.py` (opt-in): the reader can read the marts. It is refused on raw, on staging, on writing a table, and on creating a dataset. The loader can read raw and write to and delete from a dev raw table, but can't create a dataset.
- `python -m data_platform run --env dev --impersonate axiom-elt-loader@...`: a full pipeline run as the loader succeeded. BigQuery's job history shows all 39 jobs ran as the loader, with 0 errors. So these roles are enough for the pipeline, not just narrow.

## Source database access

The pipeline reads production Neon as `axiom_reader`. That role has `CONNECT`, `USAGE` on schema `public`, and `SELECT` on its tables (including future ones). Nothing else. A test insert as `axiom_reader` was refused with "permission denied for table watchlist". The app's own admin connection string is never used by the pipeline: `data_platform` blanks `DATABASE_URL` at startup.

## What the data holds

| Data | Where it comes from | Personal data? |
|---|---|---|
| Analysis runs, including traces (tool calls, LLM token counts, model output text) | Axiom's `runs` table | No. A run is started by entering a ticker. Axiom has no accounts, names or emails. |
| Theses, outcomes, actions, paper trades, watchlist | Axiom tables | No. Tickers, ratings, prices, timestamps, plans written by the agents. |
| Rate-limit counters (`usage`) | Axiom's `usage` table | **The source has client IP addresses** (`ip:<address>` keys). The extractor cuts each key to the part before the colon (`ip`, `global`) before loading, so no IP reaches BigQuery. Staging sums the counters per scope. |
| Daily price bars | yfinance, through Axiom's own fetcher | No. Public market data, kept in private datasets only and never published or committed. |
| `dq_results` | The pipeline's checks | No. |

**No PII in the warehouse, checked:** a scan of every table in all six datasets for IPv4/IPv6 and email patterns found 0 matching rows (`RESULTS.md`, Phase 2). Every dataset has the label `contains-pii: no`, plus `app: axiom` and `managed-by: data-platform`.

## Descriptions

- **Datasets:** one line each, saying what the layer is (raw change log, deduplicated staging, marts).
- **Tables:** every staging and mart table gets the `-- description:` line from its SQL file on each rebuild.
- **Columns:** `backend/data_platform/column_docs.yaml` describes every mart column and the less obvious staging columns, and is written to BigQuery after each run (107 columns in prod). A unit test fails if it names a column that the SQL doesn't produce.

## Retention

Sandbox tables and partitions expire after 60 days, and a longer expiry is refused without billing. Staging and marts are rebuilt every run, so only raw history older than 60 days is lost.

## Secrets

| Secret | Where it lives | In git? |
|---|---|---|
| Neon read-only URL (`AXIOM_SOURCE_DATABASE_URL`) | `backend/.env.data` on the owner's machine | No. Ignored by `.env.*` in `.gitignore` (checked with `git check-ignore`). |
| Google credentials for local runs | gcloud application-default credentials in the user profile | No |
| Credentials for the scheduled run (Phase 3) | GitHub Actions encrypted secret for the Neon URL. Google access through Workload Identity Federation as `axiom-elt-loader`, so no key is stored anywhere. | No |

Secret Manager isn't used. The project has no billing account, and the scheduler's secrets live in GitHub.
