import { InjectionToken } from '@angular/core';

/** Base URL of the Axiom API, without a trailing slash. */
export const API_BASE = new InjectionToken<string>('API_BASE');

export const DEFAULT_API_BASE = 'http://localhost:8000';

/**
 * Reads `config.json` (served next to index.html) before the app boots, so one build can point at any API:
 * Vercel ships a static file, the Docker image writes it from `AXIOM_API_BASE` when the container starts.
 */
export async function loadApiBase(fetchImpl: typeof fetch = fetch): Promise<string> {
  try {
    const res = await fetchImpl('config.json', { cache: 'no-store' });
    if (res.ok) {
      const body = (await res.json()) as { apiBase?: unknown };
      if (typeof body.apiBase === 'string' && body.apiBase.trim()) return body.apiBase.trim().replace(/\/+$/, '');
    }
  } catch {
    /* no config file or not JSON: fall back to the local API */
  }
  return DEFAULT_API_BASE;
}
