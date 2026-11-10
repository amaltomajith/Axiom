# Axiom Watch

A watchlist and live run monitor for [Axiom](../README.md), written in Angular with RxJS and NgRx. It runs beside
the React app and uses the same FastAPI backend.

**Live:** https://axiom-watch.vercel.app

- **Watchlist.** Add and remove tickers. Each row shows the last close, 1-day and 1-month returns, and the last
  Axiom rating. Filter and sort the list. Changes show instantly and roll back, with a message, if the API refuses them.
- **Ticker search.** Search as you type over the SEC ticker list. Stale requests are cancelled while you type.
- **Live run monitor.** Start an Axiom research run and watch the pipeline (router, technical analyst, fundamental
  auditor, risk guard, lead synthesizer, risk critic, policy) stream in until the memo's rating arrives.

Each visitor gets their own watchlist, keyed by a random id stored in this browser. The id is not a login: anyone
with the id can edit that list. Clearing site data starts a new, empty list.

How the RxJS and NgRx code works, and why, is in [`LEARNING.md`](LEARNING.md). Endpoints and state shape are in
[`PLAN.md`](PLAN.md).

## Run it

Needs Node 24 (or Node 22.22.3 and later; the Angular 22 CLI refuses older 22.x) and the Axiom API on `http://localhost:8000` (see the root README, `cd backend && uv run python -m axiom.api`).

```bash
cd angular
npm ci
npm start            # http://localhost:4200
```

The API URL comes from `public/config.json` at runtime, so one build can point at any API. The API must list the
app's origin in `CORS_ORIGINS` (`http://localhost:4200` is in the backend's default list).

## Test

```bash
npm run lint
npm test -- --watch=false   # Vitest through the Angular CLI, single run
npm run build
```

116 tests in 12 files (all passing on 2026-11-10) cover:

- reducers for every action, including both optimistic rollbacks
- memoized selectors and the filter and sort view
- effects with `provideMockActions`, including marble tests (`TestScheduler`) for the search debounce and
  `switchMap` cancellation, the run stream's retry with backoff, and pausing price refresh while the tab is hidden
- the watchlist, search box and run monitor components
- the `EventSource` wrapper closing the connection on unsubscribe, with a positive control showing that a wrapper
  without teardown leaves it open
- house rules: no em or en dashes, no text under 12px, WCAG AA contrast for every token pair

## Container

A multi-stage build: Node builds the app, then nginx serves the static files, with SPA fallback routing.

```bash
docker build -t axiom-watch .
docker run --rm -p 8080:80 axiom-watch                       # http://localhost:8080
docker run --rm -p 8080:80 -e AXIOM_API_BASE=http://localhost:8000 axiom-watch
```

`AXIOM_API_BASE` is written into `config.json` when the container starts. Without it, the image uses the deployed
API. Any free host port works: on a machine where 8080 is taken, use `-p 8081:80`.

Checked locally on 2026-11-10: the image is 93.5 MB (`docker images`). With `-p 8081:80` and
`AXIOM_API_BASE=http://localhost:8000/`, `/`, `/run/AAPL` and an unknown deep path all returned `index.html`,
`/config.json` returned `{ "apiBase": "http://localhost:8000" }` (trailing slash stripped) and `/healthz` returned 200.
The app in the container added a ticker and loaded its price against a local API.

## CI

The `angular` job in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) installs, lints, tests and builds
the app, builds the Docker image, runs it, and checks that `/` and a deep link (`/run/AAPL`) both serve the app. It
does not push the image.

[`azure-pipelines.yml`](azure-pipelines.yml) does the same steps for Azure DevOps. **It is untested:** it has never
run on Azure DevOps.

## Deploy

The app is its own Vercel project with `angular/` as the root directory, on the free tier.

```bash
cd angular
vercel link --project axiom-watch   # once: create or pick the project
vercel --prod
```

[`vercel.json`](vercel.json) sets the build output (`dist/axiom-watch/browser`), the SPA fallback and cache headers.
After the first deploy, add the app's origin to the API project's `CORS_ORIGINS` and redeploy the API.

The API runs on Vercel functions, so the first request after a quiet spell can be slow. The app checks
`/api/health` first. If that takes more than a few seconds it shows "Waking up the API" and retries with backoff.
It shows an error only if the API stays unreachable.
