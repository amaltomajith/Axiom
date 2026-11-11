# Axiom backend

The Python side of Axiom: the Autopilot paper trader (`axiom/trading/`), the API the terminal calls, the MCP server,
the research agents and their guardrails, memory, approvals and evals. For the whole project start at the
[root README](../README.md).

Python 3.12 with [uv](https://docs.astral.sh/uv/). Every command below runs from this folder.

```bash
uv sync                          # add --extra actions for Composio
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
| `uv run python -m axiom.api` | FastAPI app on `HOST`:`PORT` (default 127.0.0.1:8000). `SERVE_FRONTEND=true` also serves the `npm run build:selfhost` bundle | Nothing. An LLM key or Ollama for analysis |
| `uv run python -m axiom.trading backtest [--symbols A,B] [--bars N] [--save]` | Time Machine: the live engine over history, writes `docs/backtest-report.md` and `.json` | Nothing (yfinance daily bars) |
| `uv run python -m axiom.trading run` | The live trading loop without the API | Alpaca keys for `TRADER_BROKER=alpaca` |
| `uv run python -m axiom.trading status [-n 15]`, `kill [reason]`, `resume` | State and journal; the kill switch (writes or removes `backend/KILL`) | Nothing |
| `uv run python scripts/alpaca_smoke.py [--trade]` | Check the Alpaca paper account; `--trade` does a ~$10 BTC/USD round trip with a stop | Alpaca paper keys |
| `uv run python -m axiom.mcp_server [--transport streamable-http --port 8765]` | The 11 research tools over MCP (stdio by default). See [MCP clients](../docs/mcp-clients.md) | Nothing |
| `uv run python -m axiom.scheduler --once [TICKERS]` | The daily briefing now: score matured theses, analyse the watchlist, propose one digest | An LLM |
| `uv run python -m axiom.actions.composio_check` | List the configured Composio tool slugs and their parameters | `COMPOSIO_API_KEY`, `--extra actions` |
| `uv run python -m evals.run --mode replay --recording evals/recordings/qwen3-8b.jsonl` | Honesty and injection evals from a recording, at $0 (`--no-judge` skips the judge) | Nothing |
| `uv run python -m evals.run --mode record --recording <file>` | Record a fresh eval run. Needed after any prompt or tool-output change | An LLM (about 10 min on qwen3:8b) |
| `uv run python scripts/capture_snapshot.py` | Rewrite the landing page data (`src/landing/snapshot.json`) and `docs/eval-report.md` | The API running, one stored run |
| `uv run pytest` | The test suite, offline. Postgres tests skip unless their env var is set | Nothing |

Deployed: `api/index.py` is the Vercel entry and `vercel.json` adds the weekday cron
(`/api/cron/daily`, 13:00 UTC). `Dockerfile` is the Cloud Run or any-container fallback. Steps:
[deployment](../docs/deployment.md).

## HTTP routes

Research routes are in `axiom/api/app.py`, trader routes in `axiom/trading/api.py`. "Token" means
`Authorization: Bearer $AXIOM_API_TOKEN`.

### Autopilot (`/api/trader/*`)

Reads are public. Every POST needs the token, or, when no token is set, a direct request from the same machine with
no proxy or tunnel headers. `?session=live` (default) or `replay:<id>` picks the ledger.

| Route | Purpose |
|---|---|
| `GET status` | Kill and halt state, autonomy level and ladder progress, risk budget, account, pending approvals, LLM calls left |
| `GET positions`, `orders`, `equity`, `tournament` | Book, order log, equity against buy-and-hold, current strategy picks |
| `GET journal`, `journal/verify` | The plain-language journal and its hash-chain check |
| `GET contracts`, `calibration` | Trade contracts and their grades, Brier score and calibration buckets |
| `GET backtest/report`, `replays[/{id}]`, `stream` | The Time Machine report, replay jobs, and server-sent events |
| `POST kill`, `resume`, `start`, `stop` | Kill switch (flattens everything), release, start or stop the loop |
| `POST autonomy`, `orders/{id}/approve\|reject` | Set the autonomy level (optionally as a ceiling); approve or reject a supervised entry |
| `POST replay`, `replays/{id}/stop`, `redteam` | Run a Time Machine replay; fire an absurd order and a poisoned headline at the kernel |

### Research

| Route | Purpose |
|---|---|
| `GET /api/health` | Config snapshot. The terminal polls it to wake the function |
| `GET /api/status` | Health plus aggregate counts (runs, theses, approvals, today's analyses) |
| `GET /api/market/{t}/ohlcv`, `GET /api/quant/{t}/summary\|indicators\|regime\|risk\|forecast\|backtest\|walk-forward` | Prices and the quant layer |
| `GET /api/news/{t}`, `GET /api/filings/{t}`, `GET /api/tickers/search` | News with sentiment, SEC summary, ticker lookup |
| `POST /api/analyze`, `GET /api/analyze/stream` | One research run as SSE (POST for fetch, GET for `EventSource`), rate limited |
| `GET /api/runs[/{id}]`, `GET /api/theses`, `GET /api/scorecard`, `POST /api/score` (token) | Stored runs, theses and the track record |
| `GET /api/actions[/{id}]`, `POST /api/actions/{id}/approve\|retry\|reject` (token) | The approval queue |
| `GET\|PUT\|DELETE /api/watchlist[/{t}]` (writes: token) | The owner's watchlist, which the scheduler uses |
| `GET\|POST /api/trades`, `POST /api/trades/{id}/close`, `DELETE /api/trades/{id}` (writes: token) | The manual paper-trade ledger (separate from Autopilot) |
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
| `CORS_ORIGINS` | localhost 8080, 5173 and 4200 | Front-end origins allowed to call the API (not needed with `SERVE_FRONTEND`) |
| `RUN_DEADLINE_SECONDS` | `0` (off) | Stop a run cleanly before a serverless time limit |
| `CRON_SECRET` | none | Enables `/api/cron/daily` |
| `SCHEDULER_ENABLED` | `false` | Run the briefing inside a long-lived API process instead of cron |
| `COMPOSIO_API_KEY` | none | Real Notion, Sheets and Slack actions; dry run without it |
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | none | Alpaca **paper** keys: equity bars, news and `TRADER_BROKER=alpaca` |
| `TRADER_ENABLED` | `false` | Start the live loop with the API (never on serverless) |
| `TRADER_BROKER`, `TRADER_BRAIN` | `sim`, `rule` | `alpaca` for the paper account; `llm` lets the free LLM chain choose or veto |
| `TRADER_SYMBOLS`, `TRADER_TIMEFRAME`, `TRADER_INTERVAL_SECONDS` | 7 symbols, `1Hour`, `60` | Universe, bar size, loop period |
| `TRADER_AUTONOMY_START` | `SUPERVISED` | `SHADOW`, `SUPERVISED` or `AUTONOMOUS` |
| `TRADER_DAILY_LOSS_LIMIT_PCT`, `TRADER_RISK_PER_TRADE`, `TRADER_MAX_POSITION_PCT`, ... | `0.02`, `0.01`, `0.20` | Risk kernel limits; the full list is in `axiom/config.py` |
| `TRADER_MAX_LLM_CALLS_PER_HOUR` | `20` | Cap on LLM brain calls |
| `SERVE_FRONTEND`, `FRONTEND_DIST` | `false`, `../dist` | Serve the built frontend from the API for a one-port demo |

## Layout

```
axiom/trading/      Autopilot: risk kernel, brokers (sim, Alpaca paper), engine, tournament, contracts, autonomy,
                    LLM brain, journal, Time Machine, report, service and routes
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
tests/              pytest suite
```
