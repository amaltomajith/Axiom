import { createSelector } from '@ngrx/store';
import { Rating } from '../../core/models';
import { adapter, watchlistFeature } from './watchlist.reducer';

export interface WatchRow {
  ticker: string;
  pending: boolean;
  addedAt: number;
  lastClose: number | null;
  change1d: number | null;
  change1m: number | null;
  asOf: string | null;
  quoteError: string | null;
  quoteLoading: boolean;
  rating: Rating | null;
  conviction: number | null;
  ratedOn: string | null;
}

const { selectAll } = adapter.getSelectors();

export const selectItems = createSelector(watchlistFeature.selectWatchlistState, selectAll);

export const selectTickers = createSelector(selectItems, items => items.map(i => i.ticker));

export const selectWatchedSet = createSelector(selectTickers, tickers => new Set(tickers));

/** The table's rows: entities joined with quotes and ratings. Recomputed only when one of the three changes. */
export const selectRows = createSelector(
  selectItems,
  watchlistFeature.selectQuotes,
  watchlistFeature.selectRatings,
  (items, quotes, ratings): WatchRow[] =>
    items.map(item => {
      const quote = quotes[item.ticker];
      const rating = ratings[item.ticker];
      return {
        ticker: item.ticker,
        pending: !!item.pending,
        addedAt: item.added_at,
        lastClose: quote?.data?.last_close ?? null,
        change1d: quote?.data?.returns_pct['1d'] ?? null,
        change1m: quote?.data?.returns_pct['1m'] ?? null,
        asOf: quote?.data?.meta.as_of ?? null,
        quoteError: quote?.error ?? null,
        quoteLoading: !quote,
        rating: rating?.rating ?? null,
        conviction: rating?.conviction ?? null,
        ratedOn: rating?.issuedOn ?? null,
      };
    }),
);

export const selectLoading = watchlistFeature.selectLoading;
export const selectLoaded = watchlistFeature.selectLoaded;
export const selectError = watchlistFeature.selectError;
export const selectNotice = watchlistFeature.selectNotice;
export const selectRatingsError = watchlistFeature.selectRatingsError;
