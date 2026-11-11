import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { JournalEntry, TraderStatus } from '@/lib/types';

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
    daily_loss_limit_pct: 0.02,
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
