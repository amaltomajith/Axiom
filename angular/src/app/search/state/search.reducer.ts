import { createFeature, createReducer, createSelector, on } from '@ngrx/store';
import { TickerMatch } from '../../core/models';
import { SearchApiActions, TickerSearchActions } from './search.actions';

export interface SearchState {
  /** what is in the box right now */
  query: string;
  /** the query the current results (or error) belong to */
  answered: string | null;
  results: TickerMatch[];
  error: string | null;
}

export const initialState: SearchState = { query: '', answered: null, results: [], error: null };

export const searchFeature = createFeature({
  name: 'search',
  reducer: createReducer(
    initialState,
    on(TickerSearchActions.queryChanged, (s, { query }): SearchState => ({ ...s, query })),
    on(SearchApiActions.searchSucceeded, (s, { query, results }): SearchState => ({ ...s, answered: query, results, error: null })),
    on(SearchApiActions.searchFailed, (s, { query, error }): SearchState => ({ ...s, answered: query, results: [], error })),
    on(SearchApiActions.searchCleared, (s): SearchState => ({ ...s, answered: '', results: [], error: null })),
  ),
  extraSelectors: ({ selectQuery, selectAnswered }) => ({
    /**
     * Derived, not stored: the box holds a query the results do not answer yet. A stored `loading` flag would
     * stick when distinctUntilChanged drops a repeat query (typing "NV", "NVD", back to "NV").
     */
    selectPending: createSelector(selectQuery, selectAnswered, (q, answered) => q.trim() !== '' && q.trim() !== answered),
  }),
});
