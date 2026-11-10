# Learning notes: RxJS and NgRx in Axiom Watch

Written for someone preparing for an Angular interview. Every claim points at a file in this app, so you can open
the code and check it. Paths are relative to `angular/src/app/`.

## 1. Every RxJS operator used, where, and why

### Search (`search/state/search.effects.ts`)

| Operator | What it does | Why here, and not the alternative |
|---|---|---|
| `map` | Transforms each value. | Pulls `query` out of the action and trims it. |
| `debounceTime(250)` | Emits a value only after 250 ms with no newer value. | Typing "NVDA" sends one request, not four. `throttleTime` would fire on the first keystroke and drop the last one, which is the one the user wants. `auditTime` emits at fixed intervals, even mid-word. |
| `distinctUntilChanged` | Drops a value equal to the previous one. | "nvda", then a space, then a backspace trims back to "nvda": no second request for the same query. |
| `switchMap` | Maps each value to an inner Observable, and **unsubscribes from the previous inner one**. | Unsubscribing from an `HttpClient` Observable aborts the request, so a slow answer for "NV" can never overwrite the answer for "NVDA". `mergeMap` would keep every request and let responses arrive out of order. `concatMap` would queue them, so the UI would lag behind typing. `exhaustMap` would ignore new queries while one is in flight, so the final query might never be sent. |
| `catchError` (inside the `switchMap`) | Replaces an error with a fallback Observable. | It sits on the inner HTTP Observable, so a failed request becomes a `Search Failed` action and the effect keeps listening. Put on the outer stream, one error would complete the effect and search would stop working until reload. |
| `of` | Emits the given values and completes. | Wraps the failure action, and the `Search Cleared` action for an empty query, without calling the API. |

### Live run stream (`core/event-source.ts`, `run/state/run.effects.ts`)

| Operator / API | What it does | Why |
|---|---|---|
| `new Observable(subscriber => { ...; return teardown })` | Builds an Observable by hand, returning a teardown function. | `EventSource` is callback-based. The wrapper opens it on subscribe and returns `() => source.close()`, so unsubscribing from the stream for any reason closes the HTTP connection. See section 4. |
| `defer` | Creates the Observable lazily, once per subscription. | Each retry builds a **new** `EventSource`, not a reused, closed one. |
| `tap` | Runs a side effect without changing values. | Records that `run_start` arrived, which decides whether a retry is allowed. |
| `retry({ count: 3, delay })` | Resubscribes after an error, up to 3 times, waiting for the Observable that `delay` returns. | Recovers from a dropped or refused connection while the API wakes up. `delay` returns `timer(backoffDelay(n))` (`core/backoff.ts`: 1 s, 2 s, 4 s, capped, with jitter) or `throwError` once the run has started. See the note below. `retryWhen` is deprecated in favour of this config form. |
| `timer(ms)` | Emits once after `ms`. | The backoff wait inside `retry`. |
| `throwError(() => err)` | An Observable that only errors. | Returned from `delay` to say "do not retry this one". |
| `takeWhile(pred, true)` | Completes when `pred` turns false, and with `inclusive: true` it also emits that last value. | Completes after the `result` or `error` event, which tears down the `EventSource`. Without this the browser's built-in reconnect would fire when the server ends the response, and **start a second, paid run**. |
| `takeUntil(cancelled$)` | Completes when a notifier emits. | The Cancel button, or leaving the page, dispatches `Run Monitor Cancelled` and closes the stream. |
| `merge` | Subscribes to several Observables and interleaves their values. | Merges the `Retrying` status actions (from a `Subject` fed by the `delay` callback) with the stream's own actions. |
| `finalize` | Runs when the Observable completes, errors or is unsubscribed. | Completes that `Subject`, so the merged stream can complete. |
| `switchMap` | As above. | Starting a new run while one is streaming cancels the old one, closing its `EventSource`, before opening the new one. |
| `catchError` | As above. | After the retries are used up, or for a mid-run drop, it emits `Run Stream Failed` with a clear message. |
| `takeUntilDestroyed()` | From `@angular/core/rxjs-interop`. Completes when the injection context's `DestroyRef` fires. | Used in `run/run-monitor.component.ts`, `watchlist/watchlist.component.ts` and `search/ticker-search.component.ts` for form `valueChanges` subscriptions that dispatch actions. No `ngOnDestroy` and no `Subscription` fields. |

**Why only retry before `run_start`.** The server cancels a run when the client disconnects (`finally:
task.cancel()` in `backend/axiom/api/app.py`). A reconnect cannot resume a run. It starts a new one, and that
counts against the per-visitor and daily caps. So the effect retries only until `run_start` arrives: that covers
the cold start, where the API is waking or the first connection is refused. A drop after that is reported as
"Connection lost; start the run again". Refusals such as the rate limit or a bad ticker arrive as SSE `error`
events, not as transport errors, so they are never retried.

### Price refresh (`watchlist/state/watchlist.effects.ts`, `refreshQuotes$`)

| Operator | What it does | Why |
|---|---|---|
| `fromEvent(document, 'visibilitychange')` | An Observable of DOM events. | Notices when the tab is hidden or shown. `DOCUMENT` is injected, so tests pass a fake. |
| `startWith(isVisible())` | Emits an initial value first. | `visibilitychange` only fires on change, so the effect needs the current state at startup. |
| `distinctUntilChanged` | As above. | Ignores repeated "visible" events. |
| `switchMap(visible => visible ? timer(0, 5 min) : EMPTY)` | As above. | **This is the pause.** When the tab hides, `switchMap` unsubscribes from the timer and switches to `EMPTY`, which never emits. When it shows again, a fresh `timer(0, ...)` refreshes immediately, then every five minutes. A `filter(() => !document.hidden)` on a running timer would also skip work, but the timer would keep ticking and refresh up to five minutes late on return. |
| `EMPTY` | Completes at once, emits nothing. | The paused state. |
| `concatLatestFrom(() => store.select(selectTickers))` | From `@ngrx/operators`. Pairs each tick with the latest selector value, reading it lazily. | Each tick refreshes the tickers on the list *now*. `withLatestFrom` subscribes to the selector eagerly, when the effect is created. `concatLatestFrom` waits for the first tick, which is the NgRx-recommended form inside effects. |
| `exhaustMap` | Maps to an inner Observable and **ignores** new outer values until it completes. | If a refresh is still running when the next tick arrives, the tick is skipped. Two overlapping refreshes would only double the load on free-tier market data. |
| `from(tickers)` | Emits each array item. | One value per ticker. |
| `mergeMap(fetch, 2)` | Runs up to 2 inner Observables at once. | Two summary requests in parallel: faster than `concatMap` (one at a time), but not a burst of 25 like unbounded `mergeMap`. Order does not matter, because each result updates its own ticker. |

### Optimistic writes (`watchlist/state/watchlist.effects.ts`, `addTicker$` and `removeTicker$`)

| Operator | Why |
|---|---|
| `concatMap` | Writes go to the API one at a time, in the order they were made. Add NVDA then remove NVDA must reach the server in that order. `mergeMap` could let the DELETE land first, leaving NVDA on the server but gone from the screen. `switchMap` would abort the first write when a second arrives, even though the server may already have applied it. `exhaustMap` would drop the second click entirely. |
| `map`, `catchError`, `of` | Success becomes `Add Succeeded`. An error becomes `Add Failed` (the rollback), caught inside the `concatMap` so the effect survives. |

### Shared data (`core/api-status.service.ts`)

| Operator | Why |
|---|---|
| `defer`, `timeout({ first: 20_000 })`, `retry({ count: 5, delay })` | One health check that gives the API time to wake, with backoff between tries. |
| `shareReplay({ bufferSize: 1, refCount: true })` | `ready$` is subscribed to by the watchlist load effect, the ratings effect and the status banner. Without sharing, that is three `/api/health` calls. With it, there is **one**, and late subscribers get the replayed result. `refCount: true` unsubscribes from the source when the last subscriber leaves, so a check that is still in flight is not kept running for nobody. Once the source has completed, the replayed value stays cached either way. |
| `merge`, `timer(2500)`, `map`, `takeUntil`, `startWith('checking')`, `catchError` | `status$` is `checking`. If `ready$` has not answered within 2.5 s it becomes `waking` (the banner says "Waking up the API"). Then it ends as `ready`, or `unreachable` if every retry failed. |

### Filter and sort (`watchlist/watchlist.component.ts`, `watchlist/view.ts`)

| Operator | Why |
|---|---|
| `combineLatest([rows$, filter$, sort$])` | Recomputes the visible rows whenever any input changes: new prices from the store, a keystroke in the filter, or a new sort. Nothing is synced by hand. `withLatestFrom` would recompute only when the first stream emits. `zip` would pair the nth values of each stream, which is wrong for state. |
| `startWith` | Form `valueChanges` do not emit their initial value, and `combineLatest` waits for every input to emit once. |
| `map(visibleRows)` | `visibleRows` is `applyView` wrapped by NgRx's `defaultMemoize`, so identical inputs reuse the previous array. |

Signals appear only at the edge: `toSignal(view$)` and `toSignal(store.select(...))` let templates read values
without the `async` pipe. All async work stays in RxJS.

## 2. One action, end to end: adding a ticker

1. **Template** (`search/ticker-search.component.html`): the user picks "NVDA" from the results.
2. **Component** (`search/ticker-search.component.ts`): `pick()` dispatches
   `WatchlistPageActions.addRequested({ ticker: 'NVDA', requestedAt: Date.now() / 1000 })`. The timestamp is
   passed in, which keeps the reducer pure.
3. **Reducer** (`watchlist/state/watchlist.reducer.ts`): runs synchronously first. `adapter.addOne` inserts
   `{ ticker: 'NVDA', added_at, pending: true }`, unless NVDA is already listed.
4. **Selectors** (`watchlist/state/watchlist.selectors.ts`): `selectRows` recomputes, because the entities changed.
   The table shows the row at once, dimmed, labelled "Adding".
5. **Effect** (`addTicker$` in `watchlist/state/watchlist.effects.ts`): sees the same action after the reducer, and
   `concatMap`s to `api.watchAdd('NVDA')`.
6. **API** (`core/api.service.ts`, then the backend): `PUT /api/visitor/watchlist/NVDA` with the
   `X-Axiom-Visitor` header. The backend normalizes the ticker, checks the per-IP write limit and the 25-ticker
   cap, then upserts portably on SQLite or Postgres.
7. **Success:** `WatchlistApiActions.addSucceeded({ ticker, item })`. The reducer clears `pending` and takes the
   server's `added_at`. `quoteNewTicker$` fetches NVDA's summary straight away, instead of waiting for the next
   five-minute tick.
8. **Failure** (409 full, 429 rate limited, network): `addFailed({ ticker, error })`. The reducer removes the row,
   but only if it is still `pending`, and sets `notice` to "Could not add NVDA: ...".
9. **Template** (`watchlist/watchlist.component.html`): the `role="status"` region announces the notice, and the
   row disappears or settles.

## 3. Optimistic update and rollback

The UI changes before the server answers. Rolling back needs enough information to undo the change exactly.

- **Add.** The reducer inserts the row with `pending: true`. On failure it removes the row, *only if it is still
  pending*. That guard matters: if NVDA was already on the list, `addRequested` is a no-op. If the PUT then
  failed, a rollback without the guard would delete a row the user already had.
- **Remove.** The reducer moves the entity from the adapter into `removed[ticker]` before the request is sent. On
  failure, `removeFailed` puts `removed[ticker]` back with `adapter.addOne`, so position, `added_at` and the cached
  quote are kept. On success it deletes the stash and the cached quote.
- **Ordering.** `concatMap` in the effects means the server sees writes in the order the user made them, so the
  final server state matches the final screen state.
- **Visible message.** Every failure sets `notice`, rendered in a `role="status"` region with a Dismiss button. A
  rollback is never silent.
- **Tests.** `watchlist/state/watchlist.reducer.spec.ts` covers add then fail, remove then fail, and "already
  listed, add fails, row stays". `watchlist/state/watchlist.effects.spec.ts` checks that a failed PUT maps to
  `addFailed` and that the effect keeps working afterwards.

## 4. How the EventSource teardown prevents leaks

`core/event-source.ts`:

```ts
export function fromEventSource(url: string, factory: EventSourceFactory, events: string[]): Observable<SseMessage> {
  return new Observable<SseMessage>(subscriber => {
    const source = factory(url);
    const listeners = events.map(name => {
      const fn = (e: MessageEvent) => subscriber.next({ event: name, data: e.data });
      source.addEventListener(name, fn);
      return [name, fn] as const;
    });
    source.onerror = () => subscriber.error(new StreamTransportError(source.readyState));
    return () => {
      for (const [name, fn] of listeners) source.removeEventListener(name, fn);
      source.onerror = null;
      source.close();
    };
  });
}
```

- **The teardown runs on every way out:** an explicit unsubscribe, `takeWhile` completing after the `result`
  event, `takeUntil` on cancel, `switchMap` moving to a new run, an error (before `retry` resubscribes), and the
  effect being torn down. Each one closes the HTTP connection, so no socket is left open and the server's
  `asyncio.CancelledError` path stops the run.
- **Errors stop the browser's own reconnect.** A native `EventSource` reconnects by itself after an error. Here
  `onerror` turns the error into an Observable error, and the teardown calls `close()`, so the only reconnect is
  the deliberate one in `retry`, with backoff and the `run_start` rule.
- **Testable.** `EVENT_SOURCE_FACTORY` is an injection token. Tests provide a `FakeEventSource` that records
  `close()` calls.
- **Proved, with a positive control.** `core/event-source.spec.ts` subscribes, unsubscribes and asserts that the
  fake's `closed` is `true`. The positive control builds the same Observable *without* the teardown, unsubscribes,
  and asserts that `closed` is still `false`, with the listener still attached. So the main test would fail if the
  teardown were removed: it is not passing by accident.

## 5. Ten interview questions, answered from this code

1. **What is the difference between `switchMap`, `mergeMap`, `concatMap` and `exhaustMap`?**
   They differ in what happens to inner Observables already running when a new outer value arrives. `switchMap`
   cancels the old one, which is right for search (`search/state/search.effects.ts`) and for starting a new run.
   `mergeMap` runs them all, used with a concurrency of 2 for price fetches. `concatMap` queues them in order, used
   for watchlist writes, where order on the server matters. `exhaustMap` ignores new values while one is running,
   used to skip a price tick while a refresh is still in flight.

2. **How do you avoid memory leaks with subscriptions in Angular?**
   Prefer no manual subscriptions: templates read `toSignal(...)` values, and effects are managed by NgRx. Where a
   component must subscribe (form `valueChanges` that dispatch actions), `takeUntilDestroyed()` ends it when the
   component is destroyed. For resources outside Angular, like `EventSource`, the Observable's teardown closes the
   connection, and `core/event-source.spec.ts` proves it.

3. **Why does NgRx separate reducers from effects?**
   Reducers are pure and synchronous: `(state, action) => state`, so they are trivial to test, and devtools can
   replay them. Effects hold side effects such as HTTP and SSE, and they map actions to new actions. In this app
   components never touch `HttpClient`: `core/api.service.ts` is used only from effects.

4. **What does `@ngrx/entity` give you?**
   A normalized `{ ids, entities }` shape and an adapter with `addOne`, `removeOne`, `updateOne` and `setAll`, plus
   generated selectors. `watchlist/state/watchlist.reducer.ts` keys the watchlist by ticker, which makes the
   optimistic add, remove and rollback one adapter call each, without searching arrays.

5. **How are selectors memoized, and why does it matter?**
   `createSelector` caches the last inputs and result, and recomputes only when an input selector returns a new
   reference. `selectRows` joins entities, quotes and ratings, and it reruns only when one of those slices changes,
   so the table does not re-render on unrelated actions such as search results arriving.
   `watchlist/state/watchlist.selectors.spec.ts` checks the memoization.

6. **How do you test time-based RxJS code?**
   With `TestScheduler.run`, which runs every scheduler, including `debounceTime`, `timer` and `retry` delays, in
   virtual time and describes streams as marble strings. `search/state/search.effects.spec.ts` asserts that three
   fast keystrokes give one request 250 frames after the last one, and that a slow response is dropped when a
   newer query arrives. `run/state/run.effects.spec.ts` asserts the backoff timing of the retries.

7. **What is the difference between a cold and a hot Observable, and what does `shareReplay` do?**
   `HttpClient` Observables are cold: each subscriber triggers its own request. `shareReplay({ bufferSize: 1,
   refCount: true })` in `core/api-status.service.ts` makes the health check hot and cached: one request, shared by
   every subscriber, with the result replayed to late ones. `api-status.service.spec.ts` asserts that one request
   was made for three subscribers.

8. **How do you implement an optimistic update with rollback in NgRx?**
   Change state in the reducer on the request action, and keep what you need to undo it: the `pending` flag for
   adds, the stashed entity for removes. The effect calls the API and dispatches success or failure. The failure
   reducer restores state and sets a visible notice. See section 3.

9. **Standalone components, signals and RxJS: how do they fit together here?**
   Everything is standalone (`bootstrapApplication` with `app.config.ts` providers, no NgModules). RxJS does all
   async work: HTTP, SSE, timers, debouncing. Signals are only the last step into the template (`toSignal`), which
   removes `async` pipes and works with zoneless change detection. Signals are not used for async flows, because
   they have no cancellation or backpressure.

10. **How would you handle a slow or sleeping backend?**
    Separate "slow" from "down". `ApiStatusService.status$` shows `waking` after 2.5 s, retries with exponential
    backoff for about a minute, and only then says `unreachable`. The run stream retries a refused connection the
    same way, but only before the run starts (see section 1). Refusals that are the server's decision, such as a
    rate limit, are delivered as data (SSE `error` events with a `kind`) and shown as messages, never retried.
