# Deploying Axiom on free tiers

Two shapes. **The Autopilot demo runs on a laptop** with a public URL, because the trading loop needs a long-lived
process (section 0). The research terminal can also be deployed to serverless free tiers (sections 1 to 7); there the
trader does not run, since `TRADER_ENABLED` is ignored on serverless.

## 0. Autopilot demo: one laptop, one port, a free public URL

The short way (Git Bash, from the repo root):

```bash
npm run build:selfhost
scripts/live-demo.sh start      # API + cockpit on :8000, a quick tunnel and keep-awake, each detached
scripts/live-demo.sh url        # the tunnel URL; it changes whenever the tunnel restarts
scripts/live-demo.sh status     # loops, storage (must say sqlite), the tunnel URL and the fixed link
scripts/live-demo.sh stop
```

It runs `TRADER_BROKER=alpaca`, `TRADER_BRAIN=desk`, BTC/USD and ETH/USD, Supervised, with `TRADER_GUEST_ACTIONS=true`,
and forces `DATABASE_URL` empty so the demo never touches a production database named in `backend/.env`. Keys and
`AXIOM_API_TOKEN` come from `backend/.env`. Logs: `backend/.cache/autopilot-live.log` and `backend/.cache/tunnel.log`.

**The fixed link** is `https://axiom-autopilot.work-amaltom.workers.dev`, a free Cloudflare Worker in
`deploy/cloudflare/`. Every time the tunnel starts, the script writes the new tunnel URL to the Worker's KV store, and
the Worker sends each visitor there with a redirect after checking `/api/health` answers. If the laptop is off it
shows "offline" and checks again every 20 seconds; `stop` sets it to offline on purpose. It redirects instead of
proxying, so a polling cockpit uses one Worker request per visit and stays far inside the free 100,000 a day. To set
it up on another account: `cd deploy/cloudflare`, `npx wrangler@4 login`, `npx wrangler@4 kv namespace create ORIGIN`,
put the id in `wrangler.toml`, `npx wrangler@4 deploy`, and pass `FIXED_URL` and `KV_NAMESPACE` to the script.

**Sleep.** While the demo runs, a helper process asks Windows not to sleep (the `SetThreadExecutionState` call; no
setting is changed and it ends with `stop`). Closing the lid can still sleep the laptop, so keep it open and plugged
in, or set "When I close the lid" to "Do nothing" for "Plugged in".

The same by hand:

```bash
npm run build:selfhost        # Vite build whose API calls go to its own origin
cd backend
export UV_PROJECT_ENVIRONMENT=C:/Users/<you>/.venvs/axiom   # only on the machine where the F: drive venv is broken
DATABASE_URL= SERVE_FRONTEND=true TRADER_ENABLED=true AXIOM_API_TOKEN=<long random string>   uv run python -m axiom.api
cloudflared tunnel --url http://localhost:8000   # in a second terminal
```

`cloudflared` prints a `https://<random>.trycloudflare.com` URL. Quick tunnels need no Cloudflare account. Install
`cloudflared` from Cloudflare's downloads page (on Windows, the `.msi` or `.exe` from the cloudflared GitHub releases).

What a visitor gets, and does not:

- **Read-only.** Every `POST /api/trader/*` needs `Authorization: Bearer $AXIOM_API_TOKEN`. Without a token set, only
  direct requests from the same machine may write, and a request carrying tunnel or proxy headers (`cf-connecting-ip`,
  `x-forwarded-for`, `forwarded`, `x-real-ip`, `cf-ray`) never counts as local. Set the token anyway.
- To drive it yourself through the URL, open the key icon in the header and paste the token. It stays in that browser.
- **Guest actions** (`TRADER_GUEST_ACTIONS=true`): a visitor without the token may also play the three named
  scenarios and press Review now. A scenario runs on the simulator and a review orders nothing (six per hour at
  most), so neither touches the broker. Kill, resume, approvals, autonomy, the red team and custom replays still need
  the token. Give the token only to people who should be able to approve trades or press the kill switch.
- **No server-sent events.** Cloudflare documents that quick tunnels do not support SSE. The cockpit notices the
  stream is down and polls the live panels every 5 seconds instead, and stops polling while its tab is hidden. For
  the smoothest demo, present from `http://localhost:8000` and share the fixed link for judges to follow along.
- Quick tunnels have no uptime guarantee, a 200 in-flight request limit, and a new hostname each time (the fixed
  link hides that). A named Cloudflare Tunnel on a domain you own in Cloudflare would remove the redirect and bring
  back SSE.

Before the demo:

1. Put Alpaca **paper** keys in `backend/.env` (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`) and run
   `uv run python scripts/alpaca_smoke.py --trade` once: it checks the account is paper, crypto is active, and does a
   ~$10 BTC/USD round trip with a stop.
2. Set `TRADER_BROKER=alpaca`, `TRADER_SYMBOLS=BTC/USD,ETH/USD` (crypto trades 24/7), `TRADER_BRAIN=llm` with an LLM
   key set (for example `NEBIUS_API_KEY` and `LLM_CHAIN=nebius,groq,openrouter,ollama`), and start the loop **several days early** so the journal, contracts and autonomy ladder show a
   real track record.
3. Regenerate the report: `uv run python -m axiom.trading backtest`, then `npm run build:selfhost` so the landing
   page shows the new numbers.

Frontend and backend deploy separately in the serverless shape below. Everything there fits free plans with no card,
except where noted.

```
Browser ──> Vercel (static, Vite build) ──fetch/SSE──> Vercel Function (FastAPI, Python 3.12)
                                                        ├── Neon Postgres: runs, theses, approvals, shared cache
                                                        ├── Cerebras / Groq / OpenRouter (free LLM chain)
                                                        └── yfinance, Google News RSS, SEC EDGAR
Vercel Cron ──daily──> /api/cron/daily  (score matured theses, run the briefing)
```

## What was verified, and what was not

Verified here, locally:

- The same code runs on SQLite and on a real Postgres 16 (store, cache, usage counters: `tests/test_db_portability.py`).
- The Vercel entrypoint (`backend/api/index.py`) serves a full analysis end to end against Postgres, with the daily cap, per-client cap, deadline and cron endpoint active.
- The dependency set installs to about 310 MB, under Vercel's 500 MB function limit. Cold import takes about 6 s on this machine.
- 3.12 test run, lint, formatting, and the frontend build.

Not verified, because it needs your accounts: SSE streaming through Vercel's edge (buffering), real cold-start time, a 3-minute run finishing under the 300 s limit, yfinance from Vercel's IPs, and the free LLM providers under load. Section 5 is a 10-minute checklist for these. If it fails, the Cloud Run route in section 7 is mostly a Dockerfile away.

## Before you start: two rules that shape the setup

- **Vercel Hobby is non-commercial only.** If Axiom becomes a paid product, move to Cloud Run (section 7) or a paid Vercel plan.
- **Market data licensing.** yfinance is unofficial and often blocked from cloud IPs. Twelve Data's free plan forbids public display. No free source clearly allows showing prices publicly, so treat the public deployment as a demo, keep the daily cap on, and expect some tickers to fail with a data error.

## 1. Database (Neon)

1. Create a free project at neon.tech. Pick the region closest to your Vercel region (default `iad1`, US East).
2. Copy the **pooled** connection string (host contains `-pooler`). It looks like `postgresql://user:pass@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require`.

Tables are created automatically on first request. Nothing else to run.

## 2. Backend (Vercel)

In the Vercel dashboard: **Add New Project**, import this repository, set **Root Directory** to `backend`. Framework preset: Other. Or from a terminal:

```bash
cd backend
vercel link          # create/choose the project
vercel --prod
```

Environment variables (Project Settings, Environment Variables):

| Name | Value | Why |
|---|---|---|
| `DATABASE_URL` | Neon pooled string | Persistent runs, theses, shared cache |
| `LLM_CHAIN` | `cerebras,groq,openrouter` | Recommended for a public deploy (the code default is `groq,gemini,openrouter,ollama`; the live demo runs `openrouter,groq`). No `gemini` unless you read the note below. Ollama is skipped automatically on serverless |
| `CEREBRAS_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` | your free keys | Set at least one |
| `GROQ_MODEL`, `CEREBRAS_MODEL`, `OPENROUTER_MODEL` | check each provider's current model list | Free model ids change often. Defaults may be stale |
| `AXIOM_API_TOKEN` | a long random string | Without it, nobody can edit the watchlist, paper trades or approvals from a browser |
| `CORS_ORIGINS` | every frontend URL, comma-separated, no trailing slash | Browser calls are blocked otherwise |
| `ANALYZE_PER_DAY` | `40` | Global cap. About what the free LLM quotas sustain |
| `ANALYZE_PER_HOUR` | `6` | Per visitor (the code default is 12; lower is kinder to free quotas) |
| `RUN_DEADLINE_SECONDS` | `270` | Ends a run cleanly before the 300 s function limit |
| `CRON_SECRET` | a long random string | Enables `/api/cron/daily`; Vercel Cron sends it automatically |
| `SEC_USER_AGENT` | `Axiom Research you@yourdomain.com` | SEC requires a real contact |

Notes:

- **Gemini.** Google's free-tier terms bar serving users in the EEA, UK and Switzerland. Leave it out of a public deployment unless you geo-block, or use it only for your own private instance.
- **Actions** stay in dry-run unless you add `COMPOSIO_API_KEY`. With real actions on, `AXIOM_API_TOKEN` is mandatory (the API refuses otherwise).
- `TRUST_PROXY` defaults to on under Vercel, so per-client limits use the real caller IP from `X-Forwarded-For`.

## 3. Frontend (Vercel)

A second Vercel project from the same repository, **Root Directory** the repo root (Vite is detected). Set one variable:

| Name | Value |
|---|---|
| `VITE_API_BASE_URL` | the backend URL, for example `https://axiom-api-three.vercel.app` (the live one) |

Then go back to the backend project, add the frontend's URL to `CORS_ORIGINS` and redeploy it. Open the site, then the key icon in the app header and paste `AXIOM_API_TOKEN` to unlock watchlist, paper trades and approvals.

Cloudflare Pages works the same way (build `npm run build`, output `dist`, same variable, SPA fallback is automatic).

## 4. Daily briefing

`backend/vercel.json` registers a cron at 13:00 UTC on weekdays. Hobby allows one run per day, with up to an hour of drift. It scores theses that have matured, then analyses the watchlist and posts the digest (dry-run until Composio is configured). Trigger it by hand:

```bash
curl -H "Authorization: Bearer $CRON_SECRET" https://<backend>/api/cron/daily
```

A long watchlist cannot finish inside 300 s with a free model, so keep it to two or three tickers on Vercel.

## 5. Ten-minute spike (do this before sharing the link)

```bash
API=https://<backend>
curl -s $API/api/health                      # storage should say "postgres", llm_chain your providers
curl -s "$API/api/market/AAPL/ohlcv?bars=5"  # yfinance reachable from Vercel's IPs?
time curl -sN -X POST $API/api/analyze -H 'content-type: application/json' -d '{"ticker":"AAPL"}'
```

Check three things on the last one:

1. **Events arrive as they happen**, not all at once at the end (that means the stream is not buffered).
2. It **finishes under about 4.5 minutes**. A cache miss on a slow free model is the worst case.
3. Run the same command again: it should be much faster (shared cache in Postgres).

Then open `/app` in a browser and run one analysis through the UI. If streaming is buffered or runs exceed the limit, use section 7.

## 6. Free-tier budget

| Resource | Free limit (checked at research time, re-check) | How Axiom stays inside it |
|---|---|---|
| Vercel function | 300 s per request, 2 GB | `RUN_DEADLINE_SECONDS`, pings every 15 s keep the stream alive |
| Neon | about 0.5 GB storage | Cache rows expire (market 10 min, LLM 7 days) and are purged |
| LLM calls | a few dozen uncached analyses a day | `ANALYZE_PER_DAY`, response cache, per-run token budget (60k) |
| Market data | informal | One upstream fetch per ticker per 10 min (windows are sliced from one 1500-bar fetch) |

## 7. Fallback: Google Cloud Run (needs a billing card, free tier covers a demo)

The backend ships a Dockerfile. No code changes:

```bash
cd backend
gcloud run deploy axiom-api --source . --region us-central1 --allow-unauthenticated \
  --memory 2Gi --timeout 900 --set-env-vars LLM_CHAIN=cerebras,groq,openrouter,TRUST_PROXY=true \
  --set-secrets DATABASE_URL=...,GROQ_API_KEY=...
```

A container is long-lived, so there is no 300 s limit and APScheduler can run the briefing itself (`SCHEDULER_ENABLED=true`). Set `RUN_DEADLINE_SECONDS=0` there.

## Keeping `requirements.txt` in sync

Vercel installs from `backend/requirements.txt`, generated from `uv.lock`. CI fails if they drift. After changing dependencies:

```bash
cd backend && uv lock && uv export --no-dev --no-hashes --no-emit-project -o requirements.txt
```
