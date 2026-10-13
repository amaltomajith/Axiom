const KEY = 'axiom_recent';
const MAX = 6;

/** Recently viewed tickers. Browser storage can be unavailable (private mode), so every access is guarded. */
export function getRecent(): string[] {
  try {
    const raw = localStorage.getItem(KEY);
    const list = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(list) ? list.filter((x): x is string => typeof x === 'string').slice(0, MAX) : [];
  } catch {
    return [];
  }
}

export function pushRecent(ticker: string): string[] {
  const next = [ticker, ...getRecent().filter(t => t !== ticker)].slice(0, MAX);
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* not persisted; the in-memory list still works for this session */
  }
  return next;
}
