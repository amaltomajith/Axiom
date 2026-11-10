import { createActionGroup, emptyProps, props } from '@ngrx/store';
import { PriceSummary, RatingInfo, WatchItem } from '../../core/models';

export const WatchlistPageActions = createActionGroup({
  source: 'Watchlist Page',
  events: {
    Opened: emptyProps(),
    /** `requestedAt` (epoch seconds) is passed in so the reducer stays pure */
    'Add Requested': props<{ ticker: string; requestedAt: number }>(),
    'Remove Requested': props<{ ticker: string }>(),
    'Notice Dismissed': emptyProps(),
  },
});

export const WatchlistApiActions = createActionGroup({
  source: 'Watchlist API',
  events: {
    'Load Succeeded': props<{ items: WatchItem[] }>(),
    'Load Failed': props<{ error: string }>(),
    'Add Succeeded': props<{ ticker: string; item: WatchItem }>(),
    'Add Failed': props<{ ticker: string; error: string }>(),
    'Remove Succeeded': props<{ ticker: string }>(),
    'Remove Failed': props<{ ticker: string; error: string }>(),
  },
});

export const QuotesApiActions = createActionGroup({
  source: 'Quotes API',
  events: {
    'Refresh Succeeded': props<{ ticker: string; quote: PriceSummary; fetchedAt: number }>(),
    'Refresh Failed': props<{ ticker: string; error: string }>(),
  },
});

export const RatingsApiActions = createActionGroup({
  source: 'Ratings API',
  events: {
    'Refresh Succeeded': props<{ ratings: Record<string, RatingInfo> }>(),
    'Refresh Failed': props<{ error: string }>(),
  },
});
