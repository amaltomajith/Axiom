import { TestBed } from '@angular/core/testing';
import { provideMockActions } from '@ngrx/effects/testing';
import { Action } from '@ngrx/store';
import { Observable } from 'rxjs';
import { TestScheduler } from 'rxjs/testing';
import { runResult, ScriptStep, scriptedFactory, trace } from '../../../testing/fakes';
import { ApiService } from '../../core/api.service';
import { BACKOFF } from '../../core/backoff';
import { EVENT_SOURCE_FACTORY } from '../../core/event-source';
import { RunMonitorActions, RunStreamActions } from './run.actions';
import { runStream$ } from './run.effects';
import { initialState, reducer } from './run.reducer';
import { MESSAGES, streamRun } from './run-stream';

const backoff = (n: number) => n * 100;
const start = trace('run_start', 'system', { ticker: 'AAPL' });
const result = runResult();
const msg = {
  t: { event: 'trace', data: JSON.stringify(start) } as ScriptStep,
  r: { event: 'result', data: JSON.stringify(result) } as ScriptStep,
  q: { event: 'queued', data: JSON.stringify({ message: 'Another analysis is running; you are queued.' }) } as ScriptStep,
  l: { event: 'error', data: JSON.stringify({ error: 'Rate limit reached; try again later.', kind: 'rate_limited', retry_after: 60 }) } as ScriptStep,
  E: 'ERR' as ScriptStep,
};

describe('streamRun (marbles)', () => {
  let scheduler: TestScheduler;
  beforeEach(() => (scheduler = new TestScheduler((a, e) => expect(a).toEqual(e))));

  it('retries a refused connection with backoff, then streams the run to its result', () => {
    scheduler.run(({ cold, expectObservable }) => {
      const { factory, opened } = scriptedFactory([cold('10ms E', msg), cold('10ms E', msg), cold('5ms t 5ms r', msg)]);
      expectObservable(streamRun('/run', factory, backoff)).toBe('10ms a 109ms b 204ms c 5ms (d|)', {
        a: RunStreamActions.retrying({ attempt: 1, delayMs: 100 }),
        b: RunStreamActions.retrying({ attempt: 2, delayMs: 200 }),
        c: RunStreamActions.traceReceived({ event: start }),
        d: RunStreamActions.succeeded({ result }),
      });
      scheduler.flush();
      expect(opened.length).toBe(3); // a fresh EventSource per attempt
      expect(opened.every(s => s.closed)).toBe(true); // and every one of them closed
    });
  });

  it('does not retry once the run has started: a reconnect would start and pay for a new run', () => {
    scheduler.run(({ cold, expectObservable }) => {
      const { factory, opened } = scriptedFactory([cold('5ms t 5ms E', msg), cold('5ms r', msg)]);
      expectObservable(streamRun('/run', factory, backoff)).toBe('5ms a 5ms (b|)', {
        a: RunStreamActions.traceReceived({ event: start }),
        b: RunStreamActions.failed({ error: MESSAGES.lost, kind: 'connection_lost' }),
      });
      scheduler.flush();
      expect(opened.length).toBe(1);
    });
  });

  it('gives up after three retries and says the API is unreachable', () => {
    scheduler.run(({ cold, expectObservable }) => {
      const { factory, opened } = scriptedFactory([1, 2, 3, 4].map(() => cold('10ms E', msg)));
      // errors at 10, 120, 330 and 640 ms (waits of 100, 200, 300)
      expectObservable(streamRun('/run', factory, backoff)).toBe('10ms a 109ms b 209ms c 309ms (d|)', {
        a: RunStreamActions.retrying({ attempt: 1, delayMs: 100 }),
        b: RunStreamActions.retrying({ attempt: 2, delayMs: 200 }),
        c: RunStreamActions.retrying({ attempt: 3, delayMs: 300 }),
        d: RunStreamActions.failed({ error: MESSAGES.unreachable, kind: 'unreachable' }),
      });
      scheduler.flush();
      expect(opened.length).toBe(4);
    });
  });

  it('treats a server refusal as data: shown, never retried', () => {
    scheduler.run(({ cold, expectObservable }) => {
      const { factory, opened } = scriptedFactory([cold('5ms l', msg)]);
      expectObservable(streamRun('/run', factory, backoff)).toBe('5ms (f|)', {
        f: RunStreamActions.failed({ error: 'Rate limit reached; try again later.', kind: 'rate_limited' }),
      });
      scheduler.flush();
      expect(opened.length).toBe(1);
      expect(opened[0].closed).toBe(true);
    });
  });

  it('completes on the result and closes, before the browser could reconnect into a second run', () => {
    scheduler.run(({ cold, expectObservable }) => {
      // a real server ends the response after `result`; a native EventSource would then fire error and reconnect
      const { factory, opened } = scriptedFactory([cold('1ms q 1ms t 1ms r 1ms E', msg)]);
      expectObservable(streamRun('/run', factory, backoff)).toBe('1ms a 1ms b 1ms (c|)', {
        a: RunStreamActions.queued({ message: 'Another analysis is running; you are queued.' }),
        b: RunStreamActions.traceReceived({ event: start }),
        c: RunStreamActions.succeeded({ result }),
      });
      scheduler.flush();
      expect(opened.length).toBe(1);
      expect(opened[0].closed).toBe(true);
    });
  });
});

describe('runStream$ effect', () => {
  let scheduler: TestScheduler;
  let actions$: Observable<Action>;
  beforeEach(() => (scheduler = new TestScheduler((a, e) => expect(a).toEqual(e))));

  function setup(scripts: Observable<ScriptStep>[]) {
    const scripted = scriptedFactory(scripts);
    TestBed.configureTestingModule({
      providers: [
        provideMockActions(() => actions$),
        { provide: ApiService, useValue: { runStreamUrl: (t: string) => `/api/analyze/stream?ticker=${t}` } },
        { provide: EVENT_SOURCE_FACTORY, useValue: scripted.factory },
        { provide: BACKOFF, useValue: backoff },
      ],
    });
    return { effect$: TestBed.runInInjectionContext(() => runStream$()), opened: scripted.opened };
  }

  it('Cancelled closes the stream', () => {
    scheduler.run(({ hot, cold, expectObservable }) => {
      actions$ = hot('a 9ms c', { a: RunMonitorActions.started({ ticker: 'AAPL' }), c: RunMonitorActions.cancelled() });
      const { effect$, opened } = setup([cold('5ms t 100ms r', msg)]);
      expectObservable(effect$, '^ 200ms !').toBe('5ms t', { t: RunStreamActions.traceReceived({ event: start }) });
      scheduler.flush();
      expect(opened[0].url).toBe('/api/analyze/stream?ticker=AAPL');
      expect(opened[0].closed).toBe(true);
    });
  });

  it('a new run replaces the current one and closes the old EventSource (switchMap)', () => {
    scheduler.run(({ hot, cold, expectObservable }) => {
      actions$ = hot('a 9ms b', { a: RunMonitorActions.started({ ticker: 'AAPL' }), b: RunMonitorActions.started({ ticker: 'MSFT' }) });
      const { effect$, opened } = setup([cold('5ms t 100ms r', msg), cold('5ms r', msg)]);
      expectObservable(effect$, '^ 200ms !').toBe('5ms t 9ms s', {
        t: RunStreamActions.traceReceived({ event: start }),
        s: RunStreamActions.succeeded({ result }),
      });
      scheduler.flush();
      expect(opened.map(o => [o.url.split('=')[1], o.closed])).toEqual([
        ['AAPL', true],
        ['MSFT', true],
      ]);
    });
  });
});

describe('run reducer', () => {
  it('walks connecting, retrying, queued, running, done', () => {
    let s = reducer(initialState, RunMonitorActions.started({ ticker: 'AAPL' }));
    expect(s).toMatchObject({ ticker: 'AAPL', status: 'connecting', events: [] });
    s = reducer(s, RunStreamActions.retrying({ attempt: 1, delayMs: 1000 }));
    expect(s).toMatchObject({ status: 'retrying', attempt: 1, retryInMs: 1000 });
    s = reducer(s, RunStreamActions.queued({ message: 'queued' }));
    expect(s).toMatchObject({ status: 'queued', queueMessage: 'queued', retryInMs: null });
    s = reducer(s, RunStreamActions.traceReceived({ event: start }));
    expect(s).toMatchObject({ status: 'running', events: [start] });
    s = reducer(s, RunStreamActions.succeeded({ result }));
    expect(s).toMatchObject({ status: 'done', result });
  });

  it('records a failure and a cancel, and a new start clears the old run', () => {
    let s = reducer(initialState, RunMonitorActions.started({ ticker: 'AAPL' }));
    s = reducer(s, RunStreamActions.failed({ error: 'boom', kind: 'deadline' }));
    expect(s).toMatchObject({ status: 'error', error: 'boom', errorKind: 'deadline' });
    expect(reducer(s, RunMonitorActions.cancelled())).toBe(s); // nothing to cancel
    s = reducer(s, RunMonitorActions.started({ ticker: 'MSFT' }));
    expect(s).toMatchObject({ ticker: 'MSFT', status: 'connecting', error: null, result: null });
    expect(reducer(s, RunMonitorActions.cancelled()).status).toBe('cancelled');
  });
});
