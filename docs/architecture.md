# Architecture and design decisions

## Principle: code computes, models interpret, policy decides, humans approve

| Layer | Responsibility | Trusts |
|---|---|---|
| `quant/` | indicators, backtests, risk, sizing | nothing but data |
| MCP tools | expose compact, metadata-tagged summaries | `quant/`, providers |
| Agents (LLM) | choose tools, interpret results, write claims | tool results only, never other text |
| Faithfulness gate | prove each claim cites real evidence and real numbers | evidence registry |
| Policy guard | cap rating/conviction from evidence and analyst agreement | evidence registry |
| Human approval | the only path to any external write | the user |

## One analysis run

1. **Fail fast**: the ticker's data must exist before any LLM token is spent.
2. **Analysts in parallel** (bounded concurrency), each with its own tool allowlist.
   Native tool calling, then a validated JSON `Finding`. Guardrails for weak models:
   *nudge* (answered without tools), *prefetch* (a required tool never called is run for it), *repair*
   (schema/citation/stance violations are sent back with the specific reason; for a mis-cited number the message says
   which evidence id actually holds it), and larger token budget on truncated output.
3. **Technical stance rubric** (`policy.technical_expected_stance`): the stance must follow published rules over the
   backtest verdicts and regime. Discovered by evals: an 8B model said "edge detected" in prose but chose `neutral`.
4. **Risk Guard**: `get_risk_metrics` + `size_position` through MCP (traced, citable), limits checked in code.
5. **Synthesizer** steelmans both sides → **Critic** (one pass, revise at most once, skipped if the token budget is >70% used).
6. **Policy guard** applies caps and records each adjustment; model-invented "prior theses" are stripped when none exist.
7. **Position plan** is derived from the *final* rating by code. The thesis is stored immutably; an action plan is proposed.

Failure is graceful: a failed analyst becomes `insufficient_data` and caps conviction; a failed synthesizer yields a
`NO_CALL` memo with the analyst findings; only total LLM outage or budget exhaustion aborts a run (as a clear error event).

## Why these choices

- **Custom orchestration, no LangChain**: explicit control over tokens and a trace that mirrors the code; easy to read.
- **MCP as the only data path**: the agent code is identical in-process, over stdio, or over HTTP, and the same tools are
  reusable from Claude Desktop/Code.
- **OpenAI-compatible provider chain**: one client for Groq, Gemini, OpenRouter and Ollama.
- **SQLite locally, Postgres when deployed**, behind one `Store` (portable SQL in `axiom/db.py`). The response cache and the per-client and daily usage caps live in the same database, so serverless instances share them.
- **Request-keyed LLM cache and recordings**: replay evals and CI at zero cost.

## Security model

- Fetched text is *data*: cleaned, truncated, scanned for instructions aimed at an AI; flagged text is **redacted
  before the model sees it** (not merely excluded from a score); SEC excerpts containing an injection are dropped.
- Per-agent tool allowlists; denied attempts are traced as guardrail events.
- Mutating endpoints need `Authorization: Bearer $AXIOM_API_TOKEN`; with no token they are only permitted while actions
  are dry-run (**fail closed** when Composio is configured).
- The token lives in the user's browser storage, never in the bundle; analyses are rate-limited per client.

## Evals (`backend/evals`)

Fictional ticker "ACME" (no memorised facts) in deterministic synthetic worlds: random walk, clean uptrend, conflicting
analysts, thin data, missing filings, and a **positive control** with a genuine edge (a system that can only say HOLD
would fail it). Five injection payloads run through the real sanitizer *and* forced past it. An **undefended single-prompt
baseline** shows the attacks work on the bare model. An LLM judge scores semantic faithfulness (noisy, same model family).
Run live once to record, replay forever.
