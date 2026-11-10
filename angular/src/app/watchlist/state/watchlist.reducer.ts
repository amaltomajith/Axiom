import { createEntityAdapter, EntityState } from '@ngrx/entity';
import { createFeature, createReducer, on } from '@ngrx/store';
import { PriceSummary, RatingInfo, WatchItem } from '../../core/models';
import { QuotesApiActions, RatingsApiActions, WatchlistApiActions, WatchlistPageActions } from './watchlist.actions';

export interface QuoteState {
  data: PriceSummary | null;
  error: string | null;
  fetchedAt: number | null;
}

export interface Notice {
  tone: 'error' | 'info';
  text: string;
}

export interface WatchlistState extends EntityState<WatchItem> {
  quotes: Record<string, QuoteState>;
  ratings: Record<string, RatingInfo>;
  ratingsError: string | null;
  /** optimistic removals waiting for the API: the rollback source */
  removed: Record<string, WatchItem>;
  loading: boolean;
  loaded: boolean;
  error: string | null;
  notice: Notice | null;
}

export const adapter = createEntityAdapter<WatchItem>({
  selectId: item => item.ticker,
  sortComparer: (a, b) => a.added_at - b.added_at,
});

export const initialState: WatchlistState = adapter.getInitialState({
  quotes: {},
  ratings: {},
  ratingsError: null,
  removed: {},
  loading: false,
  loaded: false,
  error: null,
  notice: null,
});

function omit<T>(record: Record<string, T>, key: string): Record<string, T> {
  const next = { ...record };
  delete next[key];
  return next;
}

export const reducer = createReducer(
  initialState,
  on(WatchlistPageActions.opened, (s): WatchlistState => ({ ...s, loading: !s.loaded, error: null })),
  on(WatchlistApiActions.loadSucceeded, (s, { items }): WatchlistState => {
    // the server list wins, but keep optimistic changes that are still in flight
    const pending = Object.values(s.entities).filter((e): e is WatchItem => !!e?.pending);
    const kept = items.filter(i => !s.removed[i.ticker]).map(i => ({ ticker: i.ticker, added_at: i.added_at }));
    return adapter.addMany(pending, adapter.setAll(kept, { ...s, loading: false, loaded: true, error: null }));
  }),
  on(WatchlistApiActions.loadFailed, (s, { error }): WatchlistState => ({ ...s, loading: false, error })),

  // optimistic add: show the row now, marked pending
  on(WatchlistPageActions.addRequested, (s, { ticker, requestedAt }): WatchlistState =>
    s.entities[ticker] ? s : adapter.addOne({ ticker, added_at: requestedAt, pending: true }, { ...s, notice: null }),
  ),
  on(WatchlistApiActions.addSucceeded, (s, { ticker, item }): WatchlistState =>
    s.entities[ticker] ? adapter.setOne({ ticker, added_at: item.added_at }, s) : s,
  ),
  // rollback: remove the row only if it is still the optimistic one (never a row the user already had)
  on(WatchlistApiActions.addFailed, (s, { ticker, error }): WatchlistState => ({
    ...(s.entities[ticker]?.pending ? adapter.removeOne(ticker, s) : s),
    notice: { tone: 'error', text: `Could not add ${ticker}: ${error}` },
  })),

  // optimistic remove: stash the row so a failure can put it back exactly
  on(WatchlistPageActions.removeRequested, (s, { ticker }): WatchlistState => {
    const item = s.entities[ticker];
    if (!item) return s;
    return adapter.removeOne(ticker, { ...s, removed: { ...s.removed, [ticker]: item }, notice: null });
  }),
  on(WatchlistApiActions.removeSucceeded, (s, { ticker }): WatchlistState => ({
    ...s,
    removed: omit(s.removed, ticker),
    quotes: s.entities[ticker] ? s.quotes : omit(s.quotes, ticker),
  })),
  on(WatchlistApiActions.removeFailed, (s, { ticker, error }): WatchlistState => {
    const item = s.removed[ticker];
    const next: WatchlistState = {
      ...s,
      removed: omit(s.removed, ticker),
      notice: { tone: 'error', text: `Could not remove ${ticker}: ${error}` },
    };
    return item && !s.entities[ticker] ? adapter.addOne(item, next) : next;
  }),
  on(WatchlistPageActions.noticeDismissed, (s): WatchlistState => ({ ...s, notice: null })),

  on(QuotesApiActions.refreshSucceeded, (s, { ticker, quote, fetchedAt }): WatchlistState =>
    s.entities[ticker] ? { ...s, quotes: { ...s.quotes, [ticker]: { data: quote, error: null, fetchedAt } } } : s,
  ),
  on(QuotesApiActions.refreshFailed, (s, { ticker, error }): WatchlistState => {
    if (!s.entities[ticker]) return s;
    const prev = s.quotes[ticker];
    // keep the last good price on screen, with the error beside it
    return { ...s, quotes: { ...s.quotes, [ticker]: { data: prev?.data ?? null, error, fetchedAt: prev?.fetchedAt ?? null } } };
  }),
  on(RatingsApiActions.refreshSucceeded, (s, { ratings }): WatchlistState => ({ ...s, ratings, ratingsError: null })),
  on(RatingsApiActions.refreshFailed, (s, { error }): WatchlistState => ({ ...s, ratingsError: error })),
);

export const watchlistFeature = createFeature({ name: 'watchlist', reducer });
