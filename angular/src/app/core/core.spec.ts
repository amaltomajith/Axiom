import { HttpErrorResponse } from '@angular/common/http';
import { apiErrorMessage } from './api.service';
import { backoffDelay } from './backoff';
import { DEFAULT_API_BASE, loadApiBase } from './config';
import { formatPct, formatPrice, ratingLabel, ratingTone } from './format';
import { visitorId } from './visitor';

function memoryStorage(initial: Record<string, string> = {}): Storage {
  const data = new Map(Object.entries(initial));
  return {
    getItem: k => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: k => void data.delete(k),
    clear: () => data.clear(),
    key: i => [...data.keys()][i] ?? null,
    get length() {
      return data.size;
    },
  };
}

describe('backoffDelay', () => {
  it('doubles per attempt, is capped, and jitters within 20%', () => {
    const mid = () => 0.5;
    expect([1, 2, 3, 4, 5].map(n => backoffDelay(n, 1000, 8000, mid))).toEqual([1000, 2000, 4000, 8000, 8000]);
    expect(backoffDelay(1, 1000, 8000, () => 0)).toBe(800);
    expect(backoffDelay(1, 1000, 8000, () => 1)).toBe(1200);
  });
});

describe('visitorId', () => {
  it('creates an id once and reuses it', () => {
    const storage = memoryStorage();
    const id = visitorId(storage, () => 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee');
    expect(visitorId(storage, () => 'ffffffff-ffff-ffff-ffff-ffffffffffff')).toBe(id);
  });

  it('replaces a malformed saved id and survives storage that throws', () => {
    expect(visitorId(memoryStorage({ axiom_watch_visitor: 'bad id' }), () => 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')).toBe(
      'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
    );
    const broken = {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      },
    } as unknown as Storage;
    expect(visitorId(broken, () => 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')).toBe('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee');
  });
});

describe('loadApiBase', () => {
  const respond = (body: unknown, ok = true) => (() => Promise.resolve({ ok, json: () => Promise.resolve(body) })) as unknown as typeof fetch;

  it('reads apiBase from config.json and trims a trailing slash', async () => {
    expect(await loadApiBase(respond({ apiBase: 'https://api.example/' }))).toBe('https://api.example');
  });

  it('falls back to the local API when the file is missing or wrong', async () => {
    expect(await loadApiBase(respond({}, false))).toBe(DEFAULT_API_BASE);
    expect(await loadApiBase(respond({ apiBase: 42 }))).toBe(DEFAULT_API_BASE);
    expect(await loadApiBase((() => Promise.reject(new Error('offline'))) as unknown as typeof fetch)).toBe(DEFAULT_API_BASE);
  });
});

describe('apiErrorMessage', () => {
  it('prefers the backend detail or error, then a plain message', () => {
    expect(apiErrorMessage(new HttpErrorResponse({ status: 409, error: { detail: 'Your watchlist is full (25 tickers).' } }))).toBe(
      'Your watchlist is full (25 tickers).',
    );
    expect(apiErrorMessage(new HttpErrorResponse({ status: 400, error: { error: 'Invalid ticker' } }))).toBe('Invalid ticker');
    expect(apiErrorMessage(new HttpErrorResponse({ status: 0 }))).toBe('Cannot reach the Axiom API.');
    expect(apiErrorMessage(new HttpErrorResponse({ status: 500, error: 'oops' }))).toBe('The API answered 500.');
  });
});

describe('format', () => {
  it('formats prices, signed percentages and ratings', () => {
    expect(formatPrice(1234.5)).toBe('$1,234.50');
    expect(formatPrice(null)).toBe('n/a');
    expect(formatPct(1.234)).toBe('+1.23%');
    expect(formatPct(-0.5)).toBe('-0.50%');
    expect(formatPct(null)).toBe('n/a');
    expect(ratingLabel('STRONG_BUY')).toBe('Strong buy');
    expect(ratingLabel(null)).toBe('Not rated');
    expect([ratingTone('BUY'), ratingTone('SELL'), ratingTone('HOLD'), ratingTone('NO_CALL')]).toEqual(['buy', 'sell', 'hold', '']);
  });
});
