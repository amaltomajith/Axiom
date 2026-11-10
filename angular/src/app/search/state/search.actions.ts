import { createActionGroup, emptyProps, props } from '@ngrx/store';
import { TickerMatch } from '../../core/models';

export const TickerSearchActions = createActionGroup({
  source: 'Ticker Search',
  events: {
    'Query Changed': props<{ query: string }>(),
  },
});

export const SearchApiActions = createActionGroup({
  source: 'Search API',
  events: {
    'Search Succeeded': props<{ query: string; results: TickerMatch[] }>(),
    'Search Failed': props<{ query: string; error: string }>(),
    'Search Cleared': emptyProps(),
  },
});
