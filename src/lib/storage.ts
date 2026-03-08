export interface WatchlistItem {
  ticker: string;
  addedAt: string;
}

export interface PaperTrade {
  id: string;
  ticker: string;
  entryPrice: number;
  quantity: number;
  entryDate: string;
  type: 'BUY' | 'SHORT';
}

export interface PredictionLog {
  id: string;
  ticker: string;
  date: string;
  targetDate: string;
  predictions: { model: string; price: number }[];
  actualPrice?: number;
  verified?: boolean;
}

const KEYS = {
  watchlist: 'axiom_watchlist',
  trades: 'axiom_trades',
  predictions: 'axiom_predictions',
};

function get<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch { return fallback; }
}

function set(key: string, value: unknown) {
  localStorage.setItem(key, JSON.stringify(value));
}

// Watchlist
export const getWatchlist = (): WatchlistItem[] => get(KEYS.watchlist, []);
export const addToWatchlist = (ticker: string) => {
  const list = getWatchlist();
  if (!list.find(w => w.ticker === ticker)) {
    list.push({ ticker, addedAt: new Date().toISOString() });
    set(KEYS.watchlist, list);
  }
};
export const removeFromWatchlist = (ticker: string) => {
  set(KEYS.watchlist, getWatchlist().filter(w => w.ticker !== ticker));
};

// Paper trades
export const getTrades = (): PaperTrade[] => get(KEYS.trades, []);
export const addTrade = (trade: Omit<PaperTrade, 'id'>) => {
  const trades = getTrades();
  trades.push({ ...trade, id: crypto.randomUUID() });
  set(KEYS.trades, trades);
};
export const removeTrade = (id: string) => {
  set(KEYS.trades, getTrades().filter(t => t.id !== id));
};

// Prediction history
export const getPredictionLogs = (): PredictionLog[] => get(KEYS.predictions, []);
export const addPredictionLog = (log: Omit<PredictionLog, 'id'>) => {
  const logs = getPredictionLogs();
  logs.push({ ...log, id: crypto.randomUUID() });
  set(KEYS.predictions, logs);
};
export const updatePredictionLog = (id: string, update: Partial<PredictionLog>) => {
  const logs = getPredictionLogs().map(l => l.id === id ? { ...l, ...update } : l);
  set(KEYS.predictions, logs);
};
