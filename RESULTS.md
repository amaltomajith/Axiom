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

## 2. What was built

- Phase 0, baseline: DONE
- Phase 1 to 7: not started

## 3. Measurements

_Pending._

## 4. GCP services actually used

None yet.

## 5. Not done and why

- **Eval replay is date-bound.** Left unfixed because the fix touches the agent entry point (`analyze()` would take an optional `today`, pinned by the eval runner to 2026-10-13). That needs the human's go-ahead.

## 6. Honest limits

_Pending._

## 7. Resume-safe sentences

_Pending._
