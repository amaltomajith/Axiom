# Axiom Autopilot

**A paper-trading agent that has to earn its autonomy.**

Autopilot reads market data and news, picks a strategy per symbol in a walk-forward tournament, and trades an
[Alpaca](https://alpaca.markets) **paper** account (or a built-in simulator). Every order passes through a deterministic
risk kernel that no model can override. Before each entry the agent writes a falsifiable *trade contract* (odds,
target, exits), and every contract is graded when it closes. Those grades decide how much freedom it gets.

It runs on a **free stack**: free LLM tiers (Groq, Gemini, OpenRouter, Cerebras) with a fallback chain, or a local
Ollama model, plus Alpaca's free paper account and data.

> Paper only. `TradingClient(..., paper=True)` is hard-coded and no setting enables real money. Not financial advice.

## What PS-02 asks for, and where it is

| Requirement | How Autopilot does it | Code | Proof |
|---|---|---|---|
| Paper account only | Alpaca paper (`paper=True`, hard-coded) or `SimBroker`; the kernel's rule R1 refuses anything else | `trading/broker/` | `test_trading_kernel.py`, PAPER badge in the cockpit |
| Reads market data and news | Alpaca intraday bars (crypto keyless, equities on IEX), yfinance daily bars; Alpaca news, point in time, sanitised, injection headlines redacted | `trading/data.py` | `test_trading_llm.py` |
| Picks or adapts a strategy | Walk-forward tournament: 5 strategies scored on trailing out-of-sample windows per symbol; only qualifiers trade; none means cash | `trading/tournament.py` | `test_trading_engine.py` |
| Backtest against buy-and-hold | **Time Machine**: the live engine replayed over history, so no look-ahead by construction; bootstrap verdict with a 95% CI | `trading/replay.py`, `report.py` | [docs/backtest-report.md](docs/backtest-report.md) |
| Position sizing, stop-losses, daily loss limit | Kernel sizes every order at 1% equity risk, requires a stop (checked each tick and held at the broker), halts and flattens at a 2% daily loss | `trading/risk.py` | one test per rule R0 to R12 |
| Human kill switch, hard guardrails | Kill button, `POST /api/trader/kill`, CLI, or a `backend/KILL` file; flattens everything and blocks new entries until released | `trading/engine.py`, `api.py` | `test_trader_api.py` |
| Plain-language journal per trade | Every decision, including trades *not* taken, in plain English with its facts, sha256 hash-chained so edits are detectable | `trading/journal.py` | chain check badge in the cockpit |

## What is new here

1. **A risk kernel the LLM cannot touch.** The model never sees an order API and never sets a quantity. Pure code
   sizes or blocks every intent (rules R0 to R12) and journals the blocks too.
2. **Trade contracts.** Before each entry: stated confidence, expected move, horizon, machine-checkable invalidation
   (stop, signal flip, time stop, regime change). Graded at close (A to D, Brier score, calibration buckets).
3. **Earned autonomy ladder.** `SHADOW` (decides, trades nothing) to `SUPERVISED` (a human approves each entry) to
   `AUTONOMOUS`. Promotion needs enough graded contracts, good calibration and a positive net return. A daily loss
   halt, a losing streak or poor calibration demotes it. A human can set a ceiling.
4. **An honest LLM boundary.** The LLM brain may only choose among strategies that qualified and are signalling, or
   veto. Its numbers are checked against the facts it was given; any failure falls back to the rule brain. It is never
   backtested over history (models remember the past), only judged forward on paper by its contracts.
5. **Red team button.** Fires an absurd order and a poisoned headline at the agent, live, and shows both being stopped.
6. **Reports that can say no.** The current report's verdict is `no_edge`: the agent made +2.2% over 3.4 years against
   +120.2% for buy-and-hold, with a smaller drawdown (-18.8% against -31.3%). It is published anyway.

```
bars + news ──> tournament ──> Brain.decide ──> OrderIntent ──> RiskKernel.review ──> Broker ──> journal
(data.py)     (qualified set)  (Rule | LLM)    (no quantity)    (sizes, or blocks)   (Sim | Alpaca paper)
                                    └── trade contract ── graded at close ── calibration ── autonomy ladder
```

More in [docs/architecture.md](docs/architecture.md).

## Quick start

Requirements: Node 20+, Python 3.12 with [uv](https://docs.astral.sh/uv/), optionally [Ollama](https://ollama.com).

```bash
npm install && (cd backend && uv sync)    # once
cp backend/.env.example backend/.env      # optional: Alpaca PAPER keys, a free Groq or Gemini key
npm run dev:all                           # API on :8000 and the terminal on :5173; Ctrl+C stops both
```

Open http://localhost:5173/app. The **Autopilot** tab is the cockpit: status, autonomy ladder, risk budget meters,
kill switch, approval queue, positions with stops, the journal, equity against buy-and-hold, contracts and
calibration, the backtest report and the Time Machine. With no keys at all it runs on `SimBroker` and the rule brain.

The research terminal Axiom started as is still there (Analyze, Backtest, Watchlist, Scorecard, Actions tabs): agents
that research a stock through 11 MCP tools and cite every number. See [docs/mcp-clients.md](docs/mcp-clients.md) and
[docs/eval-report.md](docs/eval-report.md).

### Trading commands (inside `backend/`)

```bash
uv run python -m axiom.trading backtest              # Time Machine over 1,500 daily bars per symbol, writes docs/backtest-report.*
uv run python -m axiom.trading run                   # the live loop on its own (or TRADER_ENABLED=true with the API)
uv run python -m axiom.trading status                # state and the latest journal entries
uv run python -m axiom.trading kill "reason"         # kill switch: flatten and block; `resume` releases it
uv run python scripts/alpaca_smoke.py [--trade]      # check the Alpaca paper account (--trade: a ~$10 BTC round trip)
```

Trader settings (`TRADER_*`, `ALPACA_*`) are documented in [backend/.env.example](backend/.env.example).
US equities trade about 8:00 PM to 2:30 AM IST; Alpaca paper trades **crypto 24/7**, so the live demo runs BTC/USD and
ETH/USD and equities run in the Time Machine.

## Demo on one port with a public URL

```bash
npm run build:selfhost                                              # the frontend, calling the API on its own origin
cd backend && SERVE_FRONTEND=true AXIOM_API_TOKEN=<long random> DATABASE_URL= uv run python -m axiom.api
cloudflared tunnel --url http://localhost:8000                      # free quick tunnel, no account; prints a trycloudflare.com URL
```

Visitors through the tunnel can read everything but change nothing: every POST needs the token, and tunnelled requests
never count as local. Paste the token with the key icon in the header to drive it yourself. Quick tunnels do not carry
server-sent events, so the cockpit falls back to polling every 5 seconds. Details: [docs/deployment.md](docs/deployment.md).

## Checks

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest -q
uv run python -m evals.run --mode replay --recording evals/recordings/qwen3-8b.jsonl --no-judge
cd .. && npm run lint && npx tsc -p tsconfig.app.json --noEmit && npm test && npm run build
```

Tests never touch the network: `SimBroker`, a fake `TradingClient`, `ScriptedLLM` and synthetic bars.

## Honest limitations

- The rule brain has not shown an edge over buy-and-hold in the Time Machine, and the report says `no_edge`. What it
  offers is control: smaller drawdowns, hard limits, and a record of every decision.
- The LLM brain is judged only forward, on paper, by its contracts. A few days of contracts is a small sample; the
  ladder and the calibration chart say how many there are.
- Alpaca paper fills are simulated by Alpaca (no fees, random partial fills). The Time Machine charges 30 bps on
  crypto and 10 bps on equities to stay conservative.
- Free LLM tiers rate-limit; calls are capped per hour and any failure falls back to the rule brain, marked degraded.

## Layout

```
src/pages/AppPage.tsx             the terminal; Autopilot is the default tab
src/components/autopilot/         the cockpit: control bar, journal, book, performance, Time Machine
src/landing/                      landing page (hero uses the real backtest report)
backend/axiom/trading/            risk kernel, brokers (sim, Alpaca paper), engine, tournament, contracts,
                                  autonomy ladder, LLM brain, journal, Time Machine, report, API routes
backend/axiom/quant/              indicators, regime, sizing, backtest maths (shared with research)
backend/axiom/agents/, mcp_server/  the research agents and their 11 MCP tools
backend/axiom/llm/                free LLM fallback chain with budgets and a scripted fake
docs/                             architecture, backtest report, deployment, MCP clients, eval report
```

## License

MIT
