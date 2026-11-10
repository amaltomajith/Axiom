// Shapes returned by the Axiom API (backend/axiom/api/app.py). Only the fields this app reads.

export interface Health {
  ok: boolean;
  llm_chain: string[];
  auth_required: boolean;
  storage: string;
  daily_cap: number | null;
}

export interface WatchItem {
  ticker: string;
  added_at: number;
  /** set while an optimistic add waits for the API */
  pending?: boolean;
}

export type ReturnWindow = '1d' | '5d' | '1m' | '3m' | '6m' | '1y';

export interface PriceSummary {
  meta: { ticker?: string; as_of?: string; provider?: string };
  last_close: number;
  returns_pct: Record<ReturnWindow, number | null>;
  range_52w: { high: number; low: number; pct_below_high: number; pct_above_low: number };
  avg_volume_20d: number;
}

export type Rating = 'STRONG_BUY' | 'BUY' | 'HOLD' | 'SELL' | 'STRONG_SELL' | 'NO_CALL';

export interface ThesisRow {
  id: string;
  run_id: string;
  ticker: string;
  created_at: number;
  issue_date: string;
  rating: Rating;
  conviction: number;
}

export interface RatingInfo {
  rating: Rating;
  conviction: number;
  issuedOn: string;
}

export interface TickerMatch {
  ticker: string;
  name: string;
}

export interface TraceEvent {
  seq: number;
  ts: number;
  run_id: string;
  type: string;
  agent: string;
  data: Record<string, unknown>;
}

export interface RunResult {
  run_id: string;
  ticker: string;
  memo: { rating: Rating; conviction: number; horizon_days: number; thesis: string };
  guardrails: string[];
  degraded: string[];
  thesis_id: string;
}
