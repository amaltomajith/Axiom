import { Observable, Subscription } from 'rxjs';
import { EventSourceFactory, EventSourceLike } from '../app/core/event-source';
import { PriceSummary, RunResult, TraceEvent, WatchItem } from '../app/core/models';

/** Records what the code under test does to its EventSource: listeners, onerror, close(). */
export class FakeEventSource implements EventSourceLike {
  readyState = 0;
  closed = false;
  onerror: ((ev: Event) => unknown) | null = null;
  readonly listeners = new Map<string, Set<(ev: MessageEvent) => void>>();

  constructor(readonly url: string) {}

  addEventListener(type: string, listener: (ev: MessageEvent) => void): void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)?.add(listener);
  }

  removeEventListener(type: string, listener: (ev: MessageEvent) => void): void {
    this.listeners.get(type)?.delete(listener);
  }

  close(): void {
    this.closed = true;
    this.readyState = 2;
  }

  listenerCount(): number {
    let n = 0;
    for (const set of this.listeners.values()) n += set.size;
    return n;
  }

  emit(type: string, data: string): void {
    for (const l of this.listeners.get(type) ?? []) l(new MessageEvent(type, { data }));
  }

  fail(): void {
    this.onerror?.(new Event('error'));
  }
}

export type ScriptStep = { event: string; data: string } | 'ERR';

/**
 * A factory whose n-th EventSource plays the n-th script (a cold marble Observable) in virtual time: messages go
 * to the listeners, 'ERR' fires onerror. close() stops the script, as a real connection would end.
 */
export function scriptedFactory(scripts: Observable<ScriptStep>[]): {
  factory: EventSourceFactory;
  opened: FakeEventSource[];
} {
  const opened: FakeEventSource[] = [];
  const factory: EventSourceFactory = url => {
    const source = new FakeEventSource(url);
    const script = scripts[opened.length];
    opened.push(source);
    // scripts start at frame 1 or later, so the caller has attached its listeners before the first step
    const sub: Subscription | undefined = script?.subscribe(step =>
      step === 'ERR' ? source.fail() : source.emit(step.event, step.data),
    );
    const close = source.close.bind(source);
    source.close = () => {
      sub?.unsubscribe();
      close();
    };
    return source;
  };
  return { factory, opened };
}

export const item = (ticker: string, added_at = 1, pending?: boolean): WatchItem =>
  pending === undefined ? { ticker, added_at } : { ticker, added_at, pending };

export const summary = (last: number, d1: number | null = 1, m1: number | null = 2): PriceSummary => ({
  meta: { ticker: 'X', as_of: '2026-11-07', provider: 'test' },
  last_close: last,
  returns_pct: { '1d': d1, '5d': null, '1m': m1, '3m': null, '6m': null, '1y': null },
  range_52w: { high: last * 1.2, low: last * 0.8, pct_below_high: -10, pct_above_low: 10 },
  avg_volume_20d: 1000,
});

let seq = 0;
export const trace = (type: string, agent = 'system', data: Record<string, unknown> = {}): TraceEvent => ({
  seq: ++seq,
  ts: 0,
  run_id: 'run1',
  type,
  agent,
  data,
});

export const runResult = (rating: RunResult['memo']['rating'] = 'BUY'): RunResult => ({
  run_id: 'run1',
  ticker: 'AAPL',
  memo: { rating, conviction: 0.62, horizon_days: 20, thesis: 'Trend and fundamentals agree.' },
  guardrails: [],
  degraded: [],
  thesis_id: 'th1',
});
