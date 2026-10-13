// Shapes returned by the Axiom backend (backend/axiom/api/app.py).

export interface Bar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface OhlcvResponse {
  ticker: string;
  provider: string;
  bars: Bar[];
}

export interface Meta {
  tool?: string;
  ticker?: string;
  as_of?: string;
  provider?: string;
  n_bars?: number;
  note?: string;
}

export interface IndicatorsResponse {
  meta: Meta;
  values: Record<string, number | null>;
  reading: string[];
  caveat: string;
}

export interface RegimeResponse {
  meta: Meta;
  trend: string;
  volatility: string;
  vol_percentile: number | null;
  current_vol_annualized: number | null;
}

export interface ConeStep {
  step: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
}

export interface ForecastResponse {
  meta: Meta;
  last_close?: number;
  horizon_days?: number;
  method?: string;
  cone?: ConeStep[];
  error?: string;
  calibration?: {
    nominal_coverage: number;
    empirical_coverage: number | null;
    n_checks: number;
    well_calibrated: boolean;
  };
  caveat?: string;
}

export interface Metrics {
  total_return: number;
  cagr: number;
  ann_vol: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  hit_rate: number;
  exposure: number;
  n_days: number;
}

export type Verdict = 'insufficient_data' | 'no_edge' | 'unproven' | 'edge_detected';

export interface EquityPoint {
  date: string;
  strategy: number;
  benchmark: number;
}

export interface BacktestResponse {
  meta?: Meta;
  strategy: string;
  metrics: Metrics;
  benchmark_metrics: Metrics;
  verdict: Verdict;
  message: string;
  sharpe_diff: number;
  sharpe_diff_ci95: [number | null, number | null];
  equity_curve: EquityPoint[];
  assumptions: string;
  model_skill?: {
    oos_r2_vs_zero: number;
    directional_accuracy: number;
    naive_majority_accuracy: number;
    directional_p_value_vs_naive: number;
    n_oos: number;
    interpretation: string;
  };
}

export interface NewsItem {
  headline: string;
  summary: string;
  source: string | null;
  date: string | null;
  lexicon_score: number;
  label: 'positive' | 'neutral' | 'negative';
  injection_suspected: boolean;
}

export interface NewsResponse {
  ticker: string;
  provider: string;
  n_articles: number;
  net_sentiment: number;
  net_label: 'positive' | 'neutral' | 'negative';
  sentiment_method: string;
  injection_flagged: number;
  items: NewsItem[];
}

export interface Health {
  ok: boolean;
  llm_chain: string[];
  llm_models: Record<string, string>;
  market_data: string;
  news: string;
  actions_executor: 'dry_run' | 'composio';
  auth_required: boolean;
  scheduler: boolean;
}

// ----------------------------------------------------------------------- agents

export type Rating = 'STRONG_BUY' | 'BUY' | 'HOLD' | 'SELL' | 'STRONG_SELL' | 'NO_CALL';

export interface Claim {
  text: string;
  evidence: string[];
}

export interface Finding {
  agent: string;
  stance: 'bullish' | 'bearish' | 'neutral' | 'insufficient_data';
  confidence: number;
  summary: string;
  claims: Claim[];
  caveats: string[];
}

export interface Memo {
  ticker: string;
  rating: Rating;
  conviction: number;
  horizon_days: number;
  thesis: string;
  bull_case: Claim[];
  bear_case: Claim[];
  key_risks: string[];
  what_would_change_my_mind: string[];
  prior_theses_addressed: string;
}

export interface PositionPlan {
  action: 'open_long' | 'avoid' | 'none';
  shares: number;
  entry_reference: number | null;
  stop_price: number | null;
  risk_amount: number | null;
  position_pct: number | null;
  violations: string[];
  notes: string[];
}

export interface EvidenceRef {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  as_of: string | null;
  provider: string | null;
  excerpt: string;
}

export interface ActionStep {
  kind: 'paper_trade' | 'notion_page' | 'sheet_row' | 'slack_message';
  title: string;
  preview: Record<string, unknown>;
  idempotency_key: string;
  status: 'pending' | 'done' | 'failed' | 'skipped';
  result: Record<string, unknown> | null;
  error: string | null;
}

export interface ActionPlan {
  id: string;
  run_id: string;
  ticker: string;
  created_at: number;
  status: 'proposed' | 'executed' | 'partial' | 'failed' | 'rejected';
  rating: string;
  conviction: number;
  executor: 'dry_run' | 'composio';
  steps: ActionStep[];
}

export interface AnalysisResult {
  run_id: string;
  ticker: string;
  memo: Memo;
  markdown: string;
  findings: Finding[];
  position: PositionPlan;
  evidence: Record<string, EvidenceRef>;
  guardrails: string[];
  degraded: string[];
  usage: { tokens?: number; max_tokens?: number; calls?: number; max_calls?: number };
  thesis_id: string;
  action: ActionPlan | null;
  action_reason: string;
}

export interface TraceEvent {
  seq: number;
  ts: number;
  run_id: string;
  type: string;
  agent: string;
  data: Record<string, unknown>;
}

// ----------------------------------------------------------------------- memory

export interface Outcome {
  horizon_date: string;
  price_at_horizon: number;
  ret_pct: number;
  benchmark_ret_pct: number | null;
  excess_ret_pct: number | null;
  direction_hit: 0 | 1 | null;
  beat_benchmark: 0 | 1 | null;
  stop_hit: 0 | 1 | null;
  brier: number | null;
}

export interface Thesis {
  id: string;
  run_id: string;
  ticker: string;
  issue_date: string;
  horizon_days: number;
  price_at_issue: number;
  rating: Rating;
  conviction: number;
  status: 'pending' | 'scored';
  outcome: Outcome | null;
}

export interface RateBucket {
  n: number;
  hit_rate: number | null;
}

export interface Scorecard {
  n_scored: number;
  n_pending: number;
  n_directional: number;
  sufficient_sample: boolean;
  sample_note: string;
  direction_hit_rate: number | null;
  baseline_up_rate: number | null;
  beat_benchmark_rate: number | null;
  mean_excess_return_pct: number | null;
  mean_brier: number | null;
  brier_skill_vs_coinflip: number | null;
  stop_hit_rate: number | null;
  by_conviction: Record<string, RateBucket>;
  by_agent: Record<string, RateBucket>;
  by_rating: Record<string, number>;
}

export interface WatchItem {
  ticker: string;
  added_at: number;
}

export interface PaperTrade {
  id: string;
  ticker: string;
  side: string;
  quantity: number;
  entry_price: number;
  entry_date: string;
  thesis_id: string | null;
  exit_price: number | null;
  exit_date: string | null;
}
