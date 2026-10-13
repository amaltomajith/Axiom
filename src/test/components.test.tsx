import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { AgentTraceDrawer, describeEvent } from '@/components/AgentTraceDrawer';
import { MemoPanel } from '@/components/MemoPanel';
import { NewsPanel } from '@/components/NewsPanel';
import { PipelineStepper } from '@/components/PipelineStepper';
import { Segmented } from '@/components/kit/Segmented';
import { Cell, List, ListRow } from '@/components/kit/List';
import { deriveProgress } from '@/hooks/useTraceProgress';
import type { AnalysisResult, NewsResponse, TraceEvent } from '@/lib/types';

const ev = (seq: number, type: string, agent: string, data: Record<string, unknown> = {}): TraceEvent => ({ seq, ts: 0, run_id: 'r', type, agent, data });

describe('describeEvent', () => {
  it('renders tool calls and results as readable lines', () => {
    const call = describeEvent(ev(1, 'tool_call', 'Technical Analyst', { tool: 'get_indicators', args: { ticker: 'AAPL' } }))!;
    expect(call.tag).toBe('Tool');
    expect(call.text).toBe('get_indicators(ticker=AAPL)');
    expect(call.group).toBe('tools');
    const res = describeEvent(ev(2, 'tool_result', 'Technical Analyst', { tool: 'get_indicators', ok: true, evidence_id: 'T2', latency_ms: 340, preview: 'x' }))!;
    expect(res.text).toContain('saved as T2');
    expect(res.tone).toBe('ok');
  });

  it('highlights guardrails and failures, and ignores unknown event types', () => {
    const g = describeEvent(ev(3, 'guardrail', 'Policy', { name: 'policy_cap', detail: 'Downgraded to HOLD' }))!;
    expect(g.tone).toBe('warn');
    expect(g.group).toBe('guards');
    expect(describeEvent(ev(4, 'tool_result', 'Risk Guard', { tool: 'size_position', ok: false, latency_ms: 5 }))!.tag).toBe('Failed');
    expect(describeEvent(ev(5, 'mystery', 'system'))).toBeNull();
  });
});

describe('deriveProgress', () => {
  const start = (agent: string) => ev(1, 'agent_start', agent, { tools: [] });

  it('starts with everything pending', () => {
    expect(deriveProgress([], 'idle').map(s => s.state)).toEqual(['pending', 'pending', 'pending', 'pending', 'pending']);
  });

  it('marks only what the backend reported, and shows the live tool call', () => {
    const events = [
      start('Technical Analyst'),
      ev(2, 'tool_call', 'Technical Analyst', { tool: 'run_backtest', args: {} }),
      start('Fundamental Auditor'),
      ev(3, 'finding', 'Fundamental Auditor', { stance: 'bullish', confidence: 0.8, summary: 's' }),
    ];
    const steps = deriveProgress(events, 'running');
    expect(steps[0]).toMatchObject({ state: 'active', detail: 'Calling run_backtest' });
    expect(steps[1]).toMatchObject({ state: 'done', detail: 'bullish at 80% confidence' });
    expect(steps[2].state).toBe('pending');
  });

  it('flags a failed analyst as a warning, not a success', () => {
    const steps = deriveProgress([start('Technical Analyst'), ev(2, 'agent_error', 'Technical Analyst', { message: 'x' })], 'running');
    expect(steps[0].state).toBe('warn');
  });

  it('advances through risk, synthesis and policy, and finishes everything on the final event', () => {
    const mid = [
      ev(1, 'finding', 'Technical Analyst', { stance: 'neutral', confidence: 0.4 }),
      ev(2, 'finding', 'Fundamental Auditor', { stance: 'neutral', confidence: 0.5 }),
      ev(3, 'handoff', 'system', { to: 'Risk Guard' }),
      ev(4, 'tool_call', 'Risk Guard', { tool: 'size_position', args: {} }),
    ];
    expect(deriveProgress(mid, 'running')[2].state).toBe('active');
    const later = [...mid, ev(5, 'handoff', 'system', { to: 'Lead Synthesizer' }), ev(6, 'memo_draft', 'Lead Synthesizer', {})];
    const s = deriveProgress(later, 'running');
    expect(s[2].state).toBe('done');
    expect(s[3].state).toBe('done');
    expect(s[4].state).toBe('active');
    const done = deriveProgress([...later, ev(7, 'guardrail', 'Policy', { name: 'policy_cap' }), ev(8, 'final', 'Lead Synthesizer', {})], 'done');
    expect(done.every(x => x.state === 'done')).toBe(true);
    expect(done[4].detail).toBe('1 adjustment applied');
  });
});

describe('PipelineStepper', () => {
  it('exposes progress to assistive tech and marks the current step', () => {
    const steps = deriveProgress([ev(1, 'agent_start', 'Technical Analyst', { tools: [] })], 'running');
    render(<PipelineStepper steps={steps} />);
    expect(screen.getByRole('list', { name: 'Analysis progress' })).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(5);
    expect(screen.getByText('Technical analysis').closest('li')).toHaveAttribute('aria-current', 'step');
  });
});

describe('AgentTraceDrawer', () => {
  it('shows live counts: events, non-cached tokens and guardrail events', () => {
    const events = [
      ev(1, 'run_start', 'system', { ticker: 'AAPL' }),
      ev(2, 'llm_call', 'Technical Analyst', { provider: 'ollama', model: 'q', prompt_tokens: 100, completion_tokens: 50, latency_ms: 10, cached: false }),
      ev(3, 'llm_call', 'Technical Analyst', { provider: 'ollama', model: 'q', prompt_tokens: 999, completion_tokens: 999, latency_ms: 1, cached: true }),
      ev(4, 'guardrail', 'Policy', { name: 'policy_cap', detail: 'x' }),
    ];
    render(<AgentTraceDrawer open onOpenChange={() => {}} events={events} status="running" error={null} />);
    expect(screen.getByText('Agent trace')).toBeInTheDocument();
    expect(screen.getByText(/150 tokens/)).toBeInTheDocument(); // the cached call is excluded
    expect(screen.getByText(/1 guardrail events/)).toBeInTheDocument();
    expect(screen.getByText(/Analysis started for AAPL/)).toBeInTheDocument();
  });
});

const result = {
  run_id: 'r1',
  ticker: 'AAPL',
  memo: {
    ticker: 'AAPL',
    rating: 'HOLD',
    conviction: 0.4,
    horizon_days: 30,
    thesis: 'Mixed evidence argues for patience.',
    bull_case: [{ text: 'Revenue grew 6.4% year on year.', evidence: ['T8'] }],
    bear_case: [{ text: 'The moving-average rule did not beat buy-and-hold.', evidence: ['T4'] }],
    key_risks: ['Valuation'],
    what_would_change_my_mind: ['A detected backtest edge'],
    prior_theses_addressed: '',
  },
  markdown: '# AAPL: Hold',
  findings: [{ agent: 'Technical Analyst', stance: 'neutral', confidence: 0.4, summary: 'No edge.', claims: [], caveats: [] }],
  position: { action: 'none', shares: 0, entry_reference: null, stop_price: null, risk_amount: null, position_pct: null, violations: [], notes: [] },
  evidence: {
    T8: { id: 'T8', tool: 'fetch_sec_filing_summary', args: { ticker: 'AAPL' }, as_of: '2025-09-27', provider: 'SEC EDGAR', excerpt: '{"revenue": 416161000000}' },
    T4: { id: 'T4', tool: 'run_backtest', args: { ticker: 'AAPL' }, as_of: '2026-10-12', provider: 'yfinance', excerpt: '{"verdict": "no_edge"}' },
  },
  guardrails: ['Conviction capped at 0.5.'],
  degraded: ['Synthesizer degraded: test'],
  usage: { tokens: 1234, calls: 5 },
  thesis_id: 't',
  action: null,
  action_reason: '',
} as unknown as AnalysisResult;

describe('MemoPanel', () => {
  it('renders the rating, conviction, claims with citation chips, and the degraded warning', () => {
    render(<MemoPanel result={result} />);
    expect(screen.getByText('Hold')).toBeInTheDocument();
    expect(screen.getByRole('meter', { name: 'Conviction' })).toHaveAttribute('aria-valuenow', '40');
    expect(screen.getByText(/Revenue grew 6.4%/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Evidence T8/ }).length).toBeGreaterThan(0);
    expect(screen.getByRole('status')).toHaveTextContent('Synthesizer degraded: test');
    expect(screen.getByText(/1,234 tokens across 5 model calls/)).toBeInTheDocument();
    expect(screen.getByText('No position proposed')).toBeInTheDocument();
  });

  it('lists every source under Evidence', () => {
    render(<MemoPanel result={result} />);
    expect(screen.getByText(/Evidence, 2 sources/)).toBeInTheDocument();
    expect(screen.getAllByText('run_backtest').length).toBeGreaterThan(0);
  });
});

describe('NewsPanel', () => {
  const news = {
    ticker: 'AAPL', provider: 'google_news_rss', n_articles: 2, net_sentiment: 0.5, net_label: 'positive', sentiment_method: 'keyword lexicon', injection_flagged: 1,
    items: [
      { headline: 'Apple beats estimates', summary: '', source: 'Reuters', date: '2026-10-08', lexicon_score: 1, label: 'positive', injection_suspected: false },
      { headline: '[REDACTED: suspected prompt injection in a headline from Spam]', summary: '', source: 'Spam', date: '2026-10-08', lexicon_score: 0, label: 'neutral', injection_suspected: true },
    ],
  } as NewsResponse;

  it('shows redacted injections distinctly and says how many were removed', () => {
    render(<NewsPanel news={news} />);
    expect(screen.getByText('Apple beats estimates')).toBeInTheDocument();
    expect(screen.getByText(/REDACTED/)).toBeInTheDocument();
    expect(screen.getByText(/1 headline\(s\) were redacted/)).toBeInTheDocument();
  });

  it('shows an honest empty state, not a blank box', () => {
    render(<NewsPanel news={null} />);
    expect(screen.getByText('No headlines found')).toBeInTheDocument();
  });

  it('shows a loading skeleton while fetching', () => {
    render(<NewsPanel news={null} loading />);
    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
  });
});

describe('List alignment', () => {
  it('gives the header and every row the same column template so numbers line up', () => {
    const cols = 'grid-cols-[1fr_6rem_6rem]';
    render(
      <List cols={cols} headers={[{ label: 'Name' }, { label: 'Price', align: 'right' }, { label: 'Day', align: 'right' }]}>
        <ListRow>
          <Cell>AAPL</Cell>
          <Cell align="right" num>
            $340.97
          </Cell>
          <Cell align="right" num>
            +1.2%
          </Cell>
        </ListRow>
      </List>,
    );
    const rows = screen.getAllByRole('row');
    expect(rows).toHaveLength(2);
    rows.forEach(r => expect(r.className).toContain(cols));
    expect(screen.getByText('$340.97').className).toContain('tnum');
    expect(screen.getByText('$340.97').className).toContain('text-right');
  });

  it('makes clickable rows keyboard operable', () => {
    const onClick = vi.fn();
    render(
      <List cols="grid-cols-[1fr]">
        <ListRow onClick={onClick}>
          <Cell>NVDA</Cell>
        </ListRow>
      </List>,
    );
    const row = screen.getByRole('row');
    fireEvent.keyDown(row, { key: 'Enter' });
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe('Segmented', () => {
  function Harness() {
    const [v, setV] = useState<'a' | 'b' | 'c'>('a');
    return <Segmented<'a' | 'b' | 'c'> options={[{ value: 'a', label: 'One' }, { value: 'b', label: 'Two' }, { value: 'c', label: 'Three' }]} value={v} onChange={setV} ariaLabel="Demo" />;
  }

  it('is a labelled tablist with one selected tab and arrow-key navigation that wraps', () => {
    render(<Harness />);
    expect(screen.getByRole('tablist', { name: 'Demo' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'One' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(screen.getByRole('tab', { name: 'One' }), { key: 'ArrowRight' });
    expect(screen.getByRole('tab', { name: 'Two' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Two' }), { key: 'ArrowLeft' });
    fireEvent.keyDown(screen.getByRole('tab', { name: 'One' }), { key: 'ArrowLeft' });
    expect(screen.getByRole('tab', { name: 'Three' })).toHaveAttribute('aria-selected', 'true');
  });
});

describe('ConfirmButton', () => {
  it('never acts on the first click: it asks, names the consequence, and only then runs', async () => {
    const { ConfirmButton } = await import('@/components/kit/ConfirmButton');
    const onConfirm = vi.fn();
    render(
      <ConfirmButton title="Delete this AAPL trade?" description="This cannot be undone." confirmLabel="Delete trade" onConfirm={onConfirm}>
        <button>Delete</button>
      </ConfirmButton>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(await screen.findByText('Delete this AAPL trade?')).toBeInTheDocument();
    expect(screen.getByText('This cannot be undone.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Keep it' }));
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
