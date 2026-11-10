import { defaultMemoize } from '@ngrx/store';
import { Rating } from '../core/models';
import { WatchRow } from './state/watchlist.selectors';

export type SortKey = 'added' | 'ticker' | 'change1d' | 'change1m' | 'rating';

export const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'added', label: 'Date added' },
  { key: 'ticker', label: 'Ticker' },
  { key: 'change1d', label: '1 day change' },
  { key: 'change1m', label: '1 month change' },
  { key: 'rating', label: 'Rating' },
];

const RATING_ORDER: Record<Rating, number> = { STRONG_BUY: 0, BUY: 1, HOLD: 2, SELL: 3, STRONG_SELL: 4, NO_CALL: 5 };

/** Ascending compare with nulls last, whatever the direction. */
function byNullable(a: number | null, b: number | null, dir: 1 | -1): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return (a - b) * dir;
}

/** Filter by ticker or rating text, then sort. Pure, so it is easy to test and safe to memoize. */
export function applyView(rows: WatchRow[], filter: string, sort: SortKey): WatchRow[] {
  const q = filter.trim().toUpperCase();
  const kept = q
    ? rows.filter(r => r.ticker.includes(q) || (r.rating ?? '').replace('_', ' ').includes(q))
    : rows.slice();
  const tie = (a: WatchRow, b: WatchRow) => a.ticker.localeCompare(b.ticker);
  const compare: Record<SortKey, (a: WatchRow, b: WatchRow) => number> = {
    added: (a, b) => a.addedAt - b.addedAt,
    ticker: tie,
    change1d: (a, b) => byNullable(a.change1d, b.change1d, -1) || tie(a, b),
    change1m: (a, b) => byNullable(a.change1m, b.change1m, -1) || tie(a, b),
    rating: (a, b) =>
      byNullable(a.rating ? RATING_ORDER[a.rating] : null, b.rating ? RATING_ORDER[b.rating] : null, 1) || tie(a, b),
  };
  return kept.sort(compare[sort]);
}

/** applyView memoized on its last arguments: the same rows, filter and sort return the same array. */
export const visibleRows: typeof applyView = defaultMemoize(applyView).memoized as typeof applyView;
