import type { Bar, ConeStep } from './types';

/** The next `n` weekdays after `lastDate` (YYYY-MM-DD). Holidays are ignored: the cone is in trading-day steps. */
export function nextBusinessDays(lastDate: string, n: number): string[] {
  const d = new Date(`${lastDate}T00:00:00Z`);
  const out: string[] = [];
  while (out.length < n) {
    d.setUTCDate(d.getUTCDate() + 1);
    const dow = d.getUTCDay();
    if (dow !== 0 && dow !== 6) out.push(d.toISOString().slice(0, 10));
  }
  return out;
}

export interface ChartRow {
  date: string;
  price?: number;
  median?: number;
  band80?: [number, number];
  band50?: [number, number];
}

/** Merge actual closes with the forecast cone. The last real bar anchors the cone so it fans out from the price. */
export function buildChartRows(bars: Bar[], cone?: ConeStep[]): ChartRow[] {
  const rows: ChartRow[] = bars.map(b => ({ date: b.date, price: b.close }));
  if (!cone?.length || !bars.length) return rows;
  const last = bars[bars.length - 1];
  const anchor = rows[rows.length - 1];
  anchor.median = last.close;
  anchor.band80 = [last.close, last.close];
  anchor.band50 = [last.close, last.close];
  const dates = nextBusinessDays(last.date, cone.length);
  cone.forEach((s, i) => {
    rows.push({ date: dates[i], median: s.p50, band80: [s.p10, s.p90], band50: [s.p25, s.p75] });
  });
  return rows;
}

export function yDomain(rows: ChartRow[]): [number, number] {
  const vals: number[] = [];
  for (const r of rows) {
    if (r.price != null) vals.push(r.price);
    if (r.band80) vals.push(...r.band80);
  }
  if (!vals.length) return [0, 1];
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = (hi - lo) * 0.06 || hi * 0.02;
  return [lo - pad, hi + pad];
}
