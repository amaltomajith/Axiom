import { Type } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Action } from '@ngrx/store';
import { MockStore, provideMockStore } from '@ngrx/store/testing';
import { runResult, trace } from '../testing/fakes';
import { RunMonitor } from './run/run-monitor.component';
import { RunMonitorActions } from './run/state/run.actions';
import { initialState as runInitial, RunState } from './run/state/run.reducer';
import { TickerSearch } from './search/ticker-search.component';
import { TickerSearchActions } from './search/state/search.actions';
import { initialState as searchInitial, SearchState } from './search/state/search.reducer';
import { WatchlistPageActions } from './watchlist/state/watchlist.actions';
import { adapter, initialState as watchInitial, WatchlistState } from './watchlist/state/watchlist.reducer';
import { Watchlist } from './watchlist/watchlist.component';

interface Root {
  watchlist: WatchlistState;
  search: SearchState;
  run: RunState;
}

function state(over: { watchlist?: Partial<WatchlistState>; search?: Partial<SearchState>; run?: Partial<RunState> } = {}): Root {
  return {
    watchlist: { ...watchInitial, loaded: true, ...over.watchlist },
    search: { ...searchInitial, ...over.search },
    run: { ...runInitial, ...over.run },
  };
}

function mount<T>(component: Type<T>, initial: Root): { fixture: ComponentFixture<T>; store: MockStore; dispatched: string[] } {
  TestBed.configureTestingModule({ imports: [component], providers: [provideMockStore({ initialState: initial })] });
  const store = TestBed.inject(MockStore);
  const dispatched: string[] = [];
  const real = store.dispatch.bind(store);
  store.dispatch = ((a: Action) => (dispatched.push(JSON.stringify(a)), real(a))) as typeof store.dispatch;
  const fixture = TestBed.createComponent(component);
  fixture.detectChanges();
  return { fixture, store, dispatched };
}

const text = (f: ComponentFixture<unknown>) => (f.nativeElement as HTMLElement).textContent?.replace(/\s+/g, ' ') ?? '';
const $ = <E extends Element = HTMLElement>(f: ComponentFixture<unknown>, sel: string) => (f.nativeElement as HTMLElement).querySelector<E>(sel);
const $$ = (f: ComponentFixture<unknown>, sel: string) => Array.from((f.nativeElement as HTMLElement).querySelectorAll<HTMLElement>(sel));

function type(f: ComponentFixture<unknown>, sel: string, value: string): void {
  const input = $<HTMLInputElement>(f, sel);
  if (!input) throw new Error(`no ${sel}`);
  input.value = value;
  input.dispatchEvent(new Event('input'));
  f.detectChanges();
}

describe('Watchlist component', () => {
  const listed = adapter.setAll(
    [
      { ticker: 'AAPL', added_at: 1 },
      { ticker: 'MSFT', added_at: 2 },
      { ticker: 'NVDA', added_at: 3, pending: true },
    ],
    { ...watchInitial, loaded: true },
  );
  const withQuotes: Partial<WatchlistState> = {
    ...listed,
    quotes: {
      AAPL: { data: { meta: {}, last_close: 190.5, returns_pct: { '1d': 1.2, '5d': null, '1m': -2, '3m': null, '6m': null, '1y': null }, range_52w: { high: 1, low: 1, pct_below_high: 0, pct_above_low: 0 }, avg_volume_20d: 1 }, error: null, fetchedAt: 1 },
    },
    ratings: { AAPL: { rating: 'BUY', conviction: 0.6, issuedOn: '2026-11-01' } },
  };

  it('renders a row per ticker with price, change, rating and the pending state', () => {
    const { fixture } = mount(Watchlist, state({ watchlist: withQuotes }));
    const rows = $$(fixture, 'tbody tr');
    expect(rows.map(r => r.querySelector('th')?.textContent?.trim().split(/\s+/)[0])).toEqual(['AAPL', 'MSFT', 'NVDA']);
    expect(rows[0].textContent).toContain('$190.50');
    expect(rows[0].textContent).toContain('+1.20%');
    expect(rows[0].textContent).toContain('Buy');
    expect(rows[1].textContent).toContain('Loading');
    expect(rows[1].textContent).toContain('Not rated');
    expect(rows[2].classList).toContain('pending');
    expect(rows[2].textContent).toContain('Adding');
    expect(text(fixture)).toContain('3 of 25');
  });

  it('filters and sorts through the form controls (combineLatest with the store)', () => {
    const { fixture } = mount(Watchlist, state({ watchlist: withQuotes }));
    type(fixture, '#watch-filter', 'ms');
    expect($$(fixture, 'tbody tr').length).toBe(1);
    type(fixture, '#watch-filter', 'zz');
    expect(text(fixture)).toContain('No ticker on your list matches that filter.');
    type(fixture, '#watch-filter', '');
    const sort = $<HTMLSelectElement>(fixture, '#watch-sort');
    if (!sort) throw new Error('no sort');
    sort.value = 'rating';
    sort.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    expect($$(fixture, 'tbody th').map(t => t.textContent?.trim().split(/\s+/)[0])).toEqual(['AAPL', 'MSFT', 'NVDA']);
  });

  it('dispatches Remove Requested and Run Monitor Started, and never calls the API itself', () => {
    const { fixture, dispatched } = mount(Watchlist, state({ watchlist: withQuotes }));
    $<HTMLButtonElement>(fixture, 'button[aria-label="Remove MSFT from the watchlist"]')?.click();
    $<HTMLButtonElement>(fixture, 'button[aria-label="Run Axiom research on AAPL"]')?.click();
    expect(dispatched).toEqual([
      JSON.stringify(WatchlistPageActions.removeRequested({ ticker: 'MSFT' })),
      JSON.stringify(RunMonitorActions.started({ ticker: 'AAPL' })),
    ]);
  });

  it('shows the rollback message and lets the user dismiss it', () => {
    const { fixture, dispatched } = mount(
      Watchlist,
      state({ watchlist: { ...listed, notice: { tone: 'error', text: 'Could not add TSLA: Your watchlist is full (25 tickers).' } } }),
    );
    expect($(fixture, '[role="status"]')?.textContent).toContain('Could not add TSLA');
    $<HTMLButtonElement>(fixture, '.notice button')?.click();
    expect(dispatched).toEqual([JSON.stringify(WatchlistPageActions.noticeDismissed())]);
  });

  it('has empty and error states', () => {
    expect(text(mount(Watchlist, state()).fixture)).toContain('Your watchlist is empty.');
    TestBed.resetTestingModule();
    const { fixture, dispatched } = mount(Watchlist, state({ watchlist: { error: 'Cannot reach the Axiom API.' } }));
    expect(text(fixture)).toContain('Could not load your watchlist: Cannot reach the Axiom API.');
    $<HTMLButtonElement>(fixture, '.empty button')?.click();
    expect(dispatched).toEqual([JSON.stringify(WatchlistPageActions.opened())]);
  });
});

describe('TickerSearch component', () => {
  const results = [
    { ticker: 'NVDA', name: 'NVIDIA CORP' },
    { ticker: 'NVDL', name: 'GraniteShares 2x Long NVDA' },
  ];

  it('dispatches every keystroke; debouncing is the job of the effect', () => {
    const { fixture, dispatched } = mount(TickerSearch, state());
    type(fixture, '#ticker-search', 'n');
    type(fixture, '#ticker-search', 'nv');
    expect(dispatched).toEqual([
      JSON.stringify(TickerSearchActions.queryChanged({ query: 'n' })),
      JSON.stringify(TickerSearchActions.queryChanged({ query: 'nv' })),
    ]);
  });

  it('lists results as options, marks listed tickers, and adds a pick with the keyboard', () => {
    const watch = adapter.setAll([{ ticker: 'NVDL', added_at: 1 }], { ...watchInitial, loaded: true });
    const { fixture, store, dispatched } = mount(TickerSearch, state({ watchlist: watch }));
    type(fixture, '#ticker-search', 'nv');
    store.setState(state({ watchlist: watch, search: { query: 'nv', answered: 'nv', results } }));
    fixture.detectChanges();

    const options = $$(fixture, '[role="option"]');
    expect(options.map(o => o.querySelector('.sym')?.textContent)).toEqual(['NVDA', 'NVDL']);
    expect(options[1].getAttribute('aria-disabled')).toBe('true');
    expect(options[1].textContent).toContain('On your list');
    expect($(fixture, '[role="status"]')?.textContent).toContain('2 matches');

    const input = $<HTMLInputElement>(fixture, '#ticker-search');
    input?.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }));
    fixture.detectChanges();
    expect(input?.getAttribute('aria-activedescendant')).toBe('ticker-opt-0');
    input?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    const added = JSON.parse(dispatched[dispatched.length - 2]) as { type: string; ticker: string };
    expect(added).toMatchObject({ type: WatchlistPageActions.addRequested.type, ticker: 'NVDA' });
    expect(input?.value).toBe(''); // the box clears after a pick
  });

  it('says when nothing matches and shows errors', () => {
    const { fixture, store } = mount(TickerSearch, state());
    store.setState(state({ search: { query: 'zzzz', answered: 'zzzz', results: [] } }));
    fixture.detectChanges();
    expect($(fixture, '[role="status"]')?.textContent).toContain('No ticker with SEC filings matches that.');
    store.setState(state({ search: { query: 'x', answered: 'x', results: [], error: 'Cannot reach the Axiom API.' } }));
    fixture.detectChanges();
    expect($(fixture, '[role="status"]')?.textContent).toContain('Cannot reach the Axiom API.');
  });
});

describe('RunMonitor component', () => {
  it('starts a run for a valid ticker and refuses an invalid one', () => {
    const { fixture, dispatched } = mount(RunMonitor, state());
    type(fixture, '#run-ticker', '1bad');
    $<HTMLFormElement>(fixture, 'form')?.dispatchEvent(new Event('submit'));
    fixture.detectChanges();
    expect(dispatched).toEqual([]);
    expect(text(fixture)).toContain('Enter a ticker');
    type(fixture, '#run-ticker', 'aapl');
    $<HTMLFormElement>(fixture, 'form')?.dispatchEvent(new Event('submit'));
    expect(dispatched).toEqual([JSON.stringify(RunMonitorActions.started({ ticker: 'AAPL' }))]);
  });

  it('shows live steps, the waking-up retry, and the final rating', () => {
    const { fixture, store } = mount(RunMonitor, state());
    store.setState(state({ run: { ticker: 'AAPL', status: 'retrying', attempt: 2, retryInMs: 2000 } }));
    fixture.detectChanges();
    expect(text(fixture)).toContain('The API is waking up. Trying again in 2 s (attempt 2 of 3).');

    const events = [trace('run_start', 'system', { ticker: 'AAPL' }), trace('agent_start', 'Technical Analyst')];
    store.setState(state({ run: { ticker: 'AAPL', status: 'running', events } }));
    fixture.detectChanges();
    const steps = $$(fixture, '.steps li');
    expect(steps.length).toBe(7);
    expect(steps.map(s => s.dataset['state'])).toEqual(['done', 'active', 'pending', 'pending', 'pending', 'pending', 'pending']);
    expect($(fixture, 'button.btn:not(.primary)')?.textContent).toContain('Cancel');

    store.setState(state({ run: { ticker: 'AAPL', status: 'done', events, result: runResult('STRONG_BUY') } }));
    fixture.detectChanges();
    expect($(fixture, '.result')?.textContent).toContain('Strong buy');
    expect($(fixture, '.result')?.textContent).toContain('62% conviction, 20 day horizon');
  });

  it('cancels an active run when it is destroyed, which closes the EventSource', () => {
    const { fixture, dispatched } = mount(RunMonitor, state({ run: { ticker: 'AAPL', status: 'running' } }));
    fixture.destroy();
    expect(dispatched).toEqual([JSON.stringify(RunMonitorActions.cancelled())]);
  });

  it('prefills the ticker from the deep link without starting a run', () => {
    const { fixture, dispatched } = mount(RunMonitor, state());
    fixture.componentRef.setInput('ticker', 'msft');
    fixture.detectChanges();
    expect($<HTMLInputElement>(fixture, '#run-ticker')?.value).toBe('MSFT');
    expect(dispatched).toEqual([]);
  });
});
