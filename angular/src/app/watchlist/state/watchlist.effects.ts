import { inject } from '@angular/core';
import { Actions, createEffect, ofType } from '@ngrx/effects';
import { concatLatestFrom } from '@ngrx/operators';
import { Action, Store } from '@ngrx/store';
import { catchError, concatMap, EMPTY, exhaustMap, from, map, mergeMap, Observable, of, switchMap, take, timer } from 'rxjs';
import { ApiService, apiErrorMessage } from '../../core/api.service';
import { ApiStatusService } from '../../core/api-status.service';
import { PAGE_VISIBLE } from '../../core/page-visibility';
import { RunStreamActions } from '../../run/state/run.actions';
import { latestRatings } from '../ratings';
import { QUOTE_CONCURRENCY, QUOTE_REFRESH_MS } from './quote-refresh';
import { QuotesApiActions, RatingsApiActions, WatchlistApiActions, WatchlistPageActions } from './watchlist.actions';
import { selectTickers } from './watchlist.selectors';

function fetchQuote(api: ApiService, ticker: string): Observable<Action> {
  return api.summary(ticker).pipe(
    map(quote => QuotesApiActions.refreshSucceeded({ ticker, quote, fetchedAt: Date.now() })),
    catchError(e => of(QuotesApiActions.refreshFailed({ ticker, error: apiErrorMessage(e) }))),
  );
}

export const loadWatchlist$ = createEffect(
  (actions$ = inject(Actions), api = inject(ApiService), status = inject(ApiStatusService)) =>
    actions$.pipe(
      ofType(WatchlistPageActions.opened),
      // a second Opened while the first load is in flight is ignored, not stacked
      exhaustMap(() =>
        status.ready$.pipe(
          take(1),
          switchMap(() => api.visitorWatchlist()),
          map(items => WatchlistApiActions.loadSucceeded({ items })),
          catchError(e => of(WatchlistApiActions.loadFailed({ error: apiErrorMessage(e) }))),
        ),
      ),
    ),
  { functional: true },
);

/**
 * Adds and removes share ONE concatMap, so the server sees them in the order the user made them: add NVDA then
 * remove NVDA can never arrive as DELETE then PUT. The reducer has already changed the screen (optimistic).
 */
export const writeWatchlist$ = createEffect(
  (actions$ = inject(Actions), api = inject(ApiService)) =>
    actions$.pipe(
      ofType(WatchlistPageActions.addRequested, WatchlistPageActions.removeRequested),
      concatMap(action =>
        action.type === WatchlistPageActions.addRequested.type
          ? api.watchAdd(action.ticker).pipe(
              map(items =>
                WatchlistApiActions.addSucceeded({
                  ticker: action.ticker,
                  item: items.find(i => i.ticker === action.ticker) ?? { ticker: action.ticker, added_at: action.requestedAt },
                }),
              ),
              catchError(e => of(WatchlistApiActions.addFailed({ ticker: action.ticker, error: apiErrorMessage(e) }))),
            )
          : api.watchRemove(action.ticker).pipe(
              map(() => WatchlistApiActions.removeSucceeded({ ticker: action.ticker })),
              catchError(e => of(WatchlistApiActions.removeFailed({ ticker: action.ticker, error: apiErrorMessage(e) }))),
            ),
      ),
    ),
  { functional: true },
);

/** A new ticker gets its price at once instead of waiting for the next refresh tick. */
export const quoteNewTicker$ = createEffect(
  (actions$ = inject(Actions), api = inject(ApiService)) =>
    actions$.pipe(
      ofType(WatchlistApiActions.addSucceeded),
      mergeMap(({ ticker }) => fetchQuote(api, ticker)),
    ),
  { functional: true },
);

/**
 * Refresh every price on a timer, paused while the tab is hidden. switchMap on visibility unsubscribes from the
 * timer when the tab hides and starts a fresh timer(0, ...) when it shows, so a returning user sees new prices
 * at once. exhaustMap skips a tick while the previous refresh is still running.
 */
export const refreshQuotes$ = createEffect(
  (
    actions$ = inject(Actions),
    store = inject(Store),
    api = inject(ApiService),
    visible$ = inject(PAGE_VISIBLE),
    every = inject(QUOTE_REFRESH_MS),
  ) =>
    actions$.pipe(
      ofType(WatchlistApiActions.loadSucceeded),
      switchMap(() => visible$),
      switchMap(visible => (visible ? timer(0, every) : EMPTY)),
      concatLatestFrom(() => store.select(selectTickers)),
      exhaustMap(([, tickers]) => from(tickers).pipe(mergeMap(t => fetchQuote(api, t), QUOTE_CONCURRENCY))),
    ),
  { functional: true },
);

/** Latest rating per ticker: on open, and again after a run finishes (it may have written a new thesis). */
export const refreshRatings$ = createEffect(
  (actions$ = inject(Actions), api = inject(ApiService), status = inject(ApiStatusService)) =>
    actions$.pipe(
      ofType(WatchlistPageActions.opened, RunStreamActions.succeeded),
      switchMap(() =>
        status.ready$.pipe(
          take(1),
          switchMap(() => api.theses(200)),
          map(rows => RatingsApiActions.refreshSucceeded({ ratings: latestRatings(rows) })),
          catchError(e => of(RatingsApiActions.refreshFailed({ error: apiErrorMessage(e) }))),
        ),
      ),
    ),
  { functional: true },
);
