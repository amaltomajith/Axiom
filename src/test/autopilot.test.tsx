import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DeskEvent, DeskReview, JournalEntry, TraderStatus } from '@/lib/types';

const mocks = vi.hoisted(() => ({
  status: vi.fn(),
  positions: vi.fn(),
  journal: vi.fn(),
  verify: vi.fn(),
  contracts: vi.fn(),
  calibration: vi.fn(),
  equity: vi.fn(),
  report: vi.fn(),
  replays: vi.fn(),
  scenarios: vi.fn(),
  desk: vi.fn(),
  kill: vi.fn(),
  resume: vi.fn(),
  start: vi.fn(),
  stop: vi.fn(),
  setAutonomy: vi.fn(),
  approve: vi.fn(),
  reject: vi.fn(),
  replay: vi.fn(),
  stopReplay: vi.fn(),
  redteam: vi.fn(),
  streamUrl: () => 'http://localhost:8000/api/trader/stream?session=live',
}));

vi.mock('@/lib/api', async orig => ({ ...(await orig<typeof import('@/lib/api')>()), trader: mocks }));

import { AutopilotTab } from '@/components/autopilot/AutopilotTab';
import { Ladder, RiskBudget } from '@/components/autopilot/ControlBar';
import { deskSteps, gateRows, regimeSummary } from '@/components/autopilot/deskModel';

const STATUS: TraderStatus = {
  ok: true,
  paper: true,
  killed: false,
  halted: null,
  autonomy: 'SUPERVISED',
  running: true,
  broker: 'sim',
  brain: 'rule',
  timeframe: '1Hour',
  heartbeat_age_seconds: 12,
  benchmark_value: 101_000,
  account: { equity: 100_500, cash: 80_000, positions: 1, is_paper: true },
  budget: {
    daily_pl_pct: -0.005,
    daily_loss_used: 0.25,
    daily_loss_limit_pct: 0.025,
    exposure_pct: 0.2,
    max_gross_pct: 1,
    trades_today: 2,
    max_trades_per_day: 10,
    open_positions: 1,
    max_open_positions: 4,
  },
  ladder: { level: 'SUPERVISED', next: 'AUTONOMOUS', ceiling: null, locked: false, since: null, have: 3, need: 12, brier: 0.21, max_brier: 0.24, net_return_pct: 1.5, ready: false },
  pending: [
    {
      id: 'p-1',
      created_at: Date.now() / 1000 - 30,
      intent: { symbol: 'BTC/USD', stop_price: 58_000, strategy: 'sma_cross', confidence: 0.6 },
      verdict: { qty: 0.25, price: 60_000, notional: 15_000, risk_amount: 500 },
      decision: { reason: 'sma_cross ranked first.' },
    },
  ],
};

const ENTRY: JournalEntry = {
  session: 'live',
  seq: 1,
  ts: 1_762_000_000,
  kind: 'blocked',
  symbol: 'BTC/USD',
  text: 'Red team: asked to buy 1,000,000 BTC/USD at once. The risk kernel blocked it.',
  facts: { blocked_by: 'R6' },
  prev_hash: '0',
  hash: 'abc',
};

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AutopilotTab />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.status.mockResolvedValue(STATUS);
  mocks.positions.mockResolvedValue([]);
  mocks.journal.mockResolvedValue([ENTRY]);
  mocks.verify.mockResolvedValue({ ok: true, n: 1, broken_at: null, head: 'abc' });
  mocks.contracts.mockResolvedValue([]);
  mocks.calibration.mockResolvedValue({ all: { n: 0, brier: null, win_rate: null, mean_confidence: null, buckets: [], grades: {}, shadow: 0, net_return_pct: 0 }, recent: {} });
  mocks.equity.mockResolvedValue([]);
  mocks.report.mockRejectedValue(new Error('No backtest report yet'));
  mocks.replays.mockResolvedValue([]);
  mocks.scenarios.mockResolvedValue([]);
  mocks.desk.mockResolvedValue({ enabled: false, runs: {}, reviewing: [] });
  mocks.kill.mockResolvedValue({ ok: true, closed: 1 });
  mocks.approve.mockResolvedValue({ ok: true });
});

describe('Ladder', () => {
  it('marks the current level and says what the next one needs', () => {
    render(<Ladder level="SHADOW" progress={{ ...STATUS.ladder!, level: 'SHADOW', next: 'SUPERVISED', have: 5, need: 8, max_brier: 0.25 }} onSet={() => {}} busy={false} />);
    expect(screen.getByRole('button', { name: /Shadow/ })).toHaveAttribute('aria-current', 'step');
    expect(screen.getByText(/after 8 graded shadow contracts/)).toBeInTheDocument();
    expect(screen.getByText(/So far 5 of 8/)).toBeInTheDocument();
  });

  it('explains a human lock', () => {
    render(<Ladder level="SUPERVISED" progress={{ ...STATUS.ladder!, locked: true, ceiling: 'SUPERVISED' }} onSet={() => {}} busy={false} />);
    expect(screen.getByText(/locked: a human set this level/)).toBeInTheDocument();
  });
});

describe('RiskBudget', () => {
  it('shows each budget against its hard limit', () => {
    render(<RiskBudget status={STATUS} />);
    expect(screen.getByRole('meter', { name: 'Daily loss budget used' })).toHaveAttribute('aria-valuenow', '25');
    expect(screen.getByText('2 of 10')).toBeInTheDocument();
    expect(screen.getByText('1 of 4')).toBeInTheDocument();
  });
});

const REVIEW: DeskReview = {
  run_id: 'run1',
  rating: 'BUY',
  conviction: 0.62,
  thesis: 'Trend and backtest agree on the long side.',
  stances: { 'Technical Analyst': 'bullish', 'Fundamental Auditor': 'insufficient_data' },
  critic_ok: false,
  critic_issues: ['The last three breakout trades hit their stops.'],
  guardrails: [],
  degraded: [],
  evidence: ['T1'],
  sources: { T1: { id: 'T1', tool: 'run_backtest', args: { ticker: 'BTC-USD' }, as_of: '2026-11-10', provider: 'yahoo', excerpt: '{"verdict":"edge_detected"}' } },
  error: null,
};
const ev = (seq: number, agent: string, kind: string, data: Record<string, unknown> = {}): DeskEvent => ({ seq, ts: 1_762_000_000 + seq, run_id: 'run1', kind, agent, symbol: 'BTC/USD', data });
const EVENTS = [
  ev(1, 'system', 'run_start'),
  ev(2, 'Technical Analyst', 'tool_call', { name: 'run_backtest' }),
  ev(3, 'Technical Analyst', 'finding', { stance: 'bullish', summary: 'A backtest found an edge.' }),
  ev(4, 'Fundamental Auditor', 'agent_error', { message: 'no filings for a coin' }),
  ev(5, 'Risk Critic', 'critique', { ok: false, issues: ['The last three breakout trades hit their stops.'] }),
];

describe('trading desk', () => {
  it('turns the trace into the four agent steps, in order', () => {
    const steps = deskSteps(EVENTS, REVIEW, false);
    expect(steps.map(s => s.name)).toEqual(['Technical Analyst', 'Fundamental Auditor', 'Lead Synthesizer', 'Risk Critic']);
    expect(steps[0]).toMatchObject({ state: 'done', result: 'A backtest found an edge.', badge: { text: 'Bullish' } });
    expect(steps[1]).toMatchObject({ state: 'failed', badge: { text: 'No view' } }); // a coin has no filings: no view, not a veto
    expect(steps[2]).toMatchObject({ state: 'done', badge: { text: 'Buy, conviction 0.62' } });
    expect(steps[3]).toMatchObject({ state: 'done', result: 'The last three breakout trades hit their stops.', badge: { text: 'Objected' } });
  });

  it('shows who is still working while a review runs', () => {
    const steps = deskSteps(EVENTS.slice(0, 2), null, true);
    expect(steps.map(s => s.state)).toEqual(['working', 'waiting', 'waiting', 'waiting']);
    expect(steps[0].result).toBe('Called 1 tool so far.');
  });

  it('groups the kernel rules into the six gate checks', () => {
    const check = (rule: string, ok = true) => ({ rule, ok, detail: `${rule} detail` });
    const passed: JournalEntry = {
      ...ENTRY,
      kind: 'entry',
      facts: { rewrite: 'accepted', checks: ['R0', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7', 'R8', 'R9', 'R10', 'R11', 'R12'].map(r => check(r)) },
    };
    const g = gateRows(passed, '2.5%');
    expect(g.rows.map(r => r.label)).toEqual(['Paper account only', 'Stop-loss attached', 'Size within caps', 'Day loss under 2.5%', 'Kill switch is off', 'Journal numbers verified']);
    expect(g.rows.every(r => r.ok)).toBe(true);
    expect(g.rows[5].detail).toMatch(/kept every number/);
    expect(g.also.map(c => c.rule)).toEqual(['R2', 'R4', 'R10', 'R11', 'R12']);

    const blocked: JournalEntry = { ...ENTRY, facts: { checks: [check('R0'), check('R1'), check('R5'), check('R6', false)] } };
    const b = gateRows(blocked, '2.5%').rows;
    expect(b[2]).toMatchObject({ ok: false, detail: 'R6 detail' });
    expect(b[3]).toMatchObject({ ok: null }); // the day-loss check was not part of this verdict
  });

  it('renders the latest review and the gate on the cockpit', async () => {
    mocks.desk.mockResolvedValue({ enabled: true, runs_left: 5, reviewing: [], runs: { 'BTC/USD': { review: REVIEW, events: EVENTS, started_at: 1_762_000_000, strategy: 'sma_cross' } } });
    mocks.journal.mockResolvedValue([{ ...ENTRY, kind: 'proposal', facts: { checks: [{ rule: 'R1', ok: true, detail: 'The broker is a paper account.' }], desk: REVIEW } }]);
    renderTab();
    const card = (await screen.findByRole('heading', { name: 'Live run' })).closest('section')!;
    expect(await within(card).findByText('Objected')).toBeInTheDocument();
    expect(within(card).getByText('5 reviews left this hour')).toBeInTheDocument();
    expect(within(card).getByText('Passed, waiting for you')).toBeInTheDocument();
    expect(within(card).getByText('The broker is a paper account.')).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: /Evidence T1: run_backtest/ })).toBeInTheDocument();
    expect(await screen.findByText(/Desk review: Buy, conviction 0.62/)).toBeInTheDocument(); // and on the journal row
  });

  it('says so when the four-agent review is off', async () => {
    mocks.journal.mockResolvedValue([{ ...ENTRY, facts: { checks: [{ rule: 'R6', ok: false, detail: 'Requested 1,000,000.' }] } }]);
    renderTab();
    expect(await screen.findByText(/four-agent review is switched off/)).toBeInTheDocument();
    expect(await screen.findByText('Requested 1,000,000.')).toBeInTheDocument();
  });
});

describe('regime tile', () => {
  it('uses one word when every market agrees and a count when they do not', () => {
    expect(regimeSummary(undefined)).toBeNull();
    expect(regimeSummary({ 'BTC/USD': { trend: 'uptrend', volatility: 'normal' }, 'ETH/USD': { trend: 'uptrend', volatility: 'high' } })?.headline).toBe('Trending up');
    const mixed = regimeSummary({ A: { trend: 'uptrend' }, B: { trend: 'uptrend' }, C: { trend: 'downtrend' } });
    expect(mixed?.headline).toBe('Trending up (2 of 3)');
    expect(mixed?.detail).toContain('C: trending down, unknown volatility');
  });

  it('sits beside the equity on the control bar', async () => {
    mocks.status.mockResolvedValue({ ...STATUS, regimes: { 'BTC/USD': { trend: 'sideways', volatility: 'low' } } });
    renderTab();
    expect(await screen.findByText('Market regime')).toBeInTheDocument();
    expect(screen.getByText('Sideways')).toBeInTheDocument();
  });
});

describe('scenarios', () => {
  it('plays a named scenario and reports whether it showed what it promised', async () => {
    const sc = { id: 'flash_crash', title: 'Flash crash', summary: 'A real sell-off.', symbols: ['BTC/USD', 'SPY'], start: '2025-08-25', end: '2025-10-17', expect: 'The limit trips.' };
    mocks.scenarios.mockResolvedValue([sc]);
    mocks.replay.mockResolvedValue({ id: 'r1', session: 'replay:r1' });
    mocks.replays.mockResolvedValue([
      {
        id: 'r0',
        session: 'replay:r0',
        symbols: ['BTC/USD'],
        bars: 1500,
        status: 'done',
        progress: 1,
        sim_ts: null,
        started_at: 1,
        finished_at: 2,
        error: null,
        verdict: null,
        scenario: 'flash_crash',
        outcome: { ok: true, detail: 'Daily loss limit hit: equity is -2.87% on the day.' },
      },
    ]);
    renderTab();
    expect(await screen.findByText('2 markets, 2025-08-25 to 2025-10-17')).toBeInTheDocument();
    expect(await screen.findByText('As expected')).toBeInTheDocument();
    expect(screen.getByText(/equity is -2.87% on the day/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Play Flash crash' }));
    await waitFor(() => expect(mocks.replay).toHaveBeenCalledWith(0, 0.4, 'flash_crash'));
  });
});

describe('AutopilotTab', () => {
  it('shows the paper badge, the journal with its chain check, and the approval queue', async () => {
    renderTab();
    expect(await screen.findByText('PAPER')).toBeInTheDocument();
    expect(await screen.findByText(/Red team: asked to buy 1,000,000/)).toBeInTheDocument();
    expect(await screen.findByText(/1 entries, chain intact/)).toBeInTheDocument();
    expect(screen.getByText('Waiting for approval (1)')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(mocks.approve).toHaveBeenCalled());
  });

  it('asks before killing, then flattens through the API', async () => {
    renderTab();
    fireEvent.click(await screen.findByRole('button', { name: /Kill switch/ }));
    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText(/every position is closed at market on the paper account/)).toBeInTheDocument();
    expect(mocks.kill).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Kill and flatten' }));
    await waitFor(() => expect(mocks.kill).toHaveBeenCalledTimes(1));
  });

  it('explains a trader that could not be built', async () => {
    mocks.status.mockResolvedValue({ ok: false, paper: true, error: 'BrokerError: TRADER_BROKER=alpaca needs ALPACA_API_KEY' });
    renderTab();
    expect(await screen.findByText('The Autopilot could not start')).toBeInTheDocument();
    expect(screen.getByText(/needs ALPACA_API_KEY/)).toBeInTheDocument();
  });
});
