import type {
  ActionPlan,
  ApiStatus,
  BacktestReport,
  BacktestResponse,
  CalibrationResponse,
  ChainCheck,
  DeskRun,
  DeskRunBrief,
  DeskStatus,
  EquityPoint,
  ForecastResponse,
  Health,
  IndicatorsResponse,
  JournalEntry,
  NewsResponse,
  OhlcvResponse,
  PaperTrade,
  RedteamResult,
  RegimeResponse,
  ReplayJob,
  Scenario,
  Scorecard,
  Thesis,
  TradeContract,
  TraderPosition,
  TraderStatus,
  WatchItem,
} from './types';

// `npm run build:selfhost` builds for the one-port demo where FastAPI serves this bundle: the API is same-origin.
export const API_BASE: string = import.meta.env.MODE === 'selfhost' ? '' : ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000');
const TOKEN_KEY = 'axiom_token';

/** True when this bundle is served by the API itself to a visitor on another machine (the public demo link). */
export const PUBLIC_DEMO: boolean = API_BASE === '' && typeof window !== 'undefined' && !['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname);

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
    throw new ApiError(
      PUBLIC_DEMO
        ? 'The demo laptop is reconnecting. Reload in a minute, or open the Axiom link you were given again.'
        : `Cannot reach the Axiom backend at ${API_BASE || window.location.origin}. Is it running?`,
      0,
    );
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
  status: () => request<ApiStatus>('/api/status'),
  ohlcv: (t: string, bars = 90) => cachedGet<OhlcvResponse>(`/api/market/${enc(t)}/ohlcv?bars=${bars}`),
  indicators: (t: string) => cachedGet<IndicatorsResponse>(`/api/quant/${enc(t)}/indicators`),
  regime: (t: string) => cachedGet<RegimeResponse>(`/api/quant/${enc(t)}/regime`),
  forecast: (t: string, horizon = 14) => cachedGet<ForecastResponse>(`/api/quant/${enc(t)}/forecast?horizon=${horizon}`),
  backtest: (t: string, strategy: string) => cachedGet<BacktestResponse>(`/api/quant/${enc(t)}/backtest?strategy=${enc(strategy)}`),
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

const post = <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });
const sess = (session: string) => `session=${enc(session)}`;

/** The Autopilot paper trader. Reads are public; every POST needs the API token (or a direct local request). */
export const trader = {
  status: () => request<TraderStatus>('/api/trader/status'),
  positions: () => request<TraderPosition[]>('/api/trader/positions'),
  journal: (session = 'live', limit = 200) => request<JournalEntry[]>(`/api/trader/journal?${sess(session)}&limit=${limit}`),
  verify: (session = 'live') => request<ChainCheck>(`/api/trader/journal/verify?${sess(session)}`),
  contracts: (session = 'live') => request<TradeContract[]>(`/api/trader/contracts?${sess(session)}`),
  calibration: (session = 'live') => request<CalibrationResponse>(`/api/trader/calibration?${sess(session)}`),
  equity: (session = 'live') => request<EquityPoint[]>(`/api/trader/equity?${sess(session)}&limit=5000`),
  report: () => request<BacktestReport>('/api/trader/backtest/report'),
  replays: () => request<ReplayJob[]>('/api/trader/replays'),
  scenarios: () => request<Scenario[]>('/api/trader/scenarios'),
  desk: () => request<DeskStatus>('/api/trader/desk'),
  deskRuns: () => request<DeskRunBrief[]>('/api/trader/desk/runs'),
  deskRun: (id: string) => request<DeskRun>(`/api/trader/desk/runs/${enc(id)}`),
  deskRecorded: () => request<DeskRun>('/api/trader/desk/recorded'),

  kill: (reason: string) => post<{ ok: boolean; closed: number }>('/api/trader/kill', { reason }),
  resume: () => post<{ ok: boolean }>('/api/trader/resume'),
  start: () => post<{ ok: boolean }>('/api/trader/start'),
  stop: () => post<{ ok: boolean }>('/api/trader/stop'),
  setAutonomy: (level: string, lock = true) => post<{ ok: boolean; autonomy: string }>('/api/trader/autonomy', { level, lock }),
  approve: (id: string) => post<{ ok: boolean; reason?: string }>(`/api/trader/orders/${enc(id)}/approve`),
  reject: (id: string) => post<{ ok: boolean }>(`/api/trader/orders/${enc(id)}/reject`),
  replay: (bars: number, delay: number, scenario?: string) => post<ReplayJob>('/api/trader/replay', scenario ? { delay, scenario } : { bars, delay }),
  stopReplay: (id: string) => post<ReplayJob>(`/api/trader/replays/${enc(id)}/stop`),
  redteam: () => post<RedteamResult>('/api/trader/redteam'),
  reviewNow: (symbol: string) => post<{ ok: boolean; symbol: string; strategy: string | null; runs_left: number | null }>('/api/trader/desk/review', { symbol }),
  streamUrl: (session = 'live') => `${API_BASE}/api/trader/stream?${sess(session)}`,
};

export const POPULAR_TICKERS = ['AAPL', 'TSLA', 'NVDA', 'MSFT', 'AMZN', 'GOOGL'];
