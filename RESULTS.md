# Axiom data platform: results

Every number here comes from a command that was run; the command and date are next to it.
Machine: Windows 11 Home 10.0.26300, Python 3.12.12 (`C:\Users\Amal\.venvs\axiom`), Node 22.19.0.

## 1. Baseline

Taken 2026-11-10 on `main` @ `f0d0d7f`, before any change.

**How the baseline was run.** `backend/.env` (written by `vercel env pull`) holds the production Neon `DATABASE_URL`, and `Settings` reads that file automatically. The tests never cleared `DATABASE_URL`, so a local `pytest` would have written to production, and the eval runner calls `get_cache().clear()`, which would have emptied the production cache. To get a CI-equivalent run, the backend baseline used a clean `git archive HEAD backend` copy (no `.env`) in a scratch directory.

| Item | Result | Command |
|---|---|---|
| Backend tests collected | 160 | `python -m pytest --collect-only -q` |
| Backend tests | 155 passed, 4 skipped, **1 failed** | `python -m pytest -q` (clean copy, 50.3 s) |
| Skipped | 4: Postgres variants of `test_db_portability.py`, need `AXIOM_TEST_DATABASE_URL` | `pytest -rs tests/test_db_portability.py` |
| Failed | `test_evals.py::test_recorded_evals_replay_green` | as above |
| Frontend tests | 88 passed (6 files) | `npm ci && npm test` (vitest) |
| Replay evals, today's date | 5/21 (16 core cases all fail: "no recording for request") | `python -m evals.run --mode replay --recording evals/recordings/qwen3-8b.jsonl ...` |
| Replay evals, clock frozen at 2026-10-13 | **16/16 core** (6 honesty, 10 injection) + 5/5 undefended baselines = 21/21 | same, through a wrapper that pins `orchestrator.datetime.now()` (diagnosis only, not committed) |
| Replay evals, clock frozen at 2026-10-12 | 0/16 core | same wrapper |
| `ruff check .` | passes | `python -m ruff check .` |
| `ruff format --check .` | **fails**: `tests/test_llm.py` | `python -m ruff format --check .` |
| CI on `main` | red since 2026-10-16: pytest (eval replay) on `c0be5c5`, format check on `f0d0d7f` | `gh run list`, `gh run view --json jobs` |
| MCP tools | 11 | `@mcp.tool()` count in `backend/axiom/mcp_server/server.py` |

**Why the evals fail.** The analyst task prompt contains `Today is {today}`, taken from `datetime.now()` (`backend/axiom/agents/orchestrator.py:109,169`). Recordings are keyed by a hash of the request, so a replay only matches on the day it was recorded (2026-10-13). The pipeline still passes 16/16 on the recorded outputs, but "deterministic replay in CI" is not true today. Fixing it needs a human decision (see "Not done").

**Local database.** None existed: no `backend/.cache/axiom.db`, no `*.db` files. Real data lives only in production Neon (not read yet; needs a read-only role). Schema, from an empty store created in a scratch directory (`Store(path)` + `TTLCache(path=...)`):

| Table | Columns | Rows (local) |
|---|---|---|
| runs | run_id, ticker, created_at, result_json, events_json | 0 |
| theses | id, run_id, ticker, created_at, issue_date, horizon_days, price_at_issue, rating, conviction, stop_price, memo_json, findings_json, status | 0 |
| outcomes | thesis_id, scored_at, horizon_date, price_at_horizon, ret_pct, benchmark_ret_pct, excess_ret_pct, direction_hit, beat_benchmark, stop_hit, brier, detail_json | 0 |
| actions | id, run_id, ticker, created_at, status, plan_json, decided_at, result_json | 0 |
| action_keys | key, action_id, done_at | 0 |
| watchlist | ticker, added_at | 0 |
| paper_trades | id, ticker, side, quantity, entry_price, entry_date, thesis_id, exit_price, exit_date | 0 |
| usage | key, bucket, n | 0 |
| kv (cache) | k, v, expires | 0 |

Tool-call traces and token counts are not tables. They live inside `runs.events_json` (`tool_result` events carry `latency_ms`; `llm_call` events carry tokens and latency). Price bars are not stored; they sit in `kv` for 10 minutes only.

**After the Phase 0 fixes** (branch `gcp-data-platform`, real repo with `.env` present, `DATABASE_URL` set to an unreachable host as a tripwire):

| Item | Result | Command |
|---|---|---|
| Backend tests | 159 passed, 4 skipped, 1 failed (the same date-bound eval replay) | `python -m pytest -q` (49.4 s) |
| New isolation tests | 4 passed (2 positive controls show the leak is real, 2 show the guards stop it) | `pytest tests/test_env_isolation.py` |
| Replay evals at 2026-10-13 | 21/21, so the eval-runner change does not alter request keys | wrapper as above |
| `ruff format --check .` | passes | |

**Eval date fix** (approved by the human, commit `4fd8de2`). `analyze()` takes an optional `today` (the default is unchanged), and the eval runner pins it to 2026-10-13. After the fix: replay passes 21/21 on 2026-11-10 with no wrapper, and the backend has 160 passed, 4 skipped. No re-record was needed.

## 2. What was built

- Phase 0, baseline: DONE
- Phase 1, BigQuery ELT warehouse: DONE (sandbox, no billing)
- Phase 2, data quality and governance: DONE
- Phase 3, scheduling: BUILT. A real run in GitHub waits on two steps only the owner can take (section 5).
- Phase 4, PySpark: DONE (Docker, public-domain data)
- Phase 5, model: DONE (no useful edge found; see below)
- Phases 6 to 7: in progress

## 3. Measurements

All on 2026-11-10, project `axiom-data-514305` (BigQuery sandbox, location US), from this Windows machine.

| Item | Number | Unit | Command / evidence |
|---|---|---|---|
| Prod source rows (Neon, read-only role) | runs 5, theses 5, outcomes 0, actions 19, action_keys 19, watchlist 0, paper_trades 0, usage 6 | rows | `make_reader.py` count as `axiom_reader` (05:21Z) |
| Prod trace events | 48 tool_result, 87 llm_call (across 5 runs) | events | read-only scan of `runs.events_json` |
| Prod run 1 | 54 rows loaded (29 incremental + 25 snapshot), 3,000 price bars, reconciled, 184.8 s | | `python -m data_platform run --env prod` (05:58Z) |
| Prod run 2 (same source) | 0 incremental rows loaded, snapshots reloaded (25), reconciled, 161.8 s | | same (06:02Z) |
| Prod source vs warehouse | runs 5/5, theses 5/5, outcomes 0/0, actions 19/19, action_keys 19/19, watchlist 0/0, paper_trades 0/0, usage 6/6 | rows | `reconciled` log event, both runs |
| Prod staging/mart rows | tool_calls 48, llm_calls 87, price_bars 3,000, llm_usage_daily 17, tool_latency_daily 18, price_indicators 3,000, scorecard **0** (no directional calls) | rows | `model_built` events, prod run 2 |
| Synthetic source rows | runs 80, theses 80, outcomes 46 (33 directional), actions 38, action_keys 22, watchlist 3, paper_trades 4, usage 7 | rows | `python -m data_platform seed` |
| Dev run 1 / run 2 | 280 / 36 rows loaded (run 2: 0 incremental, 36 snapshot); 145.2 s / 115.5 s; both reconciled | | `python -m data_platform run --env dev` (05:51Z, 05:56Z) |
| Duplicate keys after 2 runs (dev) | 0 in all 9 staging tables | rows | `COUNT(*) - COUNT(DISTINCT pk)` per table |
| SQL indicators vs Axiom Python | SMA20/50/200 max abs diff 0; vol20 max abs diff 2.9e-15; null pattern identical | | `mart.price_indicators` vs `axiom.quant.indicators`, 9,000 bars, 6 tickers |
| Dry-run bytes, prod | staging: runs 190,868; theses 20,813; actions 15,528; action_keys 1,216; usage 342; tool_calls 101,683; llm_calls 101,683; price_bars 214,500. mart: scorecard 220; tool_latency_daily 1,733; llm_usage_daily 3,393; price_indicators 64,500 | bytes | `python -m data_platform dryrun --env prod` (06:04Z) |
| Dry-run bytes, dev | staging: runs 591,723; tool_calls 476,024; llm_calls 476,024; price_bars 643,500. mart: scorecard 4,842; tool_latency_daily 21,442; llm_usage_daily 23,485; price_indicators 193,500 | bytes | `python -m data_platform dryrun --env dev` |
| Partition pruning (range partitions) | full scan 1,093,500 vs 2026-only filter 169,128 | bytes (dry run) | 9,000-bar table, `WHERE date_key >= UNIX_DATE('2026-01-01')` |
| Sandbox partition expiry trap | 9,000 bars in, 294 kept with native MONTH date partitions | rows | first dev run, before switching to range partitions |
| Integration test (real BigQuery) | 1 passed, 3 pipeline runs, 361.8 s | | `AXIOM_BQ_INTEGRATION=1 pytest tests/test_data_platform_bq.py` (06:10Z) |
| Backend tests after Phase 1 | 170 passed, 5 skipped (4 Postgres, 1 opt-in BigQuery) | tests | `python -m pytest -q` |
| Frontend tests after Phase 1 | 88 passed | tests | `npm test` |
| MCP tools | 11 | tools | `@mcp.tool()` count |

**Phase 2: data quality and governance** (2026-11-10)

| Item | Number | Unit | Command / evidence |
|---|---|---|---|
| Check files / results per run | 10 files (8 critical, 2 warn) / 47 results | | `backend/data_platform/sql/dq/`, `dq_checked` log event |
| Prod run with checks | 47/47 passed, marts built, 107 column descriptions written, 196.86 s, exit 0 | | `python -m data_platform run --env prod` (06:42Z) |
| Dev run, first try | **exit 3**, marts not built: `accepted_values` on `actions.status`, 5 rows | rows | `python -m data_platform run --env dev` |
| Dev run after reload | 46/47 passed (only the `source_freshness` warn: synthetic data ends weeks ago), 280 rows loaded, 178.44 s, exit 0 | | same, after dropping `axiomdev_*` (06:48Z) |
| Positive-control test (real BigQuery) | 1 passed, 289.2 s. Clean data: only the freshness warn fails. With one bad row per rule: exactly 8 critical results and 1 warn fail, each with observed = 1. Load freshness fails when judged 3 h later. | | `AXIOM_BQ_INTEGRATION=1 pytest tests/test_data_quality_bq.py` |
| Mart columns with a description | 48/48 across 5 mart tables, plus a description on every mart table | columns | schema read-back of `axiom_mart` |
| PII scan of the warehouse | 0 rows matching IPv4/IPv6 or email patterns, in every table of all 6 datasets | rows | `REGEXP_CONTAINS(TO_JSON_STRING(row), ...)` per table |
| Service accounts | 2 created: `axiom-elt-loader`, `axiom-dashboard-reader`; 0 keys | | `gcloud iam service-accounts create`, `... list` |
| Grants, read back | both: project `roles/bigquery.jobUser`; loader `WRITER` (dataEditor) on all 6 datasets; reader `READER` (dataViewer) on the 2 mart datasets only | | `gcloud projects get-iam-policy`, `python -m data_platform.access` (run twice, no duplicate entries) |
| Least privilege, acting as each account | 2 passed, 16.9 s. Reader: mart read allowed; raw read, staging read, table write and dataset create refused (403). Loader: raw read and dev-raw write and delete allowed; dataset create refused. | | `AXIOM_BQ_INTEGRATION=1 pytest tests/test_access_bq.py` (after the owner granted token-creator, 07:03Z) |
| Dev pipeline run as the loader | exit 0, 46/47 checks (freshness warn only), 36 rows loaded, reconciled, 157.59 s. Job history: 39 jobs (6 load, 33 query), all by `axiom-elt-loader`, 0 errors. | | `python -m data_platform run --env dev --impersonate axiom-elt-loader@...` (07:04Z); `INFORMATION_SCHEMA.JOBS_BY_PROJECT` |
| Backend tests after Phase 2 | 178 passed, 8 skipped (4 Postgres, 4 opt-in BigQuery) | tests | `python -m pytest -q` |
| Replay evals after Phase 2 | 21/21 (16/16 core) | cases | `python -m evals.run --mode replay ...` |

**What the dev failure was.** I had changed the synthetic seed to write `proposed` rather than an invented `pending` status. Re-seeding rewrote 5 action rows without moving their watermark. The incremental load correctly skipped them as already loaded, so the warehouse kept the stale `pending` rows. The check stopped the run before the marts. Dropping the dev datasets and reloading fixed it. It's the same rule as Phase 1: a changed row must get a newer timestamp.

**Phase 3: scheduling** (2026-11-10)

`.github/workflows/data-platform.yml` runs `python -m data_platform run --env prod` on weekdays at 14:00 UTC, an hour after the app's own cron. It also runs on manual dispatch. It signs in to GCP as `axiom-elt-loader` through Workload Identity Federation, with no key stored. The logs are the pipeline's JSON events (run start, rows per table, checks, duration), plus a job summary. A failed critical check exits 3 and fails the job.

| Item | Result | Evidence |
|---|---|---|
| CI on the pushed branch | success, 83 s | GitHub run 42774286437 |
| First workflow run (push trigger) | failed as expected: "AXIOM_SOURCE_DATABASE_URL is not set". The secret isn't stored yet, so the job stopped before contacting GCP or Neon. | GitHub run 42774286201 |
| Workload identity pool `github` + provider `axiom-repo` | created; the condition limits it to this repo's id, this workflow file, and schedule/dispatch/push events | `gcloud iam workload-identity-pools ... create` |
| The same run as the loader, locally | passes (Phase 2: 39 jobs as `axiom-elt-loader`, 0 errors) | `--impersonate`, job history |
| Summary step | renders from a real run report | local run of the step's script on the dev report |
| Price outage guard | a failed fetch keeps the previous price window instead of truncating it; unit test (fails without the guard) | `test_a_partial_price_fetch_keeps_the_previous_window` |

**Phase 4: PySpark** (2026-11-10)

`backend/data_platform/spark/`: SMA 20/50/200 and 20-day volatility as window functions, and Wilder RSI 14 (recursive) per series in `applyInPandas`. The Spark job doesn't import Axiom, so it's an independent implementation checked against `axiom/quant/indicators.py`.
- **Real data:** Federal Reserve H.10 daily exchange rates, 24 currencies, 2000-01-03 to 2026-11-06, 155,079 rows. Downloaded from federalreserve.gov, whose disclaimer says the site's information "is in the public domain and may be copied and distributed without permission" (citation: Board of Governors of the Federal Reserve System, H.10). Two stock datasets were rejected: one is gated behind a paid subscription with license "other", the other has no license file.
- **Synthetic data** for scale: seeded GBM, 2,520 business days per series.
- **Machine:** AMD Ryzen 7 7840HS (8 cores, 16 threads), 15.3 GB RAM, Windows 11. Spark 4.1.4 runs in Docker (`apache/spark:4.1.4-python3` plus pandas 2.3.3 and pyarrow 21) with `--cpus=8 --memory=6g`, `local[8]`. pandas 3.0.6 runs on the host, single process, using Axiom's own functions per series. Each figure is the best of 2 runs.

| Dataset | Rows | Series | pandas total (read, compute, write) | Spark container wall time | Spark compute + write (excludes JVM start and container start) |
|---|---|---|---|---|---|
| H.10 (real) | 155,079 | 24 | 0.35 s | 18.8 s | 11.1 s |
| synthetic | 2,520,000 | 1,000 | 6.6 s | 33.0 s | 25.3 s |
| synthetic | 10,080,000 | 4,000 | 18.4 s | 63.7 s | 54.4 s |
| synthetic | 20,160,000 | 8,000 | 35.8 s | 116.3 s | 105.9 s |

Spark session start was 2.9 to 3.1 s in every run. Command: `python -m data_platform.spark.bench --sizes 1000,4000,8000 --repeats 2`. All runs: `pandas_all_total` / `spark_all_wall` in `backend/.cache/spark/bench.json`.

**Correctness, Spark vs Axiom, on every row of all four datasets:**

| Column | NULL positions identical | Max relative difference (all sets) | Notes |
|---|---|---|---|
| sma20 / sma50 / sma200 | yes | 5.6e-15 | max absolute 2.8e-9 on H.10 (rates up to the thousands) |
| vol20 | yes | 2.7e-14 on synthetic; 1.4e-8 on H.10 where vol > 1e-4 | 2 of 154,599 H.10 rows are pegged windows (CNY 2004, LKR 2002) with true volatility 0: Spark gives exactly 0, pandas' rolling std leaves 3.7e-11 and 7.2e-9 of rounding residue |
| rsi14 (Wilder) | yes | 0 | bit-identical |

Unit tests (`tests/test_spark_indicators.py`, no Docker needed): the H.10 parser, the Spark job's RSI against Axiom's `rsi()` (including the flat, gains-only, losses-only and too-short cases), and deterministic synthetic data.

**What the timing says.** On one 8-core machine, Spark is 3 to 54 times slower than pandas for this job. The gap narrows as the data grows (54x at 155k rows, 3.2x at 20M), but pandas still wins at 20M rows. The JVM and container start alone take about 7 s. The recursive RSI runs in Python in both engines. Spark would pay off only past what one machine's memory holds, or on a cluster. Neither was tested.

**Phase 5: direction model** (2026-11-10)

`backend/data_platform/research/direction_model.py`. It isn't used by the app, the agents or the MCP server.
- **Question:** will an H.10 exchange rate be higher in 5 trading days?
- **Data:** 24 currencies, public domain. Rows with an unchanged rate (pegs) are dropped.
- **Features:** 1/5/20-day log returns, distance from SMA 20/50/200, RSI 14 and vol 20. All use only past data and come from Axiom's own functions.
- **Model:** standardised logistic regression with seed 7. `C` was chosen on validation log loss from {0.001, ..., 10}; 0.001 won, the edge of the grid. It was then refit on train plus validation.
- **Split by time, with a 5-day embargo:** a row counts only if its label window ends inside its period.

| Period | Dates | Rows |
|---|---|---|
| train | 2000-01-03 to 2015-12-31 | 81,876 |
| validation | 2016-01-01 to 2019-12-31 | 22,119 |
| test (used once) | 2020-01-02 to 2026-10-30 | 38,960 |
| embargo (dropped) | the 5 rows before each boundary | 224 |

| On the test period | Accuracy | Accuracy, non-overlapping rows (95% CI) | Log loss | ROC AUC |
|---|---|---|---|---|
| **Model (sklearn)** | 0.525 | 0.523 (0.512 to 0.534) | 0.6895 | 0.536 |
| Majority class from training (always "up") | 0.527 | 0.527 (0.516 to 0.538) | 0.6929 | 0.5 |
| 5-day momentum | 0.517 | 0.513 (0.502 to 0.524) | n/a | 0.516 |
| Coin flip | 0.5 | | 0.6931 | 0.5 |
| **BigQuery ML twin** (`logistic_reg`, same features and rows) | 0.5251 | | 0.6922 | 0.5361 |

- **Bootstrap over 82 calendar months** (500 resamples, whole months, so the dollar's same-day move stays together):
  - AUC 95% CI 0.516 to 0.556;
  - log-loss gain over the majority class -0.0008 to 0.0058;
  - accuracy gain over the majority class -2.3 to +2.0 points.
- **Trading on the signal** (non-overlapping 5-day windows): mean log return -0.00057 per trade, against -0.00029 for always long.
- **sklearn vs BQML:** they give the same class on 96.9% of the 38,960 test rows, with a mean absolute probability difference of 0.0175. BQML used its default (no L2), while sklearn used C = 0.001, so the two aren't regularised identically.
- **Verdict:** there's a small ranking signal whose AUC interval excludes 0.5. But the model is **not** more accurate than always predicting "up", and trading on it lost money against simply holding. It's not useful as a trading signal.
- **Leakage tests** (`tests/test_direction_model.py`, 5 passed):
  - features up to a date don't change when every later price is randomised;
  - the same check catches a deliberately leaky feature (tomorrow's return), so it isn't vacuous;
  - labels are exactly 5 rows ahead;
  - no label window crosses a split boundary;
  - on a pure random walk, the whole pipeline shows no skill (AUC within 0.03 of 0.5).
- **Commands:** `python -m data_platform.research.direction_model --bqml --project axiom-data-514305` (local part about 8 s). The BQML model is `axiom_research.direction_logreg`.

**Sandbox capabilities, measured** (`python -m data_platform.sandbox_probe --project axiom-data-514305`, 05:50Z). Billing is off: `gcloud billing projects describe` says `billingEnabled: False`.

| Feature | Result |
|---|---|
| Load job (NDJSON) | allowed |
| Query job to a destination table | allowed |
| `CREATE OR REPLACE TABLE AS`, `CREATE OR REPLACE VIEW` | allowed |
| `INSERT`, `MERGE` (DML) | blocked: "DML queries are not allowed in the free tier" |
| Streaming insert | blocked: "Streaming insert is not allowed in the free tier" |
| BigQuery ML `CREATE MODEL` | allowed |
| Default table expiry and partition expiry | 60 days each; a longer partition expiry is refused ("Billing has not been enabled") |

Google's published sandbox quotas (storage and monthly query volume) were **not** re-checked: the docs page could not be fetched from this session. Measured usage is under 1 MB per query.

**Design notes**
- **Price table:** partitioned on `date_key = UNIX_DATE(date)` (30-day ranges) and clustered by `ticker, date`. Native date partitions would have kept only the last 60 days in the sandbox (measured above). Range partitions keep pruning on date filters. With billing enabled, native MONTH partitioning on `date` would be the better choice.
- **No MERGE:** raw is an append-only change log. Incremental tables skip `(pk, watermark)` versions raw already has, using a 1-day look-back for late commits. Staging is rebuilt with `QUALIFY ROW_NUMBER() OVER (PARTITION BY pk ORDER BY _wm DESC, _loaded_at DESC) = 1`. Small tables that can lose rows are full snapshots.
- **Watermarks assume timestamps only move forward.** The first version of the integration test broke that assumption on purpose, and reconciliation caught the missed rows. Axiom stamps rows with `time.time()` on insert.

## 4. GCP services actually used

- **BigQuery** (sandbox): datasets `axiom_raw`, `axiom_staging`, `axiom_mart` (prod) and `axiomdev_*` (synthetic). Load jobs, query jobs, dry runs. Evidence: the dataset listing printed after the integration test, and the run logs above.
- **Cloud SDK / IAM sign-in**: `gcloud auth login` and application-default credentials as the project owner. Owner credentials were used for setup and the runs above.
- **IAM**: two service accounts and dataset-level grants (`docs/gcp-governance.md`). No keys.
- **BigQuery ML** (sandbox): `CREATE MODEL ... logistic_reg`, `ML.EVALUATE`, `ML.PREDICT` in dataset `axiom_research` (public-domain H.10 data only).
- **Workload Identity Federation**: pool `github`, provider `axiom-repo` (Phase 3).
- **IAM Service Account Credentials API**: short-lived tokens for acting as the accounts (enabled by the owner).

## 5. Not done and why

- **Phase 3, first real run in GitHub: waiting on the owner.** Two steps were blocked for me as permission and secret changes, so they need the owner:
  1. `gcloud iam service-accounts add-iam-policy-binding axiom-elt-loader@axiom-data-514305.iam.gserviceaccount.com --project axiom-data-514305 --role roles/iam.workloadIdentityUser --member principalSet://iam.googleapis.com/projects/103613789288/locations/global/workloadIdentityPools/github/attribute.repository_id/1176257246`
  2. `gh secret set AXIOM_SOURCE_DATABASE_URL --repo amaltomajith/Axiom` (paste the read-only URL from `backend/.env.data`).

  GitHub only runs a schedule from the default branch, so the weekday cron starts when this branch is merged to `main`. Until then it runs on manual dispatch or a push that changes the workflow file.
- Cloud Run (Phase 6), Cloud Scheduler and Secret Manager need billing; the human chose the sandbox, so these will be "Not done".

## 6. Honest limits

- **Prod data is tiny:** 5 runs, 0 scored outcomes. The scorecard mart is correctly empty for prod. All scorecard statistics above come from **synthetic** data and say nothing about Axiom's skill.
- **Price data is private:** it comes from yfinance through Axiom's own fetcher, is kept in a private dataset only, and is never published.
- **Sandbox tables expire after 60 days.** Each run rebuilds staging and marts, but raw history older than 60 days would be lost without billing.
- **Data-quality checks are only as fresh as the watermark:** a source row changed without a newer timestamp is not reloaded. The checks catch it when the new value breaks a rule (as in dev), but not when it doesn't.
- **Spark was not faster here:** single machine, at most 20M rows. No cluster run.
- **The model has no practical edge:** see Phase 5. The regularisation choice hit the edge of its grid.
- **RSI differs:** the SQL RSI is Cutler's (simple means), not Axiom's Wilder RSI, and is labelled `rsi14_cutler`.

## 7. Resume-safe sentences

_Written after the last phase._
