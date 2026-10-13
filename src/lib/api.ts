import type {
  ActionPlan,
  BacktestResponse,
  ForecastResponse,
  Health,
  IndicatorsResponse,
  NewsResponse,
  OhlcvResponse,
  PaperTrade,
  RegimeResponse,
  Scorecard,
  Thesis,
  WatchItem,
} from './types';

export const API_BASE: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000';
const TOKEN_KEY = 'axiom_token';

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? '';
  } catch {
    return '';
  }
}

export function setToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable (private mode): the token simply will not persist */
  }
}

export function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

// --- small in-memory TTL cache for GETs (market data is daily bars, so minutes of staleness are fine)
const cache = new Map<string, { at: number; value: unknown }>();
const TTL_MS = 5 * 60 * 1000;

export function clearCache(ticker?: string): void {
  if (!ticker) return cache.clear();
  const needle = `/${ticker.toUpperCase()}/`;
  for (const key of [...cache.keys()]) if (key.toUpperCase().includes(needle)) cache.delete(key);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(`Cannot reach the Axiom backend at ${API_BASE}. Is it running?`, 0);
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = body.error ?? body.detail ?? msg;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(typeof msg === 'string' ? msg : JSON.stringify(msg), res.status);
  }
  return (await res.json()) as T;
}

async function cachedGet<T>(path: string): Promise<T> {
  const hit = cache.get(path);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.value as T;
  const value = await request<T>(path);
  cache.set(path, { at: Date.now(), value });
  return value;
}

const enc = encodeURIComponent;

export const api = {
  health: () => request<Health>('/api/health'),
  ohlcv: (t: string, bars = 90) => cachedGet<OhlcvResponse>(`/api/market/${enc(t)}/ohlcv?bars=${bars}`),
  indicators: (t: string) => cachedGet<IndicatorsResponse>(`/api/quant/${enc(t)}/indicators`),
  regime: (t: string) => cachedGet<RegimeResponse>(`/api/quant/${enc(t)}/regime`),
  forecast: (t: string, horizon = 14) => cachedGet<ForecastResponse>(`/api/quant/${enc(t)}/forecast?horizon=${horizon}`),
  backtest: (t: string, strategy: string) =>
    cachedGet<BacktestResponse>(`/api/quant/${enc(t)}/backtest?strategy=${enc(strategy)}`),
  walkForward: (t: string) => cachedGet<BacktestResponse>(`/api/quant/${enc(t)}/walk-forward`),
  news: (t: string) => cachedGet<NewsResponse>(`/api/news/${enc(t)}`),

  scorecard: () => request<Scorecard>('/api/scorecard'),
  theses: () => request<Thesis[]>('/api/theses?limit=100'),
  scoreNow: () => request<{ scored: number; not_yet_due: number; failed: number }>('/api/score', { method: 'POST' }),

  actions: () => request<ActionPlan[]>('/api/actions'),
  approve: (id: string) => request<ActionPlan>(`/api/actions/${enc(id)}/approve`, { method: 'POST' }),
  retry: (id: string) => request<ActionPlan>(`/api/actions/${enc(id)}/retry`, { method: 'POST' }),
  reject: (id: string) => request<ActionPlan>(`/api/actions/${enc(id)}/reject`, { method: 'POST' }),

  watchlist: () => request<WatchItem[]>('/api/watchlist'),
  watchAdd: (t: string) => request<WatchItem[]>(`/api/watchlist/${enc(t)}`, { method: 'PUT' }),
  watchRemove: (t: string) => request<WatchItem[]>(`/api/watchlist/${enc(t)}`, { method: 'DELETE' }),

  trades: () => request<PaperTrade[]>('/api/trades'),
  buy: (ticker: string, quantity: number) =>
    request<{ id: string; entry_price: number }>('/api/trades', {
      method: 'POST',
      body: JSON.stringify({ ticker, quantity }),
    }),
  closeTrade: (id: string) => request<PaperTrade>(`/api/trades/${enc(id)}/close`, { method: 'POST' }),
  deleteTrade: (id: string) => request<{ ok: boolean }>(`/api/trades/${enc(id)}`, { method: 'DELETE' }),
};

export const POPULAR_TICKERS = ['AAPL', 'TSLA', 'NVDA', 'MSFT', 'AMZN', 'GOOGL'];
