# Axiom Watch: plan

> **Historical.** The plan agreed before Axiom Watch was built. The code and [README](README.md) are the source of truth now. Kept for context; the current map is the [docs index](../docs/README.md).

A second Axiom front end in Angular, RxJS and NgRx: a per-visitor watchlist, search-as-you-type for tickers, and a
live monitor for research runs. It sits beside the React app and talks to the same FastAPI backend.

## Endpoints

### Used as they were

| Endpoint | Used for | Called from |
|---|---|---|
| `GET /api/health` | wake check, shared by every first load | `core/api-status.service.ts` |
| `GET /api/quant/{ticker}/summary` | last close, 1d and 1m returns per row | `watchlist/state/watchlist.effects.ts` |
| `GET /api/theses?limit=200` | latest rating per ticker (one call, reduced on the client) | `watchlist/state/watchlist.effects.ts` |

### Added (smallest change, existing style, tests in `backend/tests/test_api.py`)

| Endpoint | Why it had to exist |
|---|---|
| `GET /api/tickers/search?q=&limit=` | There was no search. It ranks the SEC ticker map that `axiom/data/sec.py` already downloads and caches (exact ticker, ticker prefix, name word prefix, name substring). |
| `GET /api/visitor/watchlist` | The existing watchlist is one global list, it needs `AXIOM_API_TOKEN` to change, and it feeds the daily cron. A public demo needs a list per visitor. |
| `PUT /api/visitor/watchlist/{ticker}` | Same. Capped at `VISITOR_WATCHLIST_MAX` (25), returns 409 when full. Writes count against `WATCH_WRITES_PER_HOUR` (60) per IP, returning 429 with `Retry-After`. |
| `DELETE /api/visitor/watchlist/{ticker}` | Same. |
| `GET /api/analyze/stream?ticker=&equity=` | `EventSource` can only issue GET requests, and `POST /api/analyze` is POST. The new route runs the same generator as the POST (the shared `run_events`) under the same quota. Refusals (rate limit, bad ticker) arrive as SSE `error` events with a `kind`, because `EventSource` cannot read a 429 body. |

The visitor endpoints identify a visitor by the `X-Axiom-Visitor` header (16 to 64 letters, digits or dashes), a
random UUID the app keeps in `localStorage`. It is an identifier, not authentication: anyone who has the id can
edit that list. Visitor lists are stored in their own `visitor_watchlist` table through the existing `axiom/db.py`
seam (SQLite and Postgres). They are not read by the daily cron and not copied by the BigQuery ELT. The watch write
limiter writes `watch:<ip>` keys into `usage`, so `backend/data_platform/sql/dq/accepted_values.sql` now accepts
the `watch` scope.

## Architecture

```
angular/src/app/
  core/        config.ts (runtime config.json), api.service.ts (the only HttpClient user), visitor.ts,
               api-status.service.ts (wake check, shareReplay), event-source.ts (EventSource as an Observable),
               backoff.ts, page-visibility.ts (PAGE_VISIBLE token), format.ts, models.ts
  watchlist/   state/ (actions, reducer with @ngrx/entity, selectors, effects, quote-refresh.ts tokens),
               view.ts (filter and sort), ratings.ts, watchlist.component.ts
  search/      state/ (actions, reducer with a derived selectPending, effects), ticker-search.component.ts
  run/         state/ (actions, reducer, selectors, effects, run-stream.ts: one run as a stream of actions),
               steps.ts (pipeline steps from the trace), run-monitor.component.ts
  devtools.ts / devtools.dev.ts (store devtools, swapped in by the development build only)
  watch-page.component.ts, app.ts, app.routes.ts, app.config.ts
```

Components dispatch actions and read selectors. Every HTTP call and the SSE stream live in effects.

## State

```ts
watchlist: EntityState<WatchItem> & {
  quotes: Record<string, QuoteState>;     // per ticker: summary, error, fetched at
  ratings: Record<string, RatingInfo>;    // per ticker: latest rating, conviction, issue date
  removed: Record<string, WatchItem>;     // optimistic removals waiting for the API (rollback source)
  loading: boolean; loaded: boolean; error: string | null; notice: Notice | null;
}
search: { query: string; answered: string | null; results: TickerMatch[]; error: string | null }
        // pending is derived (query not yet answered), not stored
run: { ticker: string | null;
       status: 'idle' | 'connecting' | 'retrying' | 'queued' | 'running' | 'done' | 'error' | 'cancelled';
       events: TraceEvent[]; result: RunResult | null; error: string | null; errorKind: string | null;
       queueMessage: string | null; attempt: number; retryInMs: number | null }
```

## Actions (`createActionGroup`)

| Source | Events |
|---|---|
| `Watchlist Page` | Opened, Add Requested, Remove Requested, Notice Dismissed |
| `Watchlist API` | Load Succeeded, Load Failed, Add Succeeded, Add Failed, Remove Succeeded, Remove Failed |
| `Quotes API` | Refresh Succeeded, Refresh Failed |
| `Ratings API` | Refresh Succeeded, Refresh Failed |
| `Ticker Search` | Query Changed |
| `Search API` | Search Succeeded, Search Failed, Search Cleared |
| `Run Monitor` | Started, Cancelled |
| `Run Stream` | Retrying, Queued, Trace Received, Succeeded, Failed |

## Build order

1. Backend endpoints and tests, then the data-platform accepted value.
2. Scaffold with the Angular CLI (standalone, strict, SCSS), add angular-eslint and NgRx.
3. Core services, then state slices with their tests, then components.
4. Dockerfile, nginx config, CI job.
5. Deploy the API (CORS) and the app as its own Vercel project, then verify live.
