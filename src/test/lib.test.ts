import { describe, expect, it, vi } from 'vitest';
import { citationId, linkCitations } from '@/lib/citations';
import { buildChartRows, nextBusinessDays, yDomain } from '@/lib/cone';
import { frac, money, pct, ratingLabel, ratingTone, shortDate, timeAgo } from '@/lib/format';
import { SseParser, streamSse } from '@/lib/sse';
import type { Bar, ConeStep } from '@/lib/types';

describe('SseParser', () => {
  it('parses complete events and ignores comments/pings', () => {
    const p = new SseParser();
    const out = p.push(': ping\n\nevent: trace\ndata: {"a":1}\n\nevent: result\ndata: {"b":2}\n\n');
    expect(out).toEqual([
      { event: 'trace', data: '{"a":1}' },
      { event: 'result', data: '{"b":2}' },
    ]);
  });

  it('reassembles events split across arbitrary chunk boundaries', () => {
    const p = new SseParser();
    const msgs = [
      ...p.push('event: tra'),
      ...p.push('ce\ndata: {"x"'),
      ...p.push(':1}\n'),
      ...p.push('\nevent: error\r\ndata: boom\r\n\r\n'),
    ];
    expect(msgs).toEqual([
      { event: 'trace', data: '{"x":1}' },
      { event: 'error', data: 'boom' },
    ]);
  });

  it('joins multi-line data and defaults the event name', () => {
    const p = new SseParser();
    expect(p.push('data: line1\ndata: line2\n\n')).toEqual([{ event: 'message', data: 'line1\nline2' }]);
  });

  it('does not emit a partial event until the blank line arrives', () => {
    const p = new SseParser();
    expect(p.push('event: trace\ndata: {"half":')).toEqual([]);
    expect(p.push('1}\n\n')).toHaveLength(1);
  });
});

describe('streamSse', () => {
  const streamOf = (chunks: string[]) =>
    new ReadableStream<Uint8Array>({
      start(c) {
        const enc = new TextEncoder();
        chunks.forEach(ch => c.enqueue(enc.encode(ch)));
        c.close();
      },
    });

  it('POSTs the body and delivers messages as they stream in', async () => {
    const fetchImpl = vi.fn(async () => new Response(streamOf(['event: trace\ndata: 1\n\n', 'event: result\nda', 'ta: 2\n\n']), { status: 200 }));
    const got: string[] = [];
    await streamSse({ url: '/x', body: { ticker: 'AAPL' }, headers: { Authorization: 'Bearer t' }, onMessage: m => got.push(`${m.event}:${m.data}`), fetchImpl: fetchImpl as unknown as typeof fetch });
    expect(got).toEqual(['trace:1', 'result:2']);
    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.method).toBe('POST');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer t');
    expect(JSON.parse(init.body as string)).toEqual({ ticker: 'AAPL' });
  });

  it('rejects with the server error message on a non-2xx response', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ detail: 'Rate limit reached' }), { status: 429, statusText: 'Too Many' }));
    await expect(streamSse({ url: '/x', body: {}, onMessage: () => {}, fetchImpl: fetchImpl as unknown as typeof fetch })).rejects.toThrow('Rate limit reached');
  });
});

describe('citations', () => {
  it('links bare evidence markers but leaves existing links alone', () => {
    expect(linkCitations('Revenue grew 6.4% [T8] and margin held [T2].')).toBe('Revenue grew 6.4% [T8](#ev-T8) and margin held [T2](#ev-T2).');
    expect(linkCitations('See [T3](https://x.test)')).toBe('See [T3](https://x.test)');
    expect(linkCitations('no markers [here]')).toBe('no markers [here]');
  });

  it('extracts the evidence id from a chip href', () => {
    expect(citationId('#ev-T12')).toBe('T12');
    expect(citationId('https://example.com')).toBeNull();
    expect(citationId(undefined)).toBeNull();
  });
});

describe('forecast cone chart data', () => {
  const bars: Bar[] = [
    { date: '2026-10-08', open: 100, high: 101, low: 99, close: 100, volume: 1 },
    { date: '2026-10-09', open: 100, high: 103, low: 99, close: 102, volume: 1 }, // a Friday
  ];
  const cone: ConeStep[] = [
    { step: 1, p10: 98, p25: 100, p50: 102, p75: 104, p90: 106 },
    { step: 2, p10: 96, p25: 99, p50: 102, p75: 105, p90: 108 },
  ];

  it('skips weekends when projecting dates', () => {
    expect(nextBusinessDays('2026-10-09', 3)).toEqual(['2026-10-12', '2026-10-13', '2026-10-14']);
  });

  it('anchors the cone on the last close and fans out from it', () => {
    const rows = buildChartRows(bars, cone);
    expect(rows).toHaveLength(4);
    expect(rows[1].band80).toEqual([102, 102]); // anchor: zero width at the last price
    expect(rows[2]).toMatchObject({ date: '2026-10-12', median: 102, band80: [98, 106], band50: [100, 104] });
    expect(rows[3].price).toBeUndefined();
  });

  it('returns plain price rows without a cone and a padded domain including the bands', () => {
    expect(buildChartRows(bars)).toEqual([{ date: '2026-10-08', price: 100 }, { date: '2026-10-09', price: 102 }]);
    const [lo, hi] = yDomain(buildChartRows(bars, cone));
    expect(lo).toBeLessThan(96);
    expect(hi).toBeGreaterThan(108);
  });
});

describe('format helpers', () => {
  it('formats money, percents and fractions defensively', () => {
    expect(money(1234.5)).toBe('$1,234.50');
    expect(money(null)).toBe('n/a');
    expect(pct(6.42, 1, true)).toBe('+6.4%');
    expect(pct(-2.06, 1, true)).toBe('-2.1%');
    expect(frac(0.153, 0)).toBe('15%');
    expect(frac(undefined)).toBe('n/a');
  });

  it('maps ratings to tones and renders relative times', () => {
    expect(ratingTone('STRONG_BUY')).toBe('gain');
    expect(ratingTone('SELL')).toBe('loss');
    expect(ratingTone('HOLD')).toBe('warn');
    expect(ratingTone('NO_CALL')).toBe('neutral');
    expect(ratingLabel('STRONG_BUY')).toBe('Strong buy');
    expect(timeAgo(1000, 1000_000 + 30_000)).toBe('30s ago');
    expect(timeAgo(1000, (1000 + 7200) * 1000)).toBe('2h ago');
    expect(shortDate('2026-10-12')).toBe('12 Oct 2026');
    expect(shortDate(null)).toBe('n/a');
  });
});
