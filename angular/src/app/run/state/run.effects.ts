import { inject } from '@angular/core';
import { Actions, createEffect, ofType } from '@ngrx/effects';
import { switchMap, takeUntil } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { BACKOFF } from '../../core/backoff';
import { EVENT_SOURCE_FACTORY } from '../../core/event-source';
import { RunMonitorActions } from './run.actions';
import { streamRun } from './run-stream';

export const runStream$ = createEffect(
  (actions$ = inject(Actions), api = inject(ApiService), factory = inject(EVENT_SOURCE_FACTORY), backoff = inject(BACKOFF)) =>
    actions$.pipe(
      ofType(RunMonitorActions.started),
      // a new run replaces the current one: switchMap closes the old EventSource first
      switchMap(({ ticker }) =>
        streamRun(api.runStreamUrl(ticker), factory, backoff).pipe(takeUntil(actions$.pipe(ofType(RunMonitorActions.cancelled)))),
      ),
    ),
  { functional: true },
);
