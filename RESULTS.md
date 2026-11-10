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
- Phases 2 to 7: not started

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
- **Cloud SDK / IAM sign-in**: `gcloud auth login` and application-default credentials as the project owner. No service accounts yet (Phase 2).

## 5. Not done and why

- Phases 2 to 7 not started yet.
- Cloud Run (Phase 6) and Cloud Scheduler need billing; the human chose the sandbox, so these will be "Not done".

## 6. Honest limits

- **Prod data is tiny:** 5 runs, 0 scored outcomes. The scorecard mart is correctly empty for prod. All scorecard statistics above come from **synthetic** data and say nothing about Axiom's skill.
- **Price data is private:** it comes from yfinance through Axiom's own fetcher, is kept in a private dataset only, and is never published.
- **Sandbox tables expire after 60 days.** Each run rebuilds staging and marts, but raw history older than 60 days would be lost without billing.
- **RSI differs:** the SQL RSI is Cutler's (simple means), not Axiom's Wilder RSI, and is labelled `rsi14_cutler`.

## 7. Resume-safe sentences

_Written after the last phase._
