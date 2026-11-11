# Axiom Autopilot: rules for coding agents

Source of truth: `PLAN.md` (the product plan) and the code. Ignore git history and the `archive/*` branch.

## Rules
1. Never invent a function, endpoint, env var or SDK name. Open the file and read the signature first. For
   `alpaca-py`, use only the names in `PLAN.md` section 5 or ones confirmed in the installed package source.
2. Do not change the output shape, the first docstring paragraph or the prompts of anything in
   `axiom/services.py`, `axiom/mcp_server/server.py` (the 11 research tools), `axiom/agents/prompts.py`,
   `axiom/quant/risk.py`, `axiom/quant/backtest.py`. The recorded evals are keyed on them. Trading code lives in
   `backend/axiom/trading/`.
3. Never read, print or edit `backend/.env*` except `.env.example`. Run the backend with `DATABASE_URL=` blank
   (local SQLite). `backend/.env.vercel-prod` holds production secrets.
4. Paper only. `TradingClient(..., paper=True)` is hard-coded; no setting enables live trading.
5. Tests never touch the network: use `SimBroker`, `ScriptedLLM` (`axiom/llm/fake.py`), `make_ohlcv`
   (`tests/conftest.py`) and `monkeypatch`.
6. Frontend copy: no em or en dashes, no text under 12px (`src/test/copy.test.ts`). Use `src/components/kit/*`.
7. Report real command output. Never claim a check passed that was not run.

## Checks
```
cd backend
export UV_PROJECT_ENVIRONMENT=C:/Users/Amal/.venvs/axiom   # the F: drive .venv is broken on this machine
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
uv run python -m evals.run --mode replay --recording evals/recordings/qwen3-8b.jsonl --no-judge --report "$TEMP/eval.md" --json "$TEMP/eval.json"
cd .. && npm run lint && npx tsc -p tsconfig.app.json --noEmit && npm test
```
`requirements.txt` must equal `uv export --no-dev --no-hashes --no-emit-project` (CI diffs them).

## Map
```
backend/axiom/trading/   Autopilot: risk kernel, brokers (sim, Alpaca paper), engine, tournament, journal
backend/axiom/quant/     indicators, regime, risk sizing, backtest engine (shared, frozen shapes)
backend/axiom/agents/    research agents (Technical, Fundamental, Risk, Synthesizer, Critic) + guards
backend/axiom/llm/       free LLM fallback chain (Groq, Gemini, OpenRouter, Cerebras, Ollama)
backend/axiom/api/app.py FastAPI: research routes + /api/trader/*
src/pages/AppPage.tsx    the terminal; src/components/autopilot/ is the trading cockpit
```
Ports: API 8000, Vite 5173 (8080 is taken by Oracle on this machine). Python 3.12.
