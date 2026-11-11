# Axiom backend

The Python side of Axiom: the API both front ends call, the MCP server, the agents and their guardrails, memory,
approvals, evals and the BigQuery data platform. For the whole project start at the [root README](../README.md); for
every doc see the [docs index](../docs/README.md).

Python 3.12 with [uv](https://docs.astral.sh/uv/). Every command below runs from this folder.

```bash
uv sync                          # add --extra data for the data platform, --extra actions for Composio
uv run python -m axiom.api       # http://localhost:8000, or run everything with `npm run dev:all` from the repo root
```

> `backend/.env` is read automatically. If it came from `vercel env pull` it holds the **production**
> `DATABASE_URL`. `npm run dev:all` forces local SQLite for that reason, and tests and evals ignore the file.
> When running `axiom.api` by hand, prefix it with `DATABASE_URL=` to stay on SQLite.
>
> On this machine the venv on the F: drive has a folder `uv sync` cannot remove. Use one elsewhere:
> `UV_PROJECT_ENVIRONMENT=C:/Users/<you>/.venvs/axiom`.

## Entry points

| Command | What it does | Needs |
|---|---|---|
| `uv run python -m axiom.api` | FastAPI app on `HOST`:`PORT` (default 127.0.0.1:8000) | Nothing. An LLM key or Ollama for analysis |
| `uv run python -m axiom.mcp_server [--transport streamable-http --port 8765]` | The 11 research tools over MCP (stdio by default). See [MCP clients](../docs/mcp-clients.md) | Nothing |
| `uv run python -m axiom.scheduler --once [TICKERS]` | The daily briefing now: score matured theses, analyse the watchlist, propose one digest | An LLM |
| `uv run python -m axiom.actions.composio_check` | List the configured Composio tool slugs and their parameters | `COMPOSIO_API_KEY`, `--extra actions` |
| `uv run python -m evals.run --mode replay --recording evals/recordings/qwen3-8b.jsonl` | Honesty and injection evals from a recording, at $0 (`--no-judge` skips the judge) | Nothing |
| `uv run python -m evals.run --mode record --recording <file>` | Record a fresh eval run. Needed after any prompt or tool-output change | An LLM (about 10 min on qwen3:8b) |
| `uv run python scripts/capture_snapshot.py` | Rewrite the landing page data (`src/landing/snapshot.json`) and `docs/eval-report.md` | The API running, one stored run |
| `uv run python -m data_platform seed` | Synthetic source DB for data-platform development | `--extra data` |
| `uv run python -m data_platform run --env dev\|prod [--project ID] [--report out.json]` | ELT into BigQuery, then data-quality checks (exit 3 on a critical failure), then marts | GCP sign-in. Prod also needs `backend/.env.data` |
| `uv run python -m data_platform dryrun --env prod --project ID` | Bytes each query would scan | GCP sign-in |
| `uv run python -m data_platform.access --project ID` | Grant the loader and reader service accounts their dataset roles | GCP owner |
| `uv run python -m data_platform.spark.bench` | PySpark vs pandas indicators, checked row for row and timed | Docker |
| `uv run python -m data_platform.research.direction_model [--bqml --project ID]` | Direction model study with baselines and leakage tests | Nothing (`--bqml` needs GCP) |
| `uv run pytest` | The test suite. Postgres and real-BigQuery tests skip unless their env vars are set | Nothing |

Deployed: `api/index.py` is the Vercel entry and `vercel.json` adds the weekday cron
(`/api/cron/daily`, 13:00 UTC). `Dockerfile` is the Cloud Run or any-container fallback. Steps:
[deployment](../docs/deployment.md).

## HTTP routes

All in `axiom/api/app.py`. "Token" means `Authorization: Bearer $AXIOM_API_TOKEN`, required only when that is set.

| Route | Purpose |
|---|---|
| `GET /api/health` | Config snapshot. Both front ends poll it to wake the function |
| `GET /api/status` | Health plus aggregate counts (runs, theses, approvals, today's analyses). Feeds the hub page |
| `GET /api/market/{t}/ohlcv`, `GET /api/quant/{t}/summary\|indicators\|regime\|risk\|forecast\|backtest\|walk-forward` | Prices and the quant layer |
| `GET /api/news/{t}`, `GET /api/filings/{t}`, `GET /api/tickers/search` | News with sentiment, SEC summary, ticker lookup |
| `POST /api/analyze`, `GET /api/analyze/stream` | One research run as SSE (POST for fetch, GET for `EventSource`), rate limited |
| `GET /api/runs[/{id}]`, `GET /api/theses`, `GET /api/scorecard`, `POST /api/score` (token) | Stored runs, theses and the track record |
| `GET /api/actions[/{id}]`, `POST /api/actions/{id}/approve\|retry\|reject` (token) | The approval queue |
| `GET\|PUT\|DELETE /api/watchlist[/{t}]` (writes: token) | The owner's watchlist, which the scheduler uses |
| `GET\|PUT\|DELETE /api/visitor/watchlist[/{t}]` | Per-visitor watchlist for Axiom Watch (`X-Axiom-Visitor` header) |
| `GET\|POST /api/trades`, `POST /api/trades/{id}/close`, `DELETE /api/trades/{id}` (writes: token) | Paper trades |
| `GET\|POST /api/cron/daily` | Scoring and the briefing. `Bearer $CRON_SECRET`; 404 when no secret is set |

## Settings

Read from the environment or `backend/.env` (`axiom/config.py`). All optional. The commented template is
[`.env.example`](.env.example). The ones that matter most:

| Setting | Default | Meaning |
|---|---|---|
| `LLM_CHAIN` | `groq,gemini,openrouter,ollama` | Providers tried in order; ones without a key are skipped. `cerebras` is available but not in the default |
| `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `CEREBRAS_API_KEY` | none | Free-tier keys. `*_MODEL` overrides each model id |
| `OLLAMA_MODEL` | `qwen3:8b` | The offline fallback |
| `DATABASE_URL` | none (SQLite under `.cache/`) | Postgres for runs, theses, approvals, caps and the shared cache |
| `AXIOM_API_TOKEN` | none | Required for writes when set. Set it before exposing the API |
| `ANALYZE_PER_HOUR`, `ANALYZE_PER_DAY` | `12`, `0` (off) | Per-client hourly and global daily caps on analyses |
| `CORS_ORIGINS` | localhost 8080, 5173 and 4200 | Front-end origins allowed to call the API |
| `RUN_DEADLINE_SECONDS` | `0` (off) | Stop a run cleanly before a serverless time limit |
| `CRON_SECRET` | none | Enables `/api/cron/daily` |
| `SCHEDULER_ENABLED` | `false` | Run the briefing inside a long-lived API process instead of cron |
| `COMPOSIO_API_KEY` | none | Real Notion, Sheets and Slack actions; dry run without it |

The data platform reads `backend/.env.data` instead, so it never sees the app's database. Copy
[`.env.data.example`](.env.data.example) to start.

## Layout

```
axiom/quant/        indicators, regime, risk, forecast cone, backtests (pure functions, no lookahead)
axiom/data/         market data (Twelve Data or yfinance), news, SEC EDGAR, TTL cache
axiom/mcp_server/   FastMCP server: 11 tools, 2 resources, 2 prompts
axiom/agents/       orchestrator, tool loop, faithfulness check, policy caps, risk guard, MCP toolbox
axiom/llm/          provider chain with backoff, cache and budgets; a scripted fake for tests
axiom/memory/       store (SQLite or Postgres via axiom/db.py), outcome scorer, scorecard
axiom/actions/      planner, approval gate, Composio and dry-run executors
axiom/api/          the FastAPI app
axiom/pipeline.py   recall, analyse, persist, propose: shared by the API and the scheduler
evals/              honesty and injection scenarios, judge, record and replay
data_platform/      BigQuery ELT, SQL checks and marts, PySpark job, research model
tests/              pytest suite
```
