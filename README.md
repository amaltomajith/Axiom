# Axiom

**An autonomous market-research terminal built to be honest about uncertainty.**

Axiom lets a small team of AI agents research a stock through standard **MCP tools**, argue both sides, and
write a memo in which *every number links to the tool call that produced it*. The maths (indicators,
backtests, risk, sizing) is plain tested code, the LLMs only reason and explain, a deterministic policy layer caps
what they may conclude, and every call is later **scored against what the price actually did**.

It runs on a **free stack**: Groq / Gemini / OpenRouter free tiers with an automatic fallback chain, or fully offline on
a local Ollama model. No paid API key is required.

> Research tooling, not financial advice. Axiom is paper-trading only: there is no brokerage connection.

Deep dive: [docs/architecture.md](docs/architecture.md) · Eval results: [docs/eval-report.md](docs/eval-report.md)

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
React UI (Vite, Tailwind, shadcn)  ──SSE──►  FastAPI  ──►  Orchestrator
 live Agent Trace · cited memo                              ├─ Technical Analyst ┐  (tool allowlists, evidence ids)
 cone chart · backtest verdicts                             ├─ Fundamental Auditor ┤
 approval queue · scorecard                                 ├─ Risk Guard (tools + code)
                                                            ├─ Lead Synthesizer ─► Critic ─► Policy guard
                                                            └─ Faithfulness gate · token budget
                                                                     │ MCP (in-process / stdio / HTTP)
                                                            Axiom MCP server (FastMCP)
                                                            ├─ price / indicators / regime / risk / forecast cone
                                                            ├─ backtest + walk-forward model (quant/)
                                                            ├─ news (+ injection redaction) · SEC EDGAR filings
                                                            └─ position sizing · peers
                                  Actions (Composio) ◄── approval gate ── Memory (SQLite/Postgres): runs · theses · outcomes
```

The **same MCP server** powers the web app *and* can be added to Claude Desktop / Claude Code: see
[docs/mcp-clients.md](docs/mcp-clients.md).

## Quick start

Requirements: Node 18+, Python 3.11+ with [uv](https://docs.astral.sh/uv/), and optionally [Ollama](https://ollama.com) (`ollama pull qwen3:8b`).

```bash
# 1. backend
cd backend
cp .env.example .env            # all optional; add a free Groq/Gemini key for speed
uv sync
uv run python -m axiom.api      # http://localhost:8000

# 2. frontend (new terminal)
npm install
npm run dev                     # landing page: http://localhost:5173  terminal: http://localhost:5173/app
```

With no keys at all it uses yfinance + Google News RSS + SEC EDGAR + local Ollama. A full agent run takes
about 20 to 60 seconds on a small local model and 5 to 15 seconds on Groq.

### Useful commands

```bash
uv run pytest                                   # 142 backend tests (quant, MCP, agents, API, actions, memory)
npm test && npm run lint && npm run build       # frontend
uv run python -m axiom.mcp_server               # the MCP server over stdio
npx @modelcontextprotocol/inspector uv run python -m axiom.mcp_server   # poke the tools by hand
uv run python -m evals.run --mode replay --recording evals/recordings/qwen3-8b.jsonl   # evals at $0
uv run python -m axiom.scheduler --once         # daily briefing now
uv run python -m axiom.actions.composio_check   # verify Composio tool slugs
```

## Design

Two routes: `/` is a landing page that explains the system using a recorded real run (no mock numbers), and `/app` is the terminal.
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

## Free-tier strategy

Free tiers fail with `429`s rather than bills, and the real limit is usually tokens per minute. So:

- one OpenAI-compatible client over **Cerebras / Groq → Gemini → OpenRouter free → Ollama**, with `Retry-After`-aware
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
src/                 React app (tabs: Analyze, Backtest, Watchlist, Paper trade, Scorecard, Actions)
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
backend/data_platform/  BigQuery ELT: tables.yaml, extract/load, staging + mart SQL, synthetic seed
refs/                the original design blueprint
```

## License

MIT
