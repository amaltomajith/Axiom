import { InjectionToken } from '@angular/core';

/**
 * Exponential backoff with jitter: about 1 s, 2 s, 4 s, then capped at 8 s. The jitter (plus or minus 20%) keeps
 * many tabs that lost the API at the same moment from all retrying on the same tick.
 */
export function backoffDelay(attempt: number, baseMs = 1000, maxMs = 8000, random: () => number = Math.random): number {
  const exp = Math.min(maxMs, baseMs * 2 ** Math.max(0, attempt - 1));
  return Math.round(exp * (0.8 + 0.4 * random()));
}

/** Delay in ms before retry number `attempt` (1-based). Tests provide a deterministic one. */
export const BACKOFF = new InjectionToken<(attempt: number) => number>('BACKOFF', {
  providedIn: 'root',
  factory: () => (attempt: number) => backoffDelay(attempt),
});
