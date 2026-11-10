import { Action } from '@ngrx/store';
import { catchError, defer, finalize, map, merge, Observable, of, retry, Subject, takeWhile, tap, throwError, timer } from 'rxjs';
import { EventSourceFactory, fromEventSource, SseMessage, StreamTransportError } from '../../core/event-source';
import { RunResult, TraceEvent } from '../../core/models';
import { RunStreamActions } from './run.actions';

export const RUN_EVENTS = ['queued', 'trace', 'result', 'error'] as const;
export const MAX_RETRIES = 3;

export const MESSAGES = {
  unreachable: 'Could not reach the Axiom API after several tries. It may be down; try again in a minute.',
  lost: 'Lost the connection mid-run. The server stops a run when its stream drops, so start it again.',
} as const;

function toAction(m: SseMessage): Action {
  try {
    const body = JSON.parse(m.data) as Record<string, unknown>;
    switch (m.event) {
      case 'trace':
        return RunStreamActions.traceReceived({ event: body as unknown as TraceEvent });
      case 'queued':
        return RunStreamActions.queued({ message: String(body['message'] ?? 'Queued') });
      case 'result':
        return RunStreamActions.succeeded({ result: body as unknown as RunResult });
      default:
        return RunStreamActions.failed({ error: String(body['error'] ?? 'The run failed.'), kind: String(body['kind'] ?? 'error') });
    }
  } catch {
    return RunStreamActions.failed({ error: 'The API sent an event this app could not read.', kind: 'bad_event' });
  }
}

/**
 * One run as a stream of actions. Retries a failed connection with backoff, but only before the run has
 * started: the server cancels a run when its stream drops, so reconnecting later would start (and pay for) a
 * new run. Completes after the `result` or `error` event, which closes the EventSource before the browser's own
 * reconnect could open a second run.
 */
export function streamRun(url: string, factory: EventSourceFactory, backoff: (attempt: number) => number): Observable<Action> {
  return defer(() => {
    const retrying = new Subject<Action>();
    let started = false;
    const stream$ = defer(() => fromEventSource(url, factory, RUN_EVENTS)).pipe(
      tap(m => {
        if (m.event === 'trace') started = true;
      }),
      retry({
        count: MAX_RETRIES,
        delay: (err: unknown, attempt: number) => {
          if (started || !(err instanceof StreamTransportError)) return throwError(() => err);
          const delayMs = backoff(attempt);
          retrying.next(RunStreamActions.retrying({ attempt, delayMs }));
          return timer(delayMs);
        },
      }),
      takeWhile(m => m.event !== 'result' && m.event !== 'error', true),
      map(toAction),
      catchError(() =>
        of(RunStreamActions.failed(started ? { error: MESSAGES.lost, kind: 'connection_lost' } : { error: MESSAGES.unreachable, kind: 'unreachable' })),
      ),
      finalize(() => retrying.complete()),
    );
    return merge(retrying, stream$);
  });
}
