const NA = 'n/a';

export const money = (v: number | null | undefined, digits = 2): string =>
  v == null || Number.isNaN(v) ? NA : `$${v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;

export const pct = (v: number | null | undefined, digits = 1, signed = false): string => {
  if (v == null || Number.isNaN(v)) return NA;
  const s = v.toFixed(digits);
  return `${signed && v > 0 ? '+' : ''}${s}%`;
};

/** Fractions (0.123) as percent text. */
export const frac = (v: number | null | undefined, digits = 1, signed = false): string =>
  v == null ? NA : pct(v * 100, digits, signed);

export const num = (v: number | null | undefined, digits = 2): string =>
  v == null || Number.isNaN(v) ? NA : v.toFixed(digits);

/** "STRONG_BUY" -> "Strong buy" */
export const ratingLabel = (r: string): string => {
  const s = r.replace(/_/g, ' ').toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
};

export type Tone = 'gain' | 'loss' | 'warn' | 'neutral';

export function ratingTone(r: string): Tone {
  if (r === 'BUY' || r === 'STRONG_BUY') return 'gain';
  if (r === 'SELL' || r === 'STRONG_SELL') return 'loss';
  if (r === 'HOLD') return 'warn';
  return 'neutral';
}

export const TONE_TEXT: Record<Tone, string> = {
  gain: 'text-success',
  loss: 'text-destructive',
  warn: 'text-warning',
  neutral: 'text-muted-foreground',
};

export const TONE_BG: Record<Tone, string> = {
  gain: 'bg-success',
  loss: 'bg-destructive',
  warn: 'bg-warning',
  neutral: 'bg-muted-foreground',
};

export function timeAgo(epochSeconds: number, now = Date.now()): string {
  const s = Math.max(0, Math.round(now / 1000 - epochSeconds));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

/** "2026-10-12" -> "12 Oct 2026" */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return NA;
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? NA : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
}
