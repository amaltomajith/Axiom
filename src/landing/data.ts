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
export const BACKTEST_DOC = `${REPO}/blob/main/docs/backtest-report.md`;

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

/** Sections the nav and footer link to. */
export const NAV_LINKS = [
  { href: '#how', label: 'How it works' },
  { href: '#modes', label: 'Modes' },
  { href: '#honest', label: 'Results' },
  { href: '#faq', label: 'Questions' },
] as const;

/** Questions and answers for the landing FAQ. */
export const FAQ = [
  { q: 'Is any real money involved?', a: 'No. Axiom only trades pretend money in a practice account, and there is no setting that connects it to real funds.' },
  { q: 'What does it trade?', a: 'Bitcoin and Ethereum, which trade around the clock. It can also follow a few well-known US stocks and funds.' },
  {
    q: 'Will it make me money?',
    a: 'We cannot promise that, and you should be wary of anyone who does. In long practice runs it lost less than simply holding in the bad stretches and made much less overall. That is why it starts on paper.',
  },
  { q: 'Do I have to pay for the AI?', a: 'No. It uses free AI models, or one running on your own computer. If none are available, it falls back to simple, fixed rules.' },
  { q: 'How do I stop it?', a: 'Press the red stop button at the top of the screen. Every open order is cancelled and every position is closed straight away.' },
  { q: 'Can I see how it made a decision?', a: 'Always. Every trade, and every trade it decided against, has a short note in plain language that you can read at any time.' },
];
