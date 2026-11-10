import { InjectionToken } from '@angular/core';

/** Daily bars change slowly and the market data is free-tier: five minutes between refreshes is plenty. */
export const QUOTE_REFRESH_MS = new InjectionToken<number>('QUOTE_REFRESH_MS', {
  providedIn: 'root',
  factory: () => 5 * 60_000,
});

/** Parallel summary requests per refresh. */
export const QUOTE_CONCURRENCY = 2;

