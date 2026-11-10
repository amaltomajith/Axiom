import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideMockActions } from '@ngrx/effects/testing';
import { Action } from '@ngrx/store';
import { MockStore, provideMockStore } from '@ngrx/store/testing';
import { Observable, of } from 'rxjs';
import { TestScheduler } from 'rxjs/testing';
import { item, runResult, summary } from '../../../testing/fakes';
import { ApiService } from '../../core/api.service';
import { ApiStatusService } from '../../core/api-status.service';
import { PAGE_VISIBLE } from '../../core/page-visibility';
import { RunStreamActions } from '../../run/state/run.actions';
import { QUOTE_REFRESH_MS } from './quote-refresh';
import { QuotesApiActions, RatingsApiActions, WatchlistApiActions, WatchlistPageActions } from './watchlist.actions';
import { loadWatchlist$, quoteNewTicker$, refreshQuotes$, refreshRatings$, writeWatchlist$ } from './watchlist.effects';
import { selectTickers } from './watchlist.selectors';

type ApiMock = Partial<Record<keyof ApiService, unknown>>;

describe('watchlist effects', () => {
  let scheduler: TestScheduler;
  let actions$: Observable<Action>;

  function setup(api: ApiMock, extra: unknown[] = [], ready$: Observable<unknown> = of({ ok: true })) {
    TestBed.configureTestingModule({
      providers: [
        provideMockActions(() => actions$),
        provideMockStore(),
        { provide: ApiService, useValue: api },
        { provide: ApiStatusService, useValue: { ready$ } },
        ...(extra as never[]),
      ],
    });
  }
  const run = <T>(effect: () => T): T => TestBed.runInInjectionContext(effect);

  beforeEach(() => (scheduler = new TestScheduler((a, e) => expect(a).toEqual(e))));

  describe('loadWatchlist$', () => {
    it('waits for the API to be awake, then loads the visitor list', () => {
      scheduler.run(({ hot, cold, expectObservable }) => {
        actions$ = hot('a', { a: WatchlistPageActions.opened() });
        setup({ visitorWatchlist: () => cold('10ms (l|)', { l: [item('AAPL')] }) }, [], cold('50ms (h|)', { h: { ok: true } }));
        expectObservable(run(() => loadWatchlist$())).toBe('60ms s', {
          s: WatchlistApiActions.loadSucceeded({ items: [item('AAPL')] }),
        });
      });
    });

    it('reports a failure as Load Failed', () => {
      scheduler.run(({ hot, cold, expectObservable }) => {
        actions$ = hot('a', { a: WatchlistPageActions.opened() });
        setup({ visitorWatchlist: () => cold('5ms #', {}, new HttpErrorResponse({ status: 0 })) });
        expectObservable(run(() => loadWatchlist$())).toBe('5ms f', {
          f: WatchlistApiActions.loadFailed({ error: 'Cannot reach the Axiom API.' }),
        });
      });
    });
  });

  describe('writeWatchlist$ (optimistic writes)', () => {
    it('maps a successful PUT to Add Succeeded with the server row', () => {
      scheduler.run(({ hot, cold, expectObservable }) => {
        actions$ = hot('-a', { a: WatchlistPageActions.addRequested({ ticker: 'NVDA', requestedAt: 5 }) });
        setup({ watchAdd: () => cold('--(x|)', { x: [item('AAPL', 1), item('NVDA', 6)] }) });
        expectObservable(run(() => writeWatchlist$())).toBe('---s', {
          s: WatchlistApiActions.addSucceeded({ ticker: 'NVDA', item: item('NVDA', 6) }),
        });
      });
    });

    it('maps a refused PUT to Add Failed (the rollback) and keeps working afterwards', () => {
      scheduler.run(({ hot, cold, expectObservable }) => {
        const full = new HttpErrorResponse({ status: 409, error: { detail: 'Your watchlist is full (25 tickers). Remove one first.' } });
        actions$ = hot('-a---b', {
          a: WatchlistPageActions.addRequested({ ticker: 'NVDA', requestedAt: 5 }),
          b: WatchlistPageActions.removeRequested({ ticker: 'AAPL' }),
        });
        setup({ watchAdd: () => cold('--#', {}, full), watchRemove: () => cold('-(x|)', { x: [] }) });
        expectObservable(run(() => writeWatchlist$())).toBe('---f--d', {
          f: WatchlistApiActions.addFailed({ ticker: 'NVDA', error: 'Your watchlist is full (25 tickers). Remove one first.' }),
          d: WatchlistApiActions.removeSucceeded({ ticker: 'AAPL' }),
        });
      });
    });

    it('sends writes in order: a remove waits until the earlier add has finished (concatMap)', () => {
      scheduler.run(({ hot, cold, expectObservable, expectSubscriptions }) => {
        const put = cold('----(x|)', { x: [item('NVDA', 6)] });
        const del = cold('-(y|)', { y: [] });
        actions$ = hot('-a-r', {
          a: WatchlistPageActions.addRequested({ ticker: 'NVDA', requestedAt: 5 }),
          r: WatchlistPageActions.removeRequested({ ticker: 'NVDA' }),
        });
        setup({ watchAdd: () => put, watchRemove: () => del });
        expectObservable(run(() => writeWatchlist$())).toBe('-----sd', {
          s: WatchlistApiActions.addSucceeded({ ticker: 'NVDA', item: item('NVDA', 6) }),
          d: WatchlistApiActions.removeSucceeded({ ticker: 'NVDA' }),
        });
        expectSubscriptions(put.subscriptions).toBe('-^---!');
        expectSubscriptions(del.subscriptions).toBe('-----^!'); // not at frame 3, when it was requested
      });
    });
  });

  it('quoteNewTicker$ fetches the price of a ticker as soon as it is added', () => {
    scheduler.run(({ hot, cold, expectObservable }) => {
      actions$ = hot('a', { a: WatchlistApiActions.addSucceeded({ ticker: 'NVDA', item: item('NVDA') }) });
      setup({ summary: () => cold('3ms (q|)', { q: summary(150) }) });
      expectObservable(run(() => quoteNewTicker$())).toBe('3ms s', {
        s: QuotesApiActions.refreshSucceeded({ ticker: 'NVDA', quote: summary(150), fetchedAt: expect.any(Number) as unknown as number }),
      });
    });
  });

  describe('refreshQuotes$', () => {
    it('refreshes on a timer, pauses while the tab is hidden, and refreshes at once when it returns', () => {
      scheduler.run(({ hot, cold, expectObservable }) => {
        actions$ = hot('a', { a: WatchlistApiActions.loadSucceeded({ items: [item('AAPL')] }) });
        const visible = hot('t 249ms f 299ms t', { t: true, f: false }); // hidden from 250 ms to 550 ms
        setup({ summary: () => cold('(q|)', { q: summary(190) }) }, [
          { provide: PAGE_VISIBLE, useValue: visible },
          { provide: QUOTE_REFRESH_MS, useValue: 100 },
        ]);
        TestBed.inject(MockStore).overrideSelector(selectTickers, ['AAPL']);
        const q = QuotesApiActions.refreshSucceeded({ ticker: 'AAPL', quote: summary(190), fetchedAt: expect.any(Number) as unknown as number });
        // ticks at 0, 100, 200; nothing while hidden; then 550 (immediately on return) and 650
        expectObservable(run(() => refreshQuotes$()), '^ 700ms !').toBe('q 99ms q 99ms q 349ms q 99ms q', { q });
      });
    });

    it('fetches every listed ticker, two at a time, and reports failures per ticker', () => {
      scheduler.run(({ hot, cold, expectObservable }) => {
        actions$ = hot('a', { a: WatchlistApiActions.loadSucceeded({ items: [] }) });
        const slow = (t: string) =>
          t === 'BAD'
            ? cold('10ms #', {}, new HttpErrorResponse({ status: 400, error: { error: 'No price data returned.' } }))
            : cold('10ms (q|)', { q: summary(1) });
        setup({ summary: slow }, [
          { provide: PAGE_VISIBLE, useValue: hot('t', { t: true }) },
          { provide: QUOTE_REFRESH_MS, useValue: 1000 },
        ]);
        TestBed.inject(MockStore).overrideSelector(selectTickers, ['A', 'BAD', 'C']);
        const ok = (ticker: string) => QuotesApiActions.refreshSucceeded({ ticker, quote: summary(1), fetchedAt: expect.any(Number) as unknown as number });
        expectObservable(run(() => refreshQuotes$()), '^ 30ms !').toBe('10ms (ab) 6ms c', {
          a: ok('A'),
          b: QuotesApiActions.refreshFailed({ ticker: 'BAD', error: 'No price data returned.' }),
          c: ok('C'), // the third request starts only when one of the first two finished
        });
      });
    });
  });

  it('refreshRatings$ reloads the latest rating per ticker when a run finishes', () => {
    scheduler.run(({ hot, cold, expectObservable }) => {
      actions$ = hot('-r', { r: RunStreamActions.succeeded({ result: runResult() }) });
      const rows = [{ id: '1', run_id: 'r', ticker: 'AAPL', created_at: 2, issue_date: '2026-11-10', rating: 'BUY', conviction: 0.62 }];
      setup({ theses: () => cold('-(t|)', { t: rows }) });
      expectObservable(run(() => refreshRatings$())).toBe('--s', {
        s: RatingsApiActions.refreshSucceeded({ ratings: { AAPL: { rating: 'BUY', conviction: 0.62, issuedOn: '2026-11-10' } } }),
      });
    });
  });
});
