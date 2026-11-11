import { InjectionToken } from '@angular/core';

/** Base URL of the Axiom API, without a trailing slash. */
export const API_BASE = new InjectionToken<string>('API_BASE');

/** The Axiom hub page (in the React app), which lists every part of the project. */
export const HUB_URL = new InjectionToken<string>('HUB_URL');

export const DEFAULT_API_BASE = 'http://localhost:8000';
export const DEFAULT_HUB_URL = 'https://axiom-ten-henna.vercel.app/hub';

export interface RuntimeConfig {
  apiBase: string;
  hubUrl: string;
}

const url = (v: unknown): string | null =>
  typeof v === 'string' && /^https?:\/\//.test(v.trim()) ? v.trim().replace(/\/+$/, '') : null;

/**
 * Reads `config.json` (served next to index.html) before the app boots, so one build can point at any API:
 * Vercel ships a static file, the Docker image writes it from `AXIOM_API_BASE` when the container starts.
 * Anything missing or malformed falls back to the defaults (local API, live hub).
 */
export async function loadConfig(fetchImpl: typeof fetch = fetch): Promise<RuntimeConfig> {
  let body: { apiBase?: unknown; hubUrl?: unknown } = {};
  try {
    const res = await fetchImpl('config.json', { cache: 'no-store' });
    if (res.ok) body = (await res.json()) as typeof body;
  } catch {
    /* no config file or not JSON: use the defaults */
  }
  return { apiBase: url(body.apiBase) ?? DEFAULT_API_BASE, hubUrl: url(body.hubUrl) ?? DEFAULT_HUB_URL };
}
