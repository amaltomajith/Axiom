# Deploying Axiom on free tiers

Frontend and backend deploy separately. Everything below fits free plans with no card, except where noted.

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
| `LLM_CHAIN` | `cerebras,groq,openrouter` | No `gemini` unless you read the note below. Ollama is skipped automatically on serverless |
| `CEREBRAS_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` | your free keys | Set at least one |
| `GROQ_MODEL`, `CEREBRAS_MODEL`, `OPENROUTER_MODEL` | check each provider's current model list | Free model ids change often. Defaults may be stale |
| `AXIOM_API_TOKEN` | a long random string | Without it, anyone can edit the watchlist and paper trades |
| `CORS_ORIGINS` | your frontend URL, no trailing slash | Browser calls are blocked otherwise |
| `ANALYZE_PER_DAY` | `40` | Global cap. About what the free LLM quotas sustain |
| `ANALYZE_PER_HOUR` | `6` | Per visitor |
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
| `VITE_API_BASE_URL` | the backend URL, for example `https://axiom-api.vercel.app` |

Then go back to the backend project, set `CORS_ORIGINS` to the frontend's URL and redeploy it. Open the site, then the key icon in the app header and paste `AXIOM_API_TOKEN` to unlock watchlist, paper trades and approvals.

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
