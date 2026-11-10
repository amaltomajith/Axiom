import { inject } from '@angular/core';
import { Actions, createEffect, ofType } from '@ngrx/effects';
import { catchError, debounceTime, distinctUntilChanged, map, of, switchMap } from 'rxjs';
import { ApiService, apiErrorMessage } from '../../core/api.service';
import { SearchApiActions, TickerSearchActions } from './search.actions';

const SEARCH_DEBOUNCE_MS = 250;

/**
 * Search as you type. debounceTime waits for a pause, distinctUntilChanged skips a repeat, and switchMap
 * unsubscribes from the previous request (HttpClient aborts it), so a slow answer for "NV" can never overwrite
 * the answer for "NVDA". catchError sits inside the switchMap, so one failed request does not kill the effect.
 */
export const search$ = createEffect(
  (actions$ = inject(Actions), api = inject(ApiService)) =>
    actions$.pipe(
      ofType(TickerSearchActions.queryChanged),
      map(({ query }) => query.trim()),
      debounceTime(SEARCH_DEBOUNCE_MS),
      distinctUntilChanged(),
      switchMap(query =>
        query === ''
          ? of(SearchApiActions.searchCleared())
          : api.searchTickers(query).pipe(
              map(results => SearchApiActions.searchSucceeded({ query, results })),
              catchError(e => of(SearchApiActions.searchFailed({ query, error: apiErrorMessage(e) }))),
            ),
      ),
    ),
  { functional: true },
);
