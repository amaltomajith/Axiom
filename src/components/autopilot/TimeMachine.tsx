import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Loader2, Play, Square } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Cell, List, ListRow } from '@/components/kit/List';
import { Segmented } from '@/components/kit/Segmented';
import { Section } from '@/components/kit/Surface';
import { useChartTheme } from '@/hooks/useChartTheme';
import { trader } from '@/lib/api';
import { frac, money, num } from '@/lib/format';
import type { ReportMetrics, Verdict } from '@/lib/types';
import { TRADER_KEY, shortDate, useTraderAction } from './useTrader';

const VERDICT: Record<Verdict, { title: string; variant: 'default' | 'warning' | 'neutral' }> = {
  edge_detected: { title: 'Edge detected', variant: 'default' },
  unproven: { title: 'Unproven', variant: 'warning' },
  no_edge: { title: 'No edge over buy-and-hold', variant: 'neutral' },
  insufficient_data: { title: 'Not enough data to judge', variant: 'neutral' },
};

type Speed = 'fast' | 'watch';

/** Replay history through the live engine, then browse that run as its own session. */
export function TimeMachine({ session, onSession }: { session: string; onSession: (s: string) => void }) {
  const [speed, setSpeed] = useState<Speed>('watch');
  const replays = useQuery({
    queryKey: [TRADER_KEY, 'replays'],
    queryFn: trader.replays,
    refetchInterval: q => (q.state.data?.some(r => ['queued', 'fetching', 'running'].includes(r.status)) ? 1500 : 30_000),
  });
  const start = useTraderAction(
    () => trader.replay(1000, speed === 'watch' ? 0.02 : 0),
    r => {
      onSession(r.session);
      return 'Time Machine started';
    },
  );
  const running = (replays.data ?? []).find(r => ['queued', 'fetching', 'running'].includes(r.status));
  const stop = useTraderAction(
    (id: string) => trader.stopReplay(id),
    () => 'Stopping the replay',
  );

  return (
    <Section
      title="Time Machine"
      description="The same engine, kernel and brain replayed over about four years of daily bars, filling at the next bar's open with fees and slippage"
      actions={
        running ? (
          <Button size="sm" variant="secondary" disabled={stop.isPending} onClick={() => stop.mutate(running.id)}>
            <Square /> Stop
          </Button>
        ) : (
          <Button size="sm" disabled={start.isPending} onClick={() => start.mutate(undefined)}>
            {start.isPending ? <Loader2 className="animate-spin" /> : <Play />} Run
          </Button>
        )
      }
    >
      <div className="flex flex-wrap items-center gap-3 border-t border-border px-5 py-3 sm:px-6">
        <Segmented<Speed>
          size="sm"
          options={[
            { value: 'watch', label: 'Watch it trade' },
            { value: 'fast', label: 'As fast as possible' },
          ]}
          value={speed}
          onChange={setSpeed}
          ariaLabel="Replay speed"
        />
        {running && (
          <div className="min-w-[12rem] flex-1">
            <div className="flex justify-between text-caption text-muted-foreground">
              <span>{running.status === 'fetching' ? 'Fetching history' : `Replaying ${running.sim_ts ? shortDate(running.sim_ts) : ''}`}</span>
              <span className="tnum">{Math.round(running.progress * 100)}%</span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={Math.round(running.progress * 100)} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${running.progress * 100}%` }} />
            </div>
          </div>
        )}
      </div>
      {(replays.data ?? []).length > 0 && (
        <List cols="grid-cols-[1fr_auto_auto]" headers={[{ label: 'Run' }, { label: 'Verdict', align: 'right' }, { label: '', align: 'right' }]}>
          <ListRow>
            <Cell>
              <span className="font-medium">Live paper account</span>
              <span className="block text-caption text-muted-foreground">the Autopilot's real forward record</span>
            </Cell>
            <Cell />
            <Cell align="right">
              <Button size="xs" variant={session === 'live' ? 'secondary' : 'ghost'} onClick={() => onSession('live')}>
                {session === 'live' ? 'Viewing' : 'View'}
              </Button>
            </Cell>
          </ListRow>
          {(replays.data ?? []).slice(0, 5).map(r => (
            <ListRow key={r.id}>
              <Cell>
                <span className="font-mono text-small">{r.id}</span>
                <span className="block text-caption text-muted-foreground">
                  {r.symbols.join(', ')}, {r.status}
                  {r.error ? `: ${r.error}` : ''}
                </span>
              </Cell>
              <Cell align="right">{r.verdict ? <Badge variant={VERDICT[r.verdict.verdict].variant}>{r.verdict.verdict.replace('_', ' ')}</Badge> : null}</Cell>
              <Cell align="right">
                <Button size="xs" variant={session === r.session ? 'secondary' : 'ghost'} onClick={() => onSession(r.session)}>
                  {session === r.session ? 'Viewing' : 'View'}
                </Button>
              </Cell>
            </ListRow>
          ))}
        </List>
      )}
    </Section>
  );
}

const ROWS: { label: string; get: (m: ReportMetrics) => string }[] = [
  { label: 'Total return', get: m => frac(m.total_return, 1, true) },
  { label: 'Annualised return', get: m => frac(m.cagr, 1, true) },
  { label: 'Volatility', get: m => frac(m.ann_vol, 1) },
  { label: 'Sharpe ratio', get: m => num(m.sharpe) },
  { label: 'Worst drawdown', get: m => frac(m.max_drawdown, 1) },
];

/** One honest sentence comparing risk and return, computed from the numbers (never hard-coded). */
function compare(a: ReportMetrics, b: ReportMetrics): string {
  const shallower = a.max_drawdown > b.max_drawdown;
  const calmer = a.ann_vol < b.ann_vol;
  const better = a.sharpe > b.sharpe;
  const risk = shallower && calmer ? 'a shallower drawdown and lower volatility than' : shallower ? 'a shallower drawdown than' : calmer ? 'lower volatility than' : 'no less risk than';
  return `The Autopilot had ${risk} buy-and-hold, and ${better ? 'a better' : 'a worse'} risk-adjusted return.`;
}

/** The committed backtest report: the honest verdict against buy-and-hold, with its interval. */
export function ReportView() {
  const t = useChartTheme();
  const { data, error } = useQuery({
    queryKey: [TRADER_KEY, 'report'],
    queryFn: trader.report,
    retry: false,
    staleTime: 5 * 60_000,
  });
  if (error || !data) {
    return (
      <Section title="Backtest report" description="Run `python -m axiom.trading backtest` in backend/ to generate it">
        <p className="border-t border-border px-5 py-4 text-small text-muted-foreground sm:px-6">{error ? (error as Error).message : 'Loading'}</p>
      </Section>
    );
  }
  const v = VERDICT[data.verdict.verdict];
  const ci = data.verdict.sharpe_diff_ci95;
  const tick = { fill: t.axis, fontSize: 12, fontFamily: t.mono };
  const step = Math.max(1, Math.floor(data.curve.length / 300));
  return (
    <Section
      title="Backtest report"
      description={`${data.period.start} to ${data.period.end}, ${data.universe.join(', ')}, ${money(data.start_cash, 0)} start`}
      actions={<Badge variant={v.variant}>{v.title}</Badge>}
    >
      <p className="border-t border-border px-5 py-3 text-small text-muted-foreground sm:px-6">
        {data.verdict.message} Sharpe difference {num(data.verdict.sharpe_diff)} (95% interval {ci[0] == null ? 'n/a' : `${num(ci[0])} to ${num(ci[1])}`}
        ). The LLM brain is excluded on purpose: replaying it over the past would measure its memory, not its judgement.
      </p>
      <div className="px-2 pb-3 sm:px-4">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data.curve.filter((_, i) => i % step === 0)} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={t.grid} vertical={false} />
            <XAxis dataKey="date" tick={tick} tickFormatter={(s: string) => s.slice(2, 7)} tickLine={false} axisLine={false} minTickGap={36} tickMargin={8} />
            <YAxis tick={tick} tickFormatter={(x: number) => `${(x / 1000).toFixed(0)}k`} tickLine={false} axisLine={false} width={44} domain={['auto', 'auto']} orientation="right" />
            <Tooltip
              contentStyle={{
                background: t.surface,
                border: `1px solid ${t.border}`,
                borderRadius: 10,
                fontSize: 12,
                fontFamily: t.mono,
                color: t.text,
              }}
              formatter={(x: number) => money(x, 0)}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} iconType="plainline" />
            <Line type="monotone" dataKey="benchmark" name="Buy and hold" stroke={t.benchmark} strokeWidth={1.75} dot={false} />
            <Line type="monotone" dataKey="agent" name="Autopilot" stroke={t.accent} strokeWidth={2.25} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <List cols="grid-cols-[1fr_6.5rem_6.5rem]" headers={[{ label: 'Metric' }, { label: 'Autopilot', align: 'right' }, { label: 'Buy and hold', align: 'right' }]}>
        {ROWS.map(r => (
          <ListRow key={r.label}>
            <Cell className="text-muted-foreground">{r.label}</Cell>
            <Cell num align="right">
              {r.get(data.agent)}
            </Cell>
            <Cell num align="right">
              {r.get(data.benchmark)}
            </Cell>
          </ListRow>
        ))}
      </List>
      <p className="border-t border-border px-5 py-3 text-caption text-muted-foreground sm:px-6">
        {data.trades.entries} entries, {data.risk_events.stop_outs} stop-losses hit, {data.risk_events.daily_loss_halts} daily-loss halts, fees and slippage {money(data.trades.fees_paid, 0)}.{' '}
        {compare(data.agent, data.benchmark)}
      </p>
    </Section>
  );
}
