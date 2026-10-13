import raw from './snapshot.json';
import type { Bar, BacktestResponse, ConeStep, EvidenceRef, Finding, Memo, PositionPlan, TraceEvent, ActionPlan } from '@/lib/types';

/**
 * Everything the landing page shows comes from one recorded snapshot (backend/scripts/capture_snapshot.py):
 * a real analysis run, real prices, a real backtest, the real approval payload and the real eval numbers.
 * Nothing on the page is typed in by hand.
 */
export interface Snapshot {
  captured_at: string;
  ticker: string;
  provider: string;
  bars: Bar[];
  cone: ConeStep[];
  calibration: { nominal_coverage: number; empirical_coverage: number | null; n_checks: number; well_calibrated: boolean };
  result: {
    memo: Memo;
    findings: Finding[];
    position: PositionPlan;
    evidence: Record<string, EvidenceRef>;
    guardrails: string[];
    degraded: string[];
    usage: { tokens?: number; calls?: number };
  };
  events: TraceEvent[];
  backtest: Pick<BacktestResponse, 'strategy' | 'metrics' | 'benchmark_metrics' | 'verdict' | 'message' | 'sharpe_diff' | 'sharpe_diff_ci95' | 'equity_curve' | 'assumptions'>;
  scorecard: { n_scored: number; n_pending: number; sufficient_sample: boolean; sample_note: string };
  approval: { source: string; reason: string; rating: string; plan: ActionPlan | null };
  evals: {
    passed: string;
    honesty: string;
    injection: string;
    draft_resisted: string;
    control_obeyed: string;
    judge: string;
    cases: { name: string; rating: string }[];
  };
}

export const snapshot = raw as unknown as Snapshot;

export const REPO = 'https://github.com/amaltomajith/Axiom';
export const EVAL_REPORT = `${REPO}/blob/main/docs/eval-report.md`;

/** The 11 MCP tools the server exposes (kept in sync with backend/axiom/mcp_server/server.py by a test). */
export const MCP_TOOLS = [
  'get_price_summary',
  'get_indicators',
  'get_regime',
  'get_risk_metrics',
  'get_company_news_sentiment',
  'fetch_sec_filing_summary',
  'run_backtest',
  'run_walk_forward_model',
  'get_forecast_cone',
  'size_position',
  'get_peer_comparison',
] as const;
