import { WatchRow } from './state/watchlist.selectors';
import { applyView, visibleRows } from './view';
import { latestRatings } from './ratings';

const row = (ticker: string, over: Partial<WatchRow> = {}): WatchRow => ({
  ticker,
  pending: false,
  addedAt: 0,
  lastClose: null,
  change1d: null,
  change1m: null,
  asOf: null,
  quoteError: null,
  quoteLoading: false,
  rating: null,
  conviction: null,
  ratedOn: null,
  ...over,
});

const rows = [
  row('MSFT', { addedAt: 1, change1d: -1, change1m: 4, rating: 'HOLD' }),
  row('AAPL', { addedAt: 2, change1d: 2, change1m: null, rating: 'STRONG_BUY' }),
  row('NVDA', { addedAt: 3, change1d: null, change1m: 9, rating: null }),
  row('AMD', { addedAt: 4, change1d: 0.5, change1m: -2, rating: 'SELL' }),
];
const order = (r: WatchRow[]) => r.map(x => x.ticker);

describe('applyView', () => {
  it('sorts by each key, with missing values last', () => {
    expect(order(applyView(rows, '', 'added'))).toEqual(['MSFT', 'AAPL', 'NVDA', 'AMD']);
    expect(order(applyView(rows, '', 'ticker'))).toEqual(['AAPL', 'AMD', 'MSFT', 'NVDA']);
    expect(order(applyView(rows, '', 'change1d'))).toEqual(['AAPL', 'AMD', 'MSFT', 'NVDA']);
    expect(order(applyView(rows, '', 'change1m'))).toEqual(['NVDA', 'MSFT', 'AMD', 'AAPL']);
    expect(order(applyView(rows, '', 'rating'))).toEqual(['AAPL', 'MSFT', 'AMD', 'NVDA']);
  });

  it('filters by ticker or rating text, case-insensitively', () => {
    expect(order(applyView(rows, ' a', 'ticker'))).toEqual(['AAPL', 'AMD', 'NVDA']);
    expect(order(applyView(rows, 'strong buy', 'added'))).toEqual(['AAPL']);
    expect(order(applyView(rows, 'hold', 'added'))).toEqual(['MSFT']);
    expect(applyView(rows, 'zzz', 'added')).toEqual([]);
  });

  it('never mutates its input', () => {
    const copy = rows.slice();
    applyView(rows, '', 'ticker');
    expect(rows).toEqual(copy);
  });

  it('visibleRows is memoized on its arguments', () => {
    const a = visibleRows(rows, 'a', 'ticker');
    expect(visibleRows(rows, 'a', 'ticker')).toBe(a);
    expect(visibleRows(rows, 'am', 'ticker')).not.toBe(a);
  });
});

describe('latestRatings', () => {
  it('keeps the first (newest) thesis per ticker', () => {
    const t = (ticker: string, rating: 'BUY' | 'SELL', issue_date: string) => ({
      id: issue_date,
      run_id: 'r',
      ticker,
      created_at: 0,
      issue_date,
      rating,
      conviction: 0.5,
    });
    expect(latestRatings([t('AAPL', 'SELL', '2026-11-05'), t('AAPL', 'BUY', '2026-10-01'), t('MSFT', 'BUY', '2026-11-01')])).toEqual({
      AAPL: { rating: 'SELL', conviction: 0.5, issuedOn: '2026-11-05' },
      MSFT: { rating: 'BUY', conviction: 0.5, issuedOn: '2026-11-01' },
    });
  });
});
