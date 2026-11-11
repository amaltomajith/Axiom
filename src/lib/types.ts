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
  storage?: 'postgres' | 'sqlite';
  daily_cap?: number | null;
}

/** GET /api/status: the health snapshot plus aggregate counts. */
export interface ApiStatus extends Health {
  counts: {
    runs: number;
    last_run_at: number | null;
    theses: Record<string, number>;
    actions: Record<string, number>;
    watchlist: number;
    trades: number;
  };
  analyses_today: { used: number | null; cap: number | null };
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

// ------------------------------------------------------------------ Autopilot (/api/trader)
export type Autonomy = 'SHADOW' | 'SUPERVISED' | 'AUTONOMOUS';

export interface LadderProgress {
  level: Autonomy;
  next: Autonomy | null;
  ceiling: Autonomy | null;
  locked: boolean;
  since: number | null;
  have: number;
  need: number;
  brier: number | null;
  max_brier: number | null;
  net_return_pct: number;
  ready: boolean;
}

export interface RiskBudget {
  daily_pl_pct: number;
  daily_loss_used: number;
  daily_loss_limit_pct: number;
  exposure_pct: number;
  max_gross_pct: number;
  trades_today: number;
  max_trades_per_day: number;
  open_positions: number;
  max_open_positions: number;
}

export interface PendingEntry {
  id: string;
  created_at: number;
  intent: { symbol: string; stop_price: number | null; strategy: string | null; confidence: number | null; reason?: string };
  verdict: { qty: number; price: number; notional: number; risk_amount: number };
  decision: { reason: string; thesis?: string | null };
}

export interface TraderStatus {
  ok: boolean;
  error?: string | null;
  paper: boolean;
  session?: string;
  killed?: boolean;
  halted?: string | null;
  autonomy?: Autonomy;
  running?: boolean;
  broker?: string;
  brain?: string;
  timeframe?: string;
  symbols?: string[];
  heartbeat_age_seconds?: number | null;
  failures?: number;
  last_error?: string | null;
  broker_warning?: string | null;
  symbol_errors?: Record<string, string>;
  /** Latest unusual bar per symbol: volume or range against its recent average. */
  alerts?: Record<string, { volume_x?: number; range_x?: number; move_pct: number; close: number; bar_ts: number; ts: number }>;
  benchmark_value?: number | null;
  pending?: PendingEntry[];
  account?: { equity: number; cash: number; positions: number; is_paper: boolean };
  budget?: RiskBudget;
  ladder?: LadderProgress | null;
  llm_calls_left?: number | null;
  desk_runs_left?: number | null;
  regimes?: Record<string, { trend?: string; volatility?: string }>;
}

/** One step of a trading desk review, as streamed from the agents' trace. */
export interface DeskEvent {
  seq: number;
  ts: number;
  run_id: string;
  kind: string;
  agent: string;
  symbol: string;
  data: Record<string, unknown>;
}

/** What the four agents concluded about one candidate entry. */
export interface DeskReview {
  run_id: string | null;
  rating: Rating | null;
  conviction: number | null;
  thesis: string | null;
  stances: Record<string, string>;
  critic_ok: boolean | null;
  critic_issues: string[];
  guardrails: string[];
  degraded: string[];
  evidence: string[];
  sources: Record<string, EvidenceRef>;
  error: string | null;
}

export type DeskTrigger = 'signal' | 'alert' | 'manual';

/** What the desk did with a review, by fixed rules: go ahead, half size, veto, or leave it to the rules. */
export interface DeskOutcome {
  action: 'go' | 'half' | 'veto' | 'rules';
  size_factor: number;
  why: string;
}

export interface DeskClaim {
  text: string;
  evidence: string[];
}

export interface DeskFinding {
  agent: string;
  stance: string;
  confidence: number;
  summary: string;
  claims: DeskClaim[];
  caveats: string[];
}

/** One saved desk review, as listed under Past reviews. */
export interface DeskRunBrief {
  run_id: string;
  symbol: string;
  strategy: string | null;
  trigger: DeskTrigger;
  started_at: number;
  finished_at: number | null;
  hold_policy?: string;
  review: DeskReview;
  outcome: DeskOutcome;
  recorded?: boolean;
}

/** The same review in full: every step, each agent's claims, the plan and the sources it cites. */
export interface DeskRun extends DeskRunBrief {
  events: DeskEvent[];
  findings?: DeskFinding[];
  memo?: { bull_case: DeskClaim[]; bear_case: DeskClaim[]; key_risks: string[]; what_would_change_my_mind: string[]; horizon_days: number };
  plan?: Record<string, unknown>;
  sources?: Record<string, EvidenceRef>;
}

/** How trades the desk refused (or cut in size) turned out. */
export interface NotTakenTally {
  graded: number;
  open: number;
  would_have_won: number;
  would_have_lost: number;
  avg_return_pct: number | null;
}

export interface DeskStatus {
  enabled: boolean;
  runs: Record<string, { review: DeskReview | null; events: DeskEvent[]; started_at: number; strategy: string | null; trigger?: DeskTrigger; run_id?: string | null; outcome?: DeskOutcome }>;
  reviewing: string[];
  runs_left?: number;
  max_runs_per_hour?: number;
  hold_policy?: string;
  last_error?: string | null;
}

export interface RuleCheck {
  rule: string;
  ok: boolean;
  detail: string;
}

/** A short replay of a fixed window of real history, with what it is expected to show. */
export interface Scenario {
  id: string;
  title: string;
  summary: string;
  symbols: string[];
  start: string;
  end: string;
  expect: string;
}

export interface TraderPosition {
  symbol: string;
  qty: number;
  avg_entry: number;
  market_price: number;
  stop_price: number | null;
  market_value: number;
  unrealized_pl: number;
  strategy: string | null;
  contract_id: string | null;
  entry_ts: number | null;
}

export type JournalKind = 'entry' | 'exit' | 'stop' | 'blocked' | 'proposal' | 'tournament' | 'halt' | 'kill' | 'resume' | 'autonomy' | 'note' | 'contract' | 'shadow' | 'veto' | 'flag';

export interface JournalEntry {
  session: string;
  seq: number;
  ts: number;
  kind: JournalKind;
  symbol: string | null;
  text: string;
  facts: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface ChainCheck {
  ok: boolean;
  n: number;
  broken_at: number | null;
  why?: string;
  head?: string;
}

export interface TradeContract {
  id: string;
  symbol: string;
  created_at: number;
  status: 'open' | 'graded' | 'cancelled';
  shadow: boolean;
  source: string;
  strategy: string | null;
  confidence: number | null;
  thesis: string | null;
  expected_move_pct: number | null;
  horizon_bars: number | null;
  entry_price: number;
  stop_price: number | null;
  invalidation: { type: string; [k: string]: unknown }[];
  result: {
    ts: number;
    return_pct: number | null;
    realized_pl: number | null;
    reason: string;
    outcome: number;
    target_hit: boolean;
    brier: number;
    grade: 'A' | 'B' | 'C' | 'D';
  } | null;
}

export interface CalibrationSummary {
  n: number;
  brier: number | null;
  win_rate: number | null;
  mean_confidence: number | null;
  buckets: { lo: number; hi: number; n: number; mean_confidence: number; win_rate: number }[];
  grades: Record<string, number>;
  shadow: number;
  net_return_pct: number;
}

export interface CalibrationResponse {
  all: CalibrationSummary;
  recent: CalibrationSummary;
  ladder?: LadderProgress;
  not_taken?: { vetoes: NotTakenTally; halved: NotTakenTally };
}

export interface EquityPoint {
  ts: number;
  equity: number;
  cash: number;
  benchmark: number | null;
}

export interface ReplayJob {
  id: string;
  session: string;
  symbols: string[];
  bars: number;
  status: 'queued' | 'fetching' | 'running' | 'done' | 'error' | 'stopped';
  progress: number;
  sim_ts: number | null;
  started_at: number;
  finished_at: number | null;
  error: string | null;
  verdict: { verdict: Verdict; message: string; sharpe_diff: number | null; sharpe_diff_ci95: [number | null, number | null] } | null;
  scenario?: string | null;
  outcome?: { ok: boolean; detail: string } | null;
}

export interface ReportMetrics {
  total_return: number;
  cagr: number;
  ann_vol: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  calmar: number;
  exposure?: number;
}

export interface BacktestReport {
  title: string;
  generated_at: string;
  period: { start: string; end: string; years: number; bars: number };
  universe: string[];
  start_cash: number;
  agent: ReportMetrics;
  benchmark: ReportMetrics;
  verdict: { verdict: Verdict; message: string; sharpe_diff: number | null; sharpe_diff_ci95: [number | null, number | null] };
  fixed_strategies: Record<string, ReportMetrics>;
  trades: { entries: number; closed: number; win_rate: number | null; profit_factor: number | null; fees_paid: number };
  risk_events: { stop_outs: number; daily_loss_halts: number; blocked: Record<string, number>; tournament_changes: number };
  contracts: CalibrationSummary;
  curve: { date: string; agent: number; benchmark: number }[];
  journal_entries: number;
}

export interface RedteamResult {
  approved: boolean;
  failed_rules: string[];
  verdict: { reason: string; blocked_by: string | null };
  headline: { text: string; flagged: boolean; model_sees: string | null };
}
