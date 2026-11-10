import { item, summary } from '../../../testing/fakes';
import { initialState as runInitial } from '../../run/state/run.reducer';
import { initialState as searchInitial } from '../../search/state/search.reducer';
import { adapter, initialState, WatchlistState } from './watchlist.reducer';
import { selectLoading, selectRows, selectTickers, selectWatchedSet } from './watchlist.selectors';

function root(watchlist: Partial<WatchlistState>) {
  return { watchlist: { ...initialState, ...watchlist }, search: searchInitial, run: runInitial };
}

describe('watchlist selectors', () => {
  const base = adapter.setAll([item('AAPL', 1), item('MSFT', 2, true)], initialState);
  const state = root({
    ...base,
    quotes: { AAPL: { data: summary(190.5, 1.25, -3.5), error: null, fetchedAt: 1 } },
    ratings: { AAPL: { rating: 'BUY', conviction: 0.6, issuedOn: '2026-11-01' } },
  });

  it('joins entities, quotes and ratings into rows', () => {
    expect(selectRows(state)).toEqual([
      {
        ticker: 'AAPL',
        pending: false,
        addedAt: 1,
        lastClose: 190.5,
        change1d: 1.25,
        change1m: -3.5,
        asOf: '2026-11-07',
        quoteError: null,
        quoteLoading: false,
        rating: 'BUY',
        conviction: 0.6,
        ratedOn: '2026-11-01',
      },
      {
        ticker: 'MSFT',
        pending: true,
        addedAt: 2,
        lastClose: null,
        change1d: null,
        change1m: null,
        asOf: null,
        quoteError: null,
        quoteLoading: true,
        rating: null,
        conviction: null,
        ratedOn: null,
      },
    ]);
  });

  it('is memoized: unrelated state changes return the same array', () => {
    const first = selectRows(state);
    const searched = { ...state, search: { ...searchInitial, query: 'nv' } };
    expect(selectRows(searched)).toBe(first);
    const repriced = root({ ...state.watchlist, quotes: { AAPL: { data: summary(200), error: null, fetchedAt: 2 } } });
    expect(selectRows(repriced)).not.toBe(first);
  });

  it('projector works on plain inputs', () => {
    const rows = selectRows.projector([item('X', 1)], {}, {});
    expect(rows[0]).toMatchObject({ ticker: 'X', quoteLoading: true, rating: null });
  });

  it('exposes tickers, a watched set and loading', () => {
    expect(selectTickers(state)).toEqual(['AAPL', 'MSFT']);
    expect(selectWatchedSet(state).has('MSFT')).toBe(true);
    expect(selectLoading(root({ loading: true }))).toBe(true);
  });
});
