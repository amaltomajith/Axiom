import { item, summary } from '../../../testing/fakes';
import { QuotesApiActions, RatingsApiActions, WatchlistApiActions, WatchlistPageActions } from './watchlist.actions';
import { adapter, initialState, reducer, WatchlistState } from './watchlist.reducer';

const withItems = (...items: Parameters<typeof item>[]): WatchlistState =>
  adapter.setAll(
    items.map(args => item(...args)),
    { ...initialState, loaded: true },
  );
const tickers = (s: WatchlistState) => s.ids as string[];

describe('watchlist reducer', () => {
  it('Opened starts loading only the first time', () => {
    expect(reducer(initialState, WatchlistPageActions.opened()).loading).toBe(true);
    expect(reducer(withItems(['AAPL', 1]), WatchlistPageActions.opened()).loading).toBe(false);
  });

  it('Load Succeeded replaces the list but keeps in-flight optimistic changes', () => {
    let s = withItems(['OLD', 1], ['GONE', 2]);
    s = reducer(s, WatchlistPageActions.addRequested({ ticker: 'NEW', requestedAt: 9 }));
    s = reducer(s, WatchlistPageActions.removeRequested({ ticker: 'GONE' }));
    s = reducer(s, WatchlistApiActions.loadSucceeded({ items: [item('AAPL', 3), item('GONE', 2)] }));
    expect(tickers(s)).toEqual(['AAPL', 'NEW']); // GONE is still being removed, NEW still being added
    expect(s.loaded && !s.loading).toBe(true);
  });

  it('Load Failed records the error', () => {
    const s = reducer({ ...initialState, loading: true }, WatchlistApiActions.loadFailed({ error: 'down' }));
    expect(s).toMatchObject({ loading: false, error: 'down' });
  });

  describe('optimistic add', () => {
    it('shows the row at once, marked pending, sorted by time added', () => {
      const s = reducer(withItems(['AAPL', 1]), WatchlistPageActions.addRequested({ ticker: 'NVDA', requestedAt: 5 }));
      expect(tickers(s)).toEqual(['AAPL', 'NVDA']);
      expect(s.entities['NVDA']).toEqual({ ticker: 'NVDA', added_at: 5, pending: true });
    });

    it('Add Succeeded settles the row with the server time', () => {
      let s = reducer(initialState, WatchlistPageActions.addRequested({ ticker: 'NVDA', requestedAt: 5 }));
      s = reducer(s, WatchlistApiActions.addSucceeded({ ticker: 'NVDA', item: item('NVDA', 6) }));
      expect(s.entities['NVDA']).toEqual({ ticker: 'NVDA', added_at: 6 });
    });

    it('Add Succeeded does not resurrect a row the user removed meanwhile', () => {
      let s = reducer(initialState, WatchlistPageActions.addRequested({ ticker: 'NVDA', requestedAt: 5 }));
      s = reducer(s, WatchlistPageActions.removeRequested({ ticker: 'NVDA' }));
      s = reducer(s, WatchlistApiActions.addSucceeded({ ticker: 'NVDA', item: item('NVDA', 6) }));
      expect(tickers(s)).toEqual([]);
    });

    it('rollback: Add Failed removes the optimistic row and says why', () => {
      let s = reducer(withItems(['AAPL', 1]), WatchlistPageActions.addRequested({ ticker: 'NVDA', requestedAt: 5 }));
      s = reducer(s, WatchlistApiActions.addFailed({ ticker: 'NVDA', error: 'Your watchlist is full (25 tickers).' }));
      expect(tickers(s)).toEqual(['AAPL']);
      expect(s.notice).toEqual({ tone: 'error', text: 'Could not add NVDA: Your watchlist is full (25 tickers).' });
    });

    it('rollback never deletes a row the user already had', () => {
      let s = withItems(['NVDA', 1]);
      s = reducer(s, WatchlistPageActions.addRequested({ ticker: 'NVDA', requestedAt: 5 })); // no-op: listed
      expect(s.entities['NVDA']?.pending).toBeUndefined();
      s = reducer(s, WatchlistApiActions.addFailed({ ticker: 'NVDA', error: 'Rate limit' }));
      expect(tickers(s)).toEqual(['NVDA']);
      expect(s.notice?.tone).toBe('error');
    });
  });

  describe('optimistic remove', () => {
    it('hides the row at once and stashes it', () => {
      const s = reducer(withItems(['AAPL', 1], ['MSFT', 2]), WatchlistPageActions.removeRequested({ ticker: 'AAPL' }));
      expect(tickers(s)).toEqual(['MSFT']);
      expect(s.removed['AAPL']).toEqual(item('AAPL', 1));
    });

    it('Remove Succeeded drops the stash and the cached quote', () => {
      let s = withItems(['AAPL', 1]);
      s = reducer(s, QuotesApiActions.refreshSucceeded({ ticker: 'AAPL', quote: summary(100), fetchedAt: 1 }));
      s = reducer(s, WatchlistPageActions.removeRequested({ ticker: 'AAPL' }));
      s = reducer(s, WatchlistApiActions.removeSucceeded({ ticker: 'AAPL' }));
      expect(s.removed).toEqual({});
      expect(s.quotes).toEqual({});
    });

    it('rollback: Remove Failed puts the exact row back in its place and says why', () => {
      let s = withItems(['AAPL', 1], ['MSFT', 2], ['TSLA', 3]);
      s = reducer(s, QuotesApiActions.refreshSucceeded({ ticker: 'MSFT', quote: summary(400), fetchedAt: 1 }));
      s = reducer(s, WatchlistPageActions.removeRequested({ ticker: 'MSFT' }));
      s = reducer(s, WatchlistApiActions.removeFailed({ ticker: 'MSFT', error: 'Cannot reach the Axiom API.' }));
      expect(tickers(s)).toEqual(['AAPL', 'MSFT', 'TSLA']);
      expect(s.entities['MSFT']).toEqual(item('MSFT', 2));
      expect(s.quotes['MSFT']?.data?.last_close).toBe(400); // the price never left
      expect(s.removed).toEqual({});
      expect(s.notice).toEqual({ tone: 'error', text: 'Could not remove MSFT: Cannot reach the Axiom API.' });
    });

    it('Remove Requested for an unknown ticker changes nothing', () => {
      const s = withItems(['AAPL', 1]);
      expect(reducer(s, WatchlistPageActions.removeRequested({ ticker: 'ZZZ' }))).toBe(s);
    });
  });

  it('Notice Dismissed clears the message', () => {
    const s = reducer({ ...initialState, notice: { tone: 'error', text: 'x' } }, WatchlistPageActions.noticeDismissed());
    expect(s.notice).toBeNull();
  });

  describe('quotes and ratings', () => {
    it('stores a fetched quote, ignoring tickers no longer listed', () => {
      let s = withItems(['AAPL', 1]);
      s = reducer(s, QuotesApiActions.refreshSucceeded({ ticker: 'AAPL', quote: summary(100), fetchedAt: 7 }));
      s = reducer(s, QuotesApiActions.refreshSucceeded({ ticker: 'GONE', quote: summary(1), fetchedAt: 7 }));
      expect(Object.keys(s.quotes)).toEqual(['AAPL']);
      expect(s.quotes['AAPL']).toEqual({ data: summary(100), error: null, fetchedAt: 7 });
    });

    it('a failed refresh keeps the last good price next to the error', () => {
      let s = withItems(['AAPL', 1]);
      s = reducer(s, QuotesApiActions.refreshSucceeded({ ticker: 'AAPL', quote: summary(100), fetchedAt: 7 }));
      s = reducer(s, QuotesApiActions.refreshFailed({ ticker: 'AAPL', error: 'No price data returned.' }));
      expect(s.quotes['AAPL']).toEqual({ data: summary(100), error: 'No price data returned.', fetchedAt: 7 });
      s = reducer(withItems(['NEW', 1]), QuotesApiActions.refreshFailed({ ticker: 'NEW', error: 'x' }));
      expect(s.quotes['NEW']).toEqual({ data: null, error: 'x', fetchedAt: null });
    });

    it('stores ratings and their error', () => {
      const ratings = { AAPL: { rating: 'BUY' as const, conviction: 0.6, issuedOn: '2026-11-01' } };
      let s = reducer(initialState, RatingsApiActions.refreshFailed({ error: 'down' }));
      expect(s.ratingsError).toBe('down');
      s = reducer(s, RatingsApiActions.refreshSucceeded({ ratings }));
      expect(s).toMatchObject({ ratings, ratingsError: null });
    });
  });
});
