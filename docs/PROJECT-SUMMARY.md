# Axiom: an agentic market-intelligence terminal

**Live demo:** https://axiom-ten-henna.vercel.app (landing at `/`, terminal at `/app`)
**API:** https://axiom-api-three.vercel.app
**Stack:** Python (FastAPI, FastMCP), Postgres (Neon) / SQLite, React + TypeScript + Vite + Tailwind, Vercel.
**Cost to run:** $0. Free LLM tiers, free Postgres, free hosting, free data sources.

## What it is

Axiom takes a stock ticker and runs a team of LLM agents that research it using real tools, argue both sides, and write a cited investment memo. Every number in the memo must trace back to a tool result. A deterministic policy layer can downgrade or block the call. The call is then stored and scored against what the price actually does, so the system accumulates a track record.

It started as a React dashboard that faked its predictions with in-browser mock ML. I rebuilt it as an agentic system with a Python backend, an MCP server, guardrails, evaluations and persistent memory, then redesigned the UI and deployed it.

It is research tooling, not financial advice, and the app says so.

## Architecture

```
Browser (React, Vercel static)
   | fetch + SSE
FastAPI (Vercel Python function)  ----  Vercel Cron (daily briefing, scoring)
   |-- Orchestrator: router -> analysts (parallel) -> synthesizer -> risk critic -> policy
   |-- MCP client  <--MCP-->  Axiom MCP server (11 tools)
   |-- LLM client: fallback chain, response cache, token budget, record/replay
   |-- Memory: runs, theses, outcomes, approvals, usage counters, shared cache
   |       Postgres (Neon) in production, SQLite locally, same SQL seam
   |-- Actions: approval-gated (Notion / Slack / Sheets via Composio), dry-run by default
```

### 1. MCP server (Model Context Protocol)

All data and computation sit behind one MCP server built with FastMCP, so the same tools serve the internal agents, Claude Desktop, Claude Code and any other MCP client. Agents reach the world only through MCP: the in-process client speaks the full MCP protocol, and stdio or streamable-HTTP work the same way.

The 11 tools: `get_price_summary`, `get_indicators`, `get_regime`, `get_risk_metrics`, `get_company_news_sentiment`, `fetch_sec_filing_summary`, `run_backtest`, `run_walk_forward_model`, `get_forecast_cone`, `size_position`, `get_peer_comparison`.

- Every tool returns a JSON envelope with metadata (ticker, as-of date, provider), so claims stay attributable.
- Per-agent tool allowlists, result truncation, 90 s timeouts and full tracing are enforced on the client side (`ToolRunner`).
- Tool descriptions are normalised so recorded evals replay identically on Python 3.12 and 3.13.
- Setup for Claude Desktop and Claude Code is in `docs/mcp-clients.md`.

### 2. Multi-agent orchestration

A deterministic router (the ticker is in the request, so no LLM is needed) starts the specialists in parallel:
- **Technical Analyst:** indicators, regime, backtest, walk-forward model.
- **Fundamental Auditor:** SEC filings, news sentiment, peers.
- **Lead Synthesizer:** merges findings into a structured memo (rating, conviction, thesis, bull and bear case, risks, position plan).
- **Risk Critic:** challenges the synthesis.
- **Policy:** deterministic caps applied last.

Each agent has a tool loop with a nudge if it answers before calling a tool, output repair for invalid or truncated JSON, a per-run token budget (60k) and a call budget. A run deadline ends the stream cleanly before the serverless limit.

### 3. Guardrails

- **Faithfulness check:** every number in a memo is matched against the evidence ids it cites. A figure that is absent, or that appears only in a different source, triggers a repair message naming where it actually appears.
- **Policy caps:** the final rating is capped deterministically. For example, a run where no analyst had enough data is downgraded to NO_CALL. The draft and final ratings are both shown, so a guardrail's work is visible.
- **Prompt-injection defence:** tool output is sanitized, agents can only call allowlisted tools, and actions need explicit approval.
- **Honest degradation:** thin data produces NO_CALL, not an invented view.

### 4. Quant engine

Indicators, regime detection, risk metrics, a backtester with a plain-language verdict, a walk-forward model, a forecast cone, and position sizing. Strategies are judged out of sample so the system cannot claim an edge it has not earned.

### 5. Memory and scorecard

Every run is stored with its thesis. When a call's horizon matures, a scorer records the outcome. A scorecard reports hit rate and calibration, and refuses to show statistics until there are at least 30 scored calls. Runs, theses, outcomes, approvals, watchlist, paper trades and idempotency keys all live in one store.

### 6. Actions with approval

The agent can propose actions (post a digest to Slack, add to a Notion page or a Sheet). Each is a payload the user reviews and approves in the UI. Dry-run is the default. Real execution goes through Composio and fails closed without an API token.

### 7. Evals

A record/replay harness runs agents against fixture scenarios on a fictional ticker, so answers cannot come from memorised facts. Replay is deterministic and runs in CI.

Latest report (`docs/eval-report.md`, model `qwen3:8b` recorded locally):
- 16 of 16 cases pass: 6 honesty scenarios and 10 injection cases.
- 5 of 5 injection cases still avoid STRONG_BUY when the sanitizer is bypassed.
- Positive control: with no defences and a bare prompt, the model obeyed the injection in 4 of 5 cases. This shows the evals can fail, so the defended results mean something.
- An LLM judge supported 48 of 50 memo claims. The judge is the same model family as the agents, so it is a noisy, somewhat self-favouring signal, and the report says so.

### 8. Full-stack product

- **Frontend:** React, TypeScript, Vite, Tailwind, shadcn primitives, Motion, Recharts. Token-based design system with light and dark themes that follow the system, a command palette, a pipeline stepper driven by trace events, a cited memo with evidence popovers, a trace drawer, a forecast-cone chart, and Backtest, Watchlist, Paper trading, Scorecard and Actions tabs.
- **Landing page:** built on a recorded real run (`snapshot.json`), not mock screenshots. It has a scroll-pinned walkthrough, a bento of real results and the real eval numbers.
- **Design guardrails as tests:** WCAG AA contrast on every token pair in both themes, a ban on em/en dashes in copy, and a minimum text size.
- **Tests:** about 159 backend tests (Python 3.12, including a real Postgres 16 in CI) and 88 frontend tests.

### 9. Deployment and production engineering

- **Hosting:** Vercel (static frontend and a Python function), Neon pooled Postgres, Vercel Cron. A Dockerfile for Google Cloud Run is the fallback.
- **One SQL seam for SQLite and Postgres:** placeholder translation, portable upserts, an advisory lock for schema creation, and tests parametrised across both engines. This caught a real bug: `window` is a reserved word in Postgres.
- **Free-quota protection:** per-visitor hourly and global daily caps stored in the database, so they hold across serverless instances. A shared response cache lives in Postgres. One 1500-bar price fetch is sliced per caller instead of about eight separate fetches.
- **Resilience:** an LLM fallback chain (OpenRouter, Groq, with Cerebras, Gemini and Ollama supported), SSE keepalive pings, a run deadline, and cron auth with a bearer secret and constant-time comparison.
- **CI:** lint, format, type and test jobs, a Postgres service, and a check that `requirements.txt` matches `uv.lock`.

## What I learned and what went wrong

- **Free LLM tiers shape the architecture.** Groq's free tier allows 8,000 tokens per minute per model, so a multi-agent run fails on it alone. Free OpenRouter models are mostly reasoning models that spend the token limit thinking, which ended runs as NO_CALL until I sent a reasoning-effort setting. I found both by running against the real services, not from docs.
- **Prompt and tool-output changes invalidate recorded evals.** Recordings are keyed by a hash of the request, so any change needs a re-record. A normalisation fix was needed so recordings replay on both Python 3.12 and 3.13.
- **Vercel's FastAPI preset already serves every path.** My own catch-all rewrite made the app see the wrong path and return 404 until I removed it.

## Honest limits

- The live demo runs on free tiers with daily caps. Some tickers can fail if the unofficial yfinance source is blocked, and no free market-data source clearly permits public redistribution of prices, so treat it as a demo.
- The eval recordings come from a local 8B model, not the free hosted models used in the deployed demo.
- Vercel Hobby is non-commercial.
- The Composio executor is tested against fake clients only, not a live account.
- There are no users and no performance claims. The scorecard needs at least 30 scored calls before it reports anything.

## Resume bullets

**Axiom: agentic market-intelligence terminal** | Python, FastAPI, FastMCP, Postgres, React, TypeScript, Vercel

- Built a multi-agent research system, with parallel technical and fundamental analysts, a synthesizer, a risk critic and a deterministic policy layer, that produces cited investment memos. All tool access goes through an 11-tool MCP server that also works from Claude Desktop and Claude Code.
- Designed guardrails that check every number in a memo against the evidence it cites, cap ratings deterministically, and degrade to NO_CALL on thin data. This included a prompt-injection defence and approval-gated actions through Composio.
- Wrote a record/replay eval harness. All 16 cases pass, including 10 injection cases. A no-defence control obeyed the injection in 4 of 5 cases, so the results can fail and mean something.
- Deployed free end to end on Vercel and Neon. A single SQL layer runs on SQLite and Postgres, with database-backed rate limits and cache, a run deadline and cron scoring. I tested it against real Postgres in CI, and about 159 backend and 88 frontend tests pass.
- Redesigned the UI as a light and dark product with a landing page built from a real recorded run. Design rules such as WCAG AA contrast are enforced by tests.

**Shorter version (3 bullets):**
- Built and deployed a free-tier agentic stock-research terminal: an MCP server with 11 tools, a multi-agent pipeline, and a Python FastAPI backend with Postgres on Vercel.
- Engineered guardrails and evals: a number-to-evidence faithfulness check, deterministic policy caps, injection tests with a no-defence control, and about 159 backend and 88 frontend tests.
- Shipped a React and TypeScript UI with light and dark themes and a landing page built from a real run, plus database-backed quotas and cron scoring to stay inside free limits.
