import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideMockActions } from '@ngrx/effects/testing';
import { Action } from '@ngrx/store';
import { Observable } from 'rxjs';
import { TestScheduler } from 'rxjs/testing';
import { ApiService } from '../../core/api.service';
import { TickerMatch } from '../../core/models';
import { SearchApiActions, TickerSearchActions } from './search.actions';
import { search$ } from './search.effects';
import { initialState, searchFeature } from './search.reducer';

const q = (query: string) => TickerSearchActions.queryChanged({ query });
const NVDA: TickerMatch[] = [{ ticker: 'NVDA', name: 'NVIDIA CORP' }];

describe('search$ (marbles)', () => {
  let scheduler: TestScheduler;
  let actions$: Observable<Action>;
  const calls: string[] = [];

  function effect(searchTickers: (q: string) => Observable<TickerMatch[]>) {
    TestBed.configureTestingModule({
      providers: [
        provideMockActions(() => actions$),
        { provide: ApiService, useValue: { searchTickers: (s: string) => (calls.push(s), searchTickers(s)) } },
      ],
    });
    return TestBed.runInInjectionContext(() => search$());
  }

  beforeEach(() => {
    calls.length = 0;
    scheduler = new TestScheduler((a, e) => expect(a).toEqual(e));
  });

  it('debounces typing: three fast keystrokes make one request, 250 ms after the last', () => {
    scheduler.run(({ hot, cold, expectObservable }) => {
      actions$ = hot('a 100ms b 100ms c', { a: q('n'), b: q('nv'), c: q('nvda') }); // c at 202 ms
      const out = effect(() => cold('50ms (r|)', { r: NVDA }));
      expectObservable(out).toBe('502ms s', { s: SearchApiActions.searchSucceeded({ query: 'nvda', results: NVDA }) });
    });
    expect(calls).toEqual(['nvda']);
  });

  it('switchMap drops a slow stale answer when a newer query arrives', () => {
    scheduler.run(({ hot, cold, expectObservable, expectSubscriptions }) => {
      actions$ = hot('a 299ms b', { a: q('nv'), b: q('nvda') }); // emitted after debounce at 250 and 550
      const slow = cold('500ms (r|)', { r: [{ ticker: 'NV', name: 'stale' }] });
      const fast = cold('100ms (r|)', { r: NVDA });
      const out = effect(s => (s === 'nv' ? slow : fast));
      expectObservable(out).toBe('650ms s', { s: SearchApiActions.searchSucceeded({ query: 'nvda', results: NVDA }) });
      expectSubscriptions(slow.subscriptions).toBe('250ms ^ 299ms !'); // cancelled at 550, before it answered
    });
  });

  it('skips a repeat query and ignores surrounding spaces', () => {
    scheduler.run(({ hot, cold, expectObservable }) => {
      actions$ = hot('a 300ms b 300ms c', { a: q('aapl'), b: q(' aapl '), c: q('msft') });
      const out = effect(s => cold('(r|)', { r: [{ ticker: s.toUpperCase(), name: s }] }));
      expectObservable(out).toBe('250ms x 601ms y', {
        x: SearchApiActions.searchSucceeded({ query: 'aapl', results: [{ ticker: 'AAPL', name: 'aapl' }] }),
        y: SearchApiActions.searchSucceeded({ query: 'msft', results: [{ ticker: 'MSFT', name: 'msft' }] }),
      });
    });
    expect(calls).toEqual(['aapl', 'msft']);
  });

  it('catchError inside switchMap: a failed request becomes an action and search keeps working', () => {
    scheduler.run(({ hot, cold, expectObservable }) => {
      actions$ = hot('a 300ms b', { a: q('x'), b: q('nvda') });
      const out = effect(s =>
        s === 'x' ? cold('10ms #', {}, new HttpErrorResponse({ status: 0 })) : cold('10ms (r|)', { r: NVDA }),
      );
      expectObservable(out).toBe('260ms f 300ms s', {
        f: SearchApiActions.searchFailed({ query: 'x', error: 'Cannot reach the Axiom API.' }),
        s: SearchApiActions.searchSucceeded({ query: 'nvda', results: NVDA }),
      });
    });
  });

  it('clears the results for an empty box without calling the API', () => {
    scheduler.run(({ hot, expectObservable }) => {
      actions$ = hot('a', { a: q('   ') });
      expectObservable(effect(() => hot('')), '^ 400ms !').toBe('250ms c', { c: SearchApiActions.searchCleared() });
    });
    expect(calls).toEqual([]);
  });
});

describe('search reducer and selectors', () => {
  const reducer = searchFeature.reducer;
  const root = (search: typeof initialState) => ({ search });

  it('tracks the query and whether the results answer it', () => {
    let s = reducer(initialState, q('nvda'));
    expect(s.query).toBe('nvda');
    expect(searchFeature.selectPending(root(s))).toBe(true);
    s = reducer(s, SearchApiActions.searchSucceeded({ query: 'nvda', results: NVDA }));
    expect(s).toMatchObject({ answered: 'nvda', results: NVDA, error: null });
    expect(searchFeature.selectPending(root(s))).toBe(false);
  });

  it('is not left pending when a repeat query is dropped by distinctUntilChanged', () => {
    let s = reducer(initialState, q('nv'));
    s = reducer(s, SearchApiActions.searchSucceeded({ query: 'nv', results: NVDA }));
    s = reducer(s, q('nvd'));
    s = reducer(s, q('nv ')); // the effect never sends this one again
    expect(searchFeature.selectPending(root(s))).toBe(false);
  });

  it('stores a failure and clears', () => {
    let s = reducer(initialState, SearchApiActions.searchFailed({ query: 'x', error: 'down' }));
    expect(s).toMatchObject({ answered: 'x', results: [], error: 'down' });
    s = reducer({ ...s, results: NVDA }, SearchApiActions.searchCleared());
    expect(s).toMatchObject({ answered: '', results: [], error: null });
  });
});
