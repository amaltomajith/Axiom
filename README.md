# Axiom

**An autonomous market-research terminal built to be honest about uncertainty.**

Axiom lets a small team of AI agents research a stock through standard **MCP tools**, argue both sides, and
write a memo in which *every number links to the tool call that produced it*. The maths (indicators,
backtests, risk, sizing) is plain tested code, the LLMs only reason and explain, a deterministic policy layer caps
what they may conclude, and every call is later **scored against what the price actually did**.

It runs on a **free stack**: free LLM tiers (Groq, Gemini, OpenRouter, Cerebras) with an automatic fallback chain, or
fully offline on a local Ollama model. No paid API key is required.

> Research tooling, not financial advice. Axiom is paper-trading only: there is no brokerage connection.

**Everything in one place: the [hub](https://axiom-ten-henna.vercel.app/hub)** shows each part below with live status,
how to run it and its docs. Locally it is at http://localhost:5173/hub.

## The parts

| Part | What you get | Live | Code | Run just this part |
|---|---|---|---|---|
| **Axiom terminal** (React) | The main app: run the agents on a ticker, read the cited memo, backtests, paper trades, scorecard, approvals | https://axiom-ten-henna.vercel.app | [`src/`](src/) | `npm run dev` |
| **Axiom Watch** (Angular) | A lighter app: ticker search, a personal watchlist with no sign-in, a live step-by-step run monitor | https://axiom-watch.vercel.app | [`angular/`](angular/) | `cd angular && npm start` |
| **Axiom API** (FastAPI) | The backend both apps call: agents, guardrails, memory, approvals, weekday cron | https://axiom-api-three.vercel.app (try `/api/status`) | [`backend/axiom/`](backend/axiom/) | `cd backend && uv run python -m axiom.api` |
| **MCP server** | The same 11 research tools, for Claude Desktop or Claude Code | runs on your machine | [`backend/axiom/mcp_server/`](backend/axiom/mcp_server/) | `cd backend && uv run python -m axiom.mcp_server` |
| **Data platform** | Weekday BigQuery ELT of the app's runs, with data-quality checks and marts | [GitHub Actions](https://github.com/amaltomajith/Axiom/actions/workflows/data-platform.yml) | [`backend/data_platform/`](backend/data_platform/) | `cd backend && uv run python -m data_platform run --env dev` |

Every doc, and whether it is still current: [docs/README.md](docs/README.md). The Python side in detail:
[backend/README.md](backend/README.md). Design deep dive: [docs/architecture.md](docs/architecture.md). Eval results:
[docs/eval-report.md](docs/eval-report.md).

## What makes it different

| Claim | How it is enforced | Where it is measured |
|---|---|---|
| Agents don't invent numbers | Every claim must cite a tool-call id; a mechanical checker proves each number exists (with rounding/unit tolerance) in the cited result, and tells the model *which* id actually holds it | `agents/faithfulness.py`, evals |
| LLMs can't hype a stock | Post-hoc policy: conflicting analysts → HOLD, no statistical edge → no STRONG rating, thin data → capped conviction | `agents/policy.py`, evals |
| Backtests don't flatter | No lookahead (tested by truncation invariance), costs + slippage, benchmark vs buy-and-hold, paired block-bootstrap verdict: `no_edge` / `unproven` / `edge_detected` | `quant/backtest.py` |
| Prompt injection is handled | Untrusted text is sanitised, injection-looking headlines are *redacted before the model sees them*, plus model/policy defences | `security.py`, evals (undefended baseline obeys 4/5 attacks) |
| Agents can't act unsupervised | Actions are *proposed*, shown as exact payloads, run only after approval, each step at most once (idempotency keys) | `actions/`, API |
| "AI predictions" are accountable | Every memo becomes an immutable thesis, scored at its horizon vs the price and SPY, with Brier calibration and per-agent hit rates, and the UI says when n is too small to mean anything | `memory/`, Scorecard tab |

## Architecture

```
React terminal (Vite, Tailwind)    ──SSE──►  FastAPI  ──►  Orchestrator
Axiom Watch (Angular, NgRx)  ──EventSource──►               ├─ Technical Analyst ┐  (tool allowlists, evidence ids)
                                                            ├─ Fundamental Auditor ┤
                                                            ├─ Risk Guard (tools + code)
                                                            ├─ Lead Synthesizer ─► Critic ─► Policy guard
                                                            └─ Faithfulness gate · token budget
                                                                     │ MCP (in-process / stdio / HTTP)
                                                            Axiom MCP server (FastMCP)
                                                            ├─ price / indicators / regime / risk / forecast cone
                                                            ├─ backtest + walk-forward model (quant/)
                                                            ├─ news (+ injection redaction) · SEC EDGAR filings
                                                            └─ position sizing · peers
                                  Actions (Composio) ◄── approval gate ── Memory (SQLite/Postgres): runs · theses · outcomes
                                                                     │ weekday ELT through a read-only role
                                                            BigQuery: raw → staging → data-quality gate → marts
```

The **same MCP server** powers the web app *and* can be added to Claude Desktop / Claude Code: see
[docs/mcp-clients.md](docs/mcp-clients.md).

## Quick start

Requirements: Node 20+ (Axiom Watch needs Node 24, or 22.22.3+), Python 3.12 with [uv](https://docs.astral.sh/uv/), and
optionally [Ollama](https://ollama.com) (`ollama pull qwen3:8b`).

```bash
npm install && (cd angular && npm install) && (cd backend && uv sync)   # once
cp backend/.env.example backend/.env    # optional: add a free Groq or Gemini key for speed

npm run dev:all                         # API, terminal and Axiom Watch together; Ctrl+C stops all three
```

| Open | For |
|---|---|
| http://localhost:5173/hub | The hub: every part, with status |
| http://localhost:5173 and `/app` | Landing page and the terminal |
| http://localhost:4200 | Axiom Watch |
| http://localhost:8000/api/status | The API |

The launcher ([`scripts/dev.mjs`](scripts/dev.mjs), `npm run dev:all -- --help`) prefixes each log line with its part,
skips a part whose port is busy, borrows a newer Node from nvm for Angular if yours is too old, and **keeps the local
API on SQLite even when `backend/.env` holds the production `DATABASE_URL`** (`--prod-db` overrides that).
`--only api,terminal` starts a subset.

With no keys at all it uses yfinance + Google News RSS + SEC EDGAR + local Ollama. A full agent run takes
about 20 to 60 seconds on a small local model and 5 to 15 seconds on Groq.

### Useful commands

Python commands run inside `backend/`; the full list is in [backend/README.md](backend/README.md).

```bash
uv run pytest                                   # 206 backend tests (Postgres and real-BigQuery ones skip without their env vars)
npm test && npm run lint && npm run build       # React: 97 tests, including copy, contrast and hub-manifest guardrails
(cd angular && npx ng test --watch=false)       # Axiom Watch: 116 tests
uv run python -m axiom.mcp_server               # the MCP server over stdio
npx @modelcontextprotocol/inspector uv run python -m axiom.mcp_server   # poke the tools by hand
uv run python -m evals.run --mode replay --recording evals/recordings/qwen3-8b.jsonl   # evals at $0
uv run python -m axiom.scheduler --once         # daily briefing now
uv run python -m axiom.actions.composio_check   # verify Composio tool slugs
```

## Design

Three routes: `/` is a landing page that explains the system using a recorded real run (no mock numbers), `/app` is the
terminal, and `/hub` maps every part of the project with live status.
The design follows Apple's fluid-interface principles (instant response, critically damped springs, interruptible motion,
translucent materials only on chrome, optical type) with a strict token system in `src/index.css`:

- one accent (the logo's sky blue), semantic gain/loss/warn colours, light and dark designed together, both checked for WCAG AA by a test;
- Geist and Geist Mono, a type scale with no sub-12px text, tabular numerals, one shape rule (controls 10px, surfaces 16px);
- aligned lists built on one CSS grid per table, so figures line up; skeletons shaped like the final content so nothing shifts;
- the agent trace is a drawer (vaul) and the run progress is derived from real trace events, never invented.

Refresh the landing data after you have run an analysis: `cd backend && uv run python scripts/capture_snapshot.py`.

## Deploy

Free tiers, no card: Vercel (static frontend + Python function), Neon Postgres, free LLM providers, Vercel Cron for
the daily briefing. A Dockerfile covers Cloud Run if Vercel's limits get in the way. Full steps, the env table and a
ten-minute verification checklist are in [`docs/deployment.md`](docs/deployment.md).

## Axiom Watch (Angular)

[`angular/`](angular/) holds **Axiom Watch**, a second front end written in Angular, RxJS and NgRx: a per-visitor
watchlist with prices and the last rating, search-as-you-type for tickers, and a live monitor for a research run's
pipeline, streamed over `EventSource`. It is deployed as its own Vercel project (https://axiom-watch.vercel.app), ships
a multi-stage Docker image (Node build, nginx serve), and links back to the hub. How it works and why each RxJS operator was chosen:
[`angular/LEARNING.md`](angular/LEARNING.md). Run, test and deploy steps: [`angular/README.md`](angular/README.md).

## Data platform

A BigQuery warehouse built *beside* the agents (it never calls an LLM or touches prompts and tools). It runs in the
BigQuery sandbox, so no card is needed. Measured results are in [`RESULTS.md`](RESULTS.md).

```bash
cd backend && uv sync --extra data
uv run python -m data_platform seed                                     # synthetic source DB for development
uv run python -m data_platform run --env dev  --project <gcp-project>   # synthetic SQLite -> axiomdev_* datasets
uv run python -m data_platform run --env prod --project <gcp-project>   # Neon, read-only role -> axiom_* datasets
uv run python -m data_platform dryrun --env prod --project <gcp-project>  # bytes each query would scan
```

- **Layers.** `raw` is an append-only change log written by batch load jobs. `staging` holds typed rows, one per key
  (newest version). `mart` holds the scorecard (empty below 30 directional calls, like the app), tool latency
  percentiles, LLM tokens per day with a 7-day average, and rolling price indicators.
- **Config-driven.** [`backend/data_platform/tables.yaml`](backend/data_platform/tables.yaml) lists each table with
  its key, its watermark and whether it loads incrementally or as a full snapshot. Adding a table means adding an
  entry there and a staging `.sql` file.
- **Sandbox-safe.** The sandbox blocks DML and streaming, so the pipeline uses neither. Re-runs are idempotent
  because they skip versions already loaded and rebuild staging with `QUALIFY ROW_NUMBER()`. Price tables use
  integer-range partitions on the day number, because the sandbox's 60-day partition expiry would silently drop
  older date partitions.
- **Data-quality gate.** After staging, the SQL checks in
  [`backend/data_platform/sql/dq/`](backend/data_platform/sql/dq) cover keys, accepted values, ranges, references,
  freshness and source-vs-warehouse row counts. Results are appended to `mart.dq_results`. A failed critical check
  stops the run before the marts and exits with code 3. Warnings are recorded only.
- **Private.** Client IPs are redacted before loading. Price data is never published.
- **Access.** The prod source is a read-only Postgres role, given in `backend/.env.data` (gitignored). In BigQuery, a
  loader and a dashboard-reader service account get per-dataset roles. See
  [`docs/gcp-governance.md`](docs/gcp-governance.md).
- **Scheduled.** [`.github/workflows/data-platform.yml`](.github/workflows/data-platform.yml) runs the prod pipeline on
  weekdays as the loader, through Workload Identity Federation (no stored key).
- **PySpark.** `python -m data_platform.spark.bench` runs the indicators in Spark (Docker), checks them row for row
  against Axiom's pandas code, and times both, on Federal Reserve H.10 exchange rates (public domain) and synthetic data.
- **Research model.** `python -m data_platform.research.direction_model [--bqml --project <id>]` is a time-split
  direction model with baselines, leakage tests and a BigQuery ML twin. It isn't used by the agents.
- Design: [`docs/gcp-architecture.md`](docs/gcp-architecture.md). Every number: [`RESULTS.md`](RESULTS.md).

## Free-tier strategy

Free tiers fail with `429`s rather than bills, and the real limit is usually tokens per minute. So:

- one OpenAI-compatible client over **Groq → Gemini → OpenRouter free → Ollama** by default (set by `LLM_CHAIN`;
  Cerebras is available too, and the live demo runs OpenRouter then Groq), with `Retry-After`-aware
  backoff, a process-wide cooldown for rate-limited providers, and per-run token and call budgets;
- MCP tools return *computed summaries*, never raw price arrays, and all arithmetic happens in code;
- identical requests are cached, and evals record once then replay deterministically at zero cost;
- bad tickers fail before any LLM call; analyses are capped per client and per day, in the database, so the caps hold across serverless instances.

## Honest limitations

- Daily bars, not real-time. The header says so.
- News sentiment is a transparent keyword baseline (Finnhub's sentiment endpoint is premium-only).
- The mechanical faithfulness check proves a number *exists* in the cited result, not that it means what the claim says
  (the evals use an LLM judge for that: a noisy signal, documented as such).
- Small free models need guardrails: the loop nudges, prefetches and repairs (counts are reported in
  [docs/eval-report.md](docs/eval-report.md)).
- The Composio path is built to the SDK's documented interface but has **not been exercised against a live account**:
  everything else around it (planner, approval, idempotency, argument mapping) is tested with a fake client.
- Backtests of a handful of simple rules on one stock are not evidence of an edge; Axiom says so when it is the case.

## Layout

```
src/                 React app: landing, terminal (Analyze, Backtest, Watchlist, Paper trade, Scorecard, Actions), hub
src/hub/parts.ts     the list of parts and docs behind the hub page (tests keep it in step with the repo)
angular/             Axiom Watch: Angular + RxJS + NgRx watchlist and live run monitor
scripts/dev.mjs      npm run dev:all, the one-command local launcher
backend/axiom/
  quant/             indicators, regime, walk-forward backtester, forecast cone, risk (pure, tested)
  data/              market (Twelve Data/yfinance), news, SEC EDGAR, cache, rate limits
  mcp_server/        FastMCP server: 11 tools, resources, prompts
  agents/            loop, orchestrator, policy, faithfulness, risk guard, prompts, toolbox (MCP client)
  llm/               provider chain, client (failover/budget/cache), scripted fake
  actions/           planner, approval gate, Composio + dry-run executors
  memory/            store (SQLite or Postgres), outcome scorer, scorecard
  api/               FastAPI app (SSE analysis stream, memory, approvals)
backend/evals/       honesty scenarios, injection attacks + undefended control, judge, record/replay
backend/data_platform/  BigQuery ELT: tables.yaml, extract/load, staging + mart SQL, synthetic seed, Spark, research
docs/                architecture, deployment, MCP, data platform, eval report (index: docs/README.md)
refs/, reports/      the original blueprint and the hosting research (historical)
```

## License

MIT
