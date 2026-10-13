# Vercel Hobby plus Neon carries Axiom free

Axiom's best all-free stack as of October 2026 is a static frontend on Cloudflare, the FastAPI backend on Vercel Hobby, Neon free Postgres for state, and GitHub Actions plus cron-job.org for scheduling. Vercel Hobby is the only no-card platform that fits the whole workload: a **300 s function cap**, **2 GB RAM / 1 vCPU**, real CPython with native wheels, and native FastAPI support, against a 2 to 3 minute SSE run ([Vercel limits](https://vercel.com/docs/functions/limitations), [Vercel Python](https://vercel.com/docs/functions/runtimes/python)). Google Cloud Run is the stronger technical host (60-minute timeout, configurable memory, scale to zero), but it needs a billing card ([Cloud Run timeout](https://docs.cloud.google.com/run/docs/configuring/request-timeout)), so it ranks as the fallback. Render Free is the no-card fallback of last resort: its 512 MB and 0.1 CPU are marginal for pandas and scikit-learn ([Render Free](https://render.com/docs/free)). The real constraints are not compute. Vercel Hobby is non-commercial only. No free market-data plan clearly licenses public display. Gemini's free tier forbids serving EEA, UK and Swiss users. Free LLM quotas support only roughly 40 to 60 uncached analyses a day, so caching is the core design. Nothing here was tested against the actual app. SSE buffering on Vercel, Cloud Run's current free-tier numbers, and Northflank's limits remain unverified.

## Recommended stack and ranked alternatives

The recommended stack has four layers.

- **Frontend:** Cloudflare Workers static assets (or Pages).
- **Backend:** Vercel Hobby.
- **Database:** Neon free Postgres.
- **Scheduling:** GitHub Actions cron with cron-job.org as an independent second trigger.

SSE goes from browser to backend directly, so the frontend host never proxies the stream and its function limits are irrelevant (inference). CORS must allow the frontend origin and the Authorization header. A regex or wildcard policy is needed if preview deployments are used.

For the backend, the ranking from the notes is:

1. Vercel Hobby.
2. Cloud Run (card required).
3. Render Free (no card, tight RAM).
4. Northflank Sandbox, if its undisclosed limits check out in the console.
5. Oracle Always Free Ampere A1, as a high-effort VM option.
6. AWS Lambda with a container image, which needs rewrite work and sits on a trial-style account.

A decision rule follows. If the owner has no card and Axiom stays strictly personal and non-commercial, use Vercel. If the owner can add a card, or Axiom may ever carry ads, payments or paid work, use Cloud Run. Vercel's rules define commercial use as any deployment used for financial gain, including ads, payments and being paid to build it, while donations are explicitly not commercial ([Vercel fair use](https://vercel.com/docs/limits/fair-use-guidelines)).

Vercel needs only modest changes. The app must expose `app` at a recognized entrypoint, pin Python 3.12 to 3.14, keep the bundle lean (500 MB unzipped is allowed for Python), and point the yfinance cache directory at `/tmp`. The stream should emit SSE keepalive comments well under every 120 s, because the CDN origin timeout is 120 s to first byte and long responses survive only while data keeps flowing ([Vercel changelog](https://vercel.com/changelog/cdn-origin-timeout-increased-to-two-minutes)). The pipeline should also enforce a self-imposed deadline below 300 s and spawn no work after the response closes, since instances are paused between requests. Hobby gives 1M invocations, 4 hours of Active CPU and 360 GB-hours of provisioned memory a month ([Vercel usage](https://vercel.com/docs/functions/usage-and-pricing)). One analysis at 2 GB for 180 s is about 0.1 GB-hour, so the memory allowance covers roughly 3,600 full analyses a month (inference). Active CPU does not bill during I/O waits such as LLM calls.

Cloud Run's request-based free grant is 2M requests, 180,000 vCPU-seconds and 360,000 GiB-seconds a month, which is about 100 GiB-hours. That figure comes from secondary sources and truncated official pages ([AgentDeals](https://agentdeals.dev/hosting-free-tier-comparison-2026), [SnapDeploy](https://snapdeploy.dev/blog/free-cloud-deployment-platforms-2026-comparison)). Run it with min instances 0 and a raised timeout, and it needs only a Dockerfile.

## Backend host comparison

| Host | RAM / CPU | Sleep behavior | Card | SSE fit | Verdict |
|---|---|---|---|---|---|
| Vercel Hobby | 2 GB / 1 vCPU | Instances pause between requests; cold start imports pandas/sklearn (unmeasured) | No | 300 s cap, streaming supported; buffering untested | **Primary.** Non-commercial only |
| Google Cloud Run | Configurable (1-2 GiB) | Scale to zero; cold start unmeasured | Yes | Timeout up to 3600 s; SSE not stated in docs | **Best technical fit; fallback** |
| Render Free | 512 MB / 0.1 CPU | Spins down after 15 min; about 1 min wake; 750 h/month pool | Not stated as required | Unverified | No-card fallback; likely OOM or slow |
| Northflank Sandbox | "Limited" (one secondary source says 1 GB) | Documented as always-on | Conflicting | Unverified | Possible; verify in console |
| Oracle Always Free A1 | 2 OCPU / 12 GB (cut June 2026) | Idle reclamation risk | Yes | Full control | Roomy but highest ops burden |
| Leapcell Hobby | Up to 4 GB | Serverless-style cold starts | Not stated | 900 s timeout; undocumented | Marginal: 3 GB-hours and 2 GB transfer a month |
| AWS Lambda (container) | Up to 10 GB | Cold starts | Yes | 15 min; streaming needs an adapter | Rewrite; account is a 6-month trial |
| Azure Container Apps | Consumption grant | Scale to zero | Yes | HTTP idle timeout unverified | Marginal |
| Hugging Face Docker Space | 16 GB / 2 vCPU | Sleeps on free hardware | Paid plan needed | Port 7860 unconfirmed | Trap: creation requires a paid plan |
| Koyeb, Fly.io, Railway, Zeabur, Back4app, Sevalla, Heroku, DigitalOcean | Varies | n/a | n/a | n/a | No fit for new accounts |

Several rows need context. Render's April 2026 plan change cut Hobby bandwidth to 5 GB a month, and free services are suspended when it runs out without a payment method ([AgentDeals Render](https://agentdeals.dev/vendor/render), secondary). A single Render free service can stay up all month, since 744 hours is below the 750-hour pool, but pinging it is neither sanctioned nor forbidden in the docs ([Render Free](https://render.com/docs/free)). Oracle halved the Ampere allowance to 2 OCPU and 12 GB effective June 15, 2026, with unclear enforcement ([InfoQ](https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/)). It also needs Caddy, TLS and patching. Hugging Face's docs now say creating a Docker Space needs a paid plan ([HF Spaces](https://huggingface.co/docs/hub/spaces-overview)). The remaining serverless platforms cannot run the Python stack. Cloudflare Workers Free allows 10 ms of CPU per request, and its Containers have no free tier ([CF Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [CF Containers](https://developers.cloudflare.com/containers/pricing/)). Netlify, Supabase Edge and Deno Deploy are TypeScript runtimes with 60 s, 150 s and no Python support respectively. Azure Functions caps HTTP at 230 s and gives no free grant to free accounts ([Azure scale](https://learn.microsoft.com/en-us/azure/azure-functions/functions-scale)). AWS App Runner closed to new customers on April 30, 2026 ([AWS docs](https://docs.aws.amazon.com/ja_jp/apprunner/latest/dg/apprunner-availability-change.html)). PythonAnywhere free limits outbound traffic to an allowlist, so yfinance is likely blocked there (secondary).

## Persistence: Neon first, Turso or Litestream if SQLite must stay

Because every serious free host has an ephemeral filesystem, state must live off-box. **Neon Free** is the best fit. It is real Postgres, scales to zero after 5 minutes idle, wakes in a few hundred milliseconds, and the official plans page lists 1 GB per project with no inactivity deletion found ([Neon plans](https://neon.com/docs/introduction/plans), [Neon latency](https://neon.com/docs/connect/connection-latency)). Use the `-pooler` hostname for the app and the direct string for migrations. Set `connect_timeout=10`, `pool_pre_ping`, and retries with backoff ([Neon pooling](https://neon.com/docs/connect/connection-pooling)). Migrating from SQLite means porting DDL (identity columns, JSONB, `%s` placeholders) while keeping the unique idempotency-key constraint.

Alternatives, in order, are as follows.

- **Turso:** 5 GB, no card, minimal SQLite-dialect change, and no stated inactivity policy ([Turso pricing](https://turso.tech/pricing)).
- **SQLite with Litestream to Cloudflare R2:** needs zero schema change but a restore-then-replicate boot wrapper, and it must be single-instance ([Litestream](https://litestream.io/reference/restore/)). It cannot run on Vercel, where there is no long-lived process to wrap.
- **Supabase Free:** pauses projects after a week idle, so the daily job must double as keep-alive ([Supabase pricing](https://supabase.com/pricing)).
- **Aiven free Postgres, MongoDB Atlas M0, Firestore:** viable, but Aiven powers off on inactivity with no stated retention, and the other two require rewriting the Store class.

Avoid Render free Postgres, which expires after 30 days ([Render Free](https://render.com/docs/free)). Also avoid CockroachDB, Xata and Railway, which offer trials or credits only, and PlanetScale, which has no free tier.

## Scheduling, cold starts and the frontend

On Vercel, cold starts cost a few seconds of imports rather than a minute-long wake, and the notes found no measurements. The remaining job is a reliable daily trigger. GitHub Actions cron may be delayed at the top of the hour, can drop runs under load, enforces a 5-minute minimum interval, and is auto-disabled after 60 days without repo activity in public repos ([GitHub events docs](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)). Use an odd minute, add `curl --retry` against a health endpoint, and treat the schedule as a window. Pair it with cron-job.org, which allows custom headers but only a 30 s timeout and deactivates a job after 25 consecutive failures ([cron-job.org FAQ](https://cron-job.org/en/faq/)). A warm-up GET followed by the real call is therefore safer. A Cloudflare Worker cron can wait up to 15 minutes and retry ([Workers limits](https://developers.cloudflare.com/workers/platform/limits/)). Healthchecks.io alerts when a daily run goes missing ([Healthchecks](https://healthchecks.io/pricing/)). If Render is used instead, ping only around the daily job rather than 24/7. Add a landing-page warm-up `fetch` and a "waking up" state in the app route (an unsourced UX recommendation).

For the frontend, Cloudflare static asset requests are documented as free and unlimited, and Pages Free allows 500 builds a month ([CF static assets](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/), [CF Pages limits](https://developers.cloudflare.com/pages/platform/limits/)). Vercel Hobby also works for a personal portfolio with 100 GB of transfer ([Vercel Hobby](https://vercel.com/docs/plans/hobby)). GitHub Pages works but needs a 404.html SPA workaround and has a 100 GB soft cap ([GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)). Avoid Netlify (credit-capped, with all sites paused on exhaustion, per unofficial sources), Firebase Spark (360 MB a day), and Amplify (12-month or 6-month trial).

## External data and LLM limits shape the product

**Market data.** yfinance from cloud IPs is unreliable. Yahoo blocks per IP, there is no official statement, and outcomes depend on IP reputation, with Streamlit Cloud users blocked and Colab users unaffected ([yfinance discussion #2431](https://github.com/ranaroussi/yfinance/discussions/2431), [Streamlit forum](https://discuss.streamlit.io/t/yfratelimiterror-too-many-requests-rate-limited-try-after-a-while/111207)). Free fallbacks are weak. Twelve Data Free gives 8 credits a minute and 800 a day but **internal non-display use only** ([Twelve Data pricing](https://twelvedata.com/pricing)). Finnhub's free plan never included `/stock/candle` ([Finnhub issue #546](https://github.com/finnhubio/Finnhub-API/issues/546)). Tiingo, Massive, FMP, EODHD and Alpha Vantage are limited, personal-use, or too small for roughly 1,300 bars, and Stooq now sits behind a CAPTCHA key and browser challenge (all secondary sources). The recommended chain is cache (24 h, since daily bars change once a day), then yfinance with backoff, then Twelve Data, with a pre-baked snapshot for a fixed ticker list as the safe demo path. SEC EDGAR is free if requests carry a descriptive User-Agent with contact info and stay under 10 requests a second ([SEC](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)). For news, Finnhub company news is the cleanest key-based option, with Google News RSS as a gray-area fallback. NewsAPI's free tier is development-only ([NewsAPI](https://newsapi.org/pricing)).

**LLMs.** Cerebras free allows about 1M tokens a day on gpt-oss-120b but only 5 requests a minute ([Cerebras](https://inference-docs.cerebras.ai/support/rate-limits)). Groq's gpt-oss-120b allows 8K tokens a minute and 200K a day, per organization, so about 10 to 13 analyses a day ([Groq](https://console.groq.com/docs/rate-limits)). OpenRouter `:free` allows 50 requests a day, or 1,000 after a one-time $10 purchase ([OpenRouter](https://openrouter.ai/docs/api-reference/limits)). Combined, that is roughly 60 to 70 uncached analyses a day at 15 to 20k tokens each (inference). Use Cerebras and Groq as primary and secondary (same model, consistent tool-calling), and OpenRouter third. Gemini's terms say free-tier content is used to improve products. They also say that if you make clients available to users in the EEA, Switzerland or the UK, you may use only Paid Services ([Gemini terms](https://ai.google.dev/gemini-api/terms)), which a global public demo would breach. Remove GitHub Models, retired July 30, 2026 ([GitHub docs](https://docs.github.com/en/github-models/prototyping-with-ai-models)). Skip Hugging Face Inference Providers, which has no free credits ([HF pricing](https://huggingface.co/docs/inference-providers/pricing)), and SambaNova at 20 requests a day (secondary).

Quota protection is therefore mandatory. It means a whole-analysis cache keyed by ticker and date, single-flight deduplication, a global daily budget with a circuit breaker to cached or sample analyses, per-IP caps, `Retry-After` backoff, and optional bring-your-own-key. Limits are per organization, project or account, so extra keys add no capacity and risk bans.

## What is verified, what is not, and conflicts to carry forward

**Verified from official pages:** Vercel limits, Python runtime, usage quotas, fair-use text and Hobby plan limits. Render Free docs. Cloud Run timeout. Cloudflare Workers, Pages and Containers limits. Lambda quotas. Azure Functions hosting limits. Neon, Supabase, Aiven, Prisma, Turso and D1 plan pages. Litestream flags. Twelve Data pricing. Groq, Cerebras and OpenRouter limits. Gemini terms. GitHub Models retirement. SEC EDGAR policy. GitHub Actions scheduling rules and cron-job.org FAQ. The notes caution that fetches were run through a summarizing model, so numbers should be rechecked before commitment.

**Secondary or unverified:**

- Cloud Run's free-tier numbers (official pricing page truncated) and its eligible regions.
- Northflank's CPU, RAM and card status.
- Leapcell's SSE behavior.
- Oracle idle-reclamation rules.
- Hugging Face's sleep timeout.
- Most market-data free limits (Tiingo, Massive, FMP, EODHD, Alpha Vantage).
- Gemini's current free quotas.
- Netlify's credit model.
- Cloudflare Pages bandwidth and Cloudflare ToS commercial clause.
- Vercel's overage or pause behavior on Hobby, and whether the 4.5 MB payload cap applies to streams.
- Mistral's free tier (page 404).

**Conflicts between sources:**

- Neon storage is 1 GB per project on the official page versus 0.5 GB per trackers; either is ample.
- Koyeb's free tier for new accounts is closed per aggregators and the pricing page, but still described in its FAQ with a $29 hold.
- Northflank card requirement conflicts across sources.
- Supabase paused-project restore is 90 days in the changelog versus one year in a docs mirror.
- Oracle enforcement dates and which account types are affected differ across reports.
- Netlify credits per GB are 20 versus 10.
- Gemini free quotas and Pro availability differ across guides.
- Render wake time is 30 to 50 s from one source versus about 1 minute officially.
- Cloudflare's bundle limit is 64 MiB (official) versus older 3 or 10 MB figures.

**Not tested anywhere:** FastAPI plus pandas, scikit-learn and the in-process MCP server on any host. The notes found no sources on anyio memory streams in serverless, and treat it as working wherever the app runs as normal CPython. Tool-calling reliability of free LLMs, cold-start times for this dependency set, and GitHub Actions cron delay distributions were also not measured.

## Decisions for the project owner

1. **Commercial intent.** Confirm Axiom stays non-commercial. If not, Vercel Hobby is out and the backend moves to Cloud Run.
2. **Card.** Decide whether a billing card on Google Cloud is acceptable. If yes, Cloud Run is the safer host; if no, Vercel, with Render as a weak fallback.
3. **Public display of market data.** Decide whether to show prices publicly given that no free plan clearly licenses display and Yahoo's terms were not read. Options are minimal display with attribution and a disclaimer, a pre-baked snapshot for fixed tickers, or a paid licensed feed.
4. **Gemini.** Either exclude Gemini, geo-block EEA, UK and Swiss visitors and disclose training use, or pay for it. The recommended default is to exclude it.
5. **Usage caps.** Set the global daily analysis cap (about 40 to 50), the per-IP cap (about 3 a day), and whether to allow bring-your-own-key.
6. **Database.** Choose Neon (recommended) versus Turso or Litestream to keep SQLite, and accept the rewrite effort.
7. **Keep-alive stance.** Decide whether pinging a sleeping host is acceptable, and whether to pay the one-time $10 OpenRouter unlock.
8. **Pre-commit test.** Run a spike on Vercel: deploy the app, confirm SSE is not buffered, check cold-start time, and confirm a 3-minute run finishes under 300 s. If any of these fails, switch to Cloud Run.

## Conclusion

The central lesson is that free compute is the easy part. Only Vercel Hobby and Cloud Run fit a 3-minute SSE agent without a rewrite. The harder limits are licensing and quotas: market-data display rights, Gemini's regional clause, and a free-LLM budget of a few dozen analyses a day. These force caching, caps and snapshot fallbacks into the architecture regardless of host.

The stack is also modular. Because state sits in Neon and the frontend talks to the backend over plain HTTP, moving from Vercel to Cloud Run is mostly a Dockerfile and a CORS change. Start on Vercel for its no-card convenience, run the spike, and keep Cloud Run ready as the escape hatch.
