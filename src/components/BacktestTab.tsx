import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { BarChart3, Loader2, Play } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Cell, List, ListRow } from '@/components/kit/List';
import { DefList } from '@/components/kit/DefList';
import { EmptyState } from '@/components/kit/EmptyState';
import { Segmented } from '@/components/kit/Segmented';
import { SkeletonBlock } from '@/components/kit/Skeleton';
import { Section } from '@/components/kit/Surface';
import { useChartTheme } from '@/hooks/useChartTheme';
import { api } from '@/lib/api';
import { frac, num } from '@/lib/format';
import type { BacktestResponse, Metrics, Verdict } from '@/lib/types';
import { cn } from '@/lib/utils';

type StrategyId = 'sma_cross' | 'macd_trend' | 'rsi_reversion' | 'walk_forward';

const STRATEGIES: { value: StrategyId; label: string }[] = [
  { value: 'sma_cross', label: 'Moving-average cross' },
  { value: 'macd_trend', label: 'MACD trend' },
  { value: 'rsi_reversion', label: 'RSI reversion' },
  { value: 'walk_forward', label: 'Walk-forward model' },
];

/** Plain-language verdicts. "No edge" is an honest result, not an error, so it is not coloured as one. */
const VERDICT: Record<Verdict, { title: string; variant: 'success' | 'warning' | 'neutral'; text: string }> = {
  edge_detected: { title: 'Edge detected', variant: 'success', text: 'text-success' },
  unproven: { title: 'Unproven', variant: 'warning', text: 'text-warning' },
  no_edge: { title: 'No edge over buy-and-hold', variant: 'neutral', text: 'text-foreground' },
  insufficient_data: { title: 'Not enough data to judge', variant: 'neutral', text: 'text-muted-foreground' },
};

const ROWS: { label: string; get: (m: Metrics) => string }[] = [
  { label: 'Total return', get: m => frac(m.total_return, 1, true) },
  { label: 'Annualised return', get: m => frac(m.cagr, 1, true) },
  { label: 'Sharpe ratio', get: m => num(m.sharpe) },
  { label: 'Sortino ratio', get: m => num(m.sortino) },
  { label: 'Worst drawdown', get: m => frac(m.max_drawdown, 1) },
  { label: 'Time in the market', get: m => frac(m.exposure, 0) },
  { label: 'Trading days', get: m => String(m.n_days) },
];

export function BacktestTab({ ticker }: { ticker: string }) {
  const t = useChartTheme();
  const [strategy, setStrategy] = useState<StrategyId>('sma_cross');
  const [armed, setArmed] = useState<string | null>(null);
  const key = `${ticker}:${strategy}`;

  const { data, isFetching, error } = useQuery<BacktestResponse>({
    queryKey: ['backtest', ticker, strategy],
    queryFn: () => (strategy === 'walk_forward' ? api.walkForward(ticker) : api.backtest(ticker, strategy)),
    enabled: armed === key,
    staleTime: 5 * 60_000,
    retry: false,
  });

  const verdict = data ? VERDICT[data.verdict] : null;
  const ci = data?.sharpe_diff_ci95;
  const tick = { fill: t.axis, fontSize: 12, fontFamily: t.mono };

  return (
    <div className="space-y-6">
      <Section
        title={`Backtest ${ticker}`}
        description="About four years of daily bars, next-bar execution, 10 bps costs, always compared with buy-and-hold"
        actions={
          <Button onClick={() => setArmed(key)} disabled={isFetching}>
            {isFetching ? <Loader2 className="animate-spin" /> : <Play />}
            {isFetching ? 'Running…' : 'Run backtest'}
          </Button>
        }
      >
        <div className="border-t border-border px-5 py-4 sm:px-6">
          <Segmented<StrategyId> options={STRATEGIES} value={strategy} onChange={setStrategy} ariaLabel="Strategy" size="sm" scroll />
        </div>
      </Section>

      {error && (
        <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-small text-destructive">
          {(error as Error).message}
        </div>
      )}

      {!data && !isFetching && !error && (
        <div className="surface">
          <EmptyState icon={BarChart3} title="Pick a strategy and run it" description="You will get a verdict, an equity curve against buy-and-hold, and the exact assumptions used." />
        </div>
      )}

      {isFetching && !data && (
        <div className="surface space-y-4 p-6" role="status" aria-label="Running backtest">
          <SkeletonBlock className="h-6 w-56" />
          <SkeletonBlock className="h-[300px] w-full" />
        </div>
      )}

      {data && verdict && (
        <>
          <section className="surface px-5 py-5 sm:px-6" aria-label="Verdict">
            <Badge variant={verdict.variant}>{data.verdict.replace('_', ' ')}</Badge>
            <h2 className={cn('mt-2 text-h1', verdict.text)}>{verdict.title}</h2>
            <p className="mt-1.5 max-w-[65ch] text-body text-muted-foreground">{data.message}</p>
            <p className="tnum mt-3 text-small text-muted-foreground">
              Sharpe difference against buy-and-hold: {num(data.sharpe_diff)} (95% bootstrap interval {ci?.[0] == null ? 'not available' : `${num(ci[0])} to ${num(ci[1])}`}).
            </p>
          </section>

          <Section title="Growth of $1" description="Strategy against buy-and-hold over the same days">
            <div className="border-t border-border px-2 pb-3 pt-4 sm:px-4">
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={data.equity_curve} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={t.grid} vertical={false} />
                  <XAxis dataKey="date" tick={tick} tickFormatter={(v: string) => v.slice(2, 7)} tickLine={false} axisLine={false} minTickGap={36} tickMargin={8} />
                  <YAxis tick={tick} tickFormatter={(v: number) => v.toFixed(1)} tickLine={false} axisLine={false} width={40} domain={['auto', 'auto']} orientation="right" />
                  <Tooltip
                    contentStyle={{ background: t.surface, border: `1px solid ${t.border}`, borderRadius: 10, fontSize: 12, fontFamily: t.mono, color: t.text }}
                    labelStyle={{ color: t.axis }}
                    formatter={(v: number) => v.toFixed(3)}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} iconType="plainline" />
                  <Line type="monotone" dataKey="benchmark" name="Buy and hold" stroke={t.benchmark} strokeWidth={1.75} dot={false} />
                  <Line type="monotone" dataKey="strategy" name="Strategy" stroke={t.accent} strokeWidth={2.25} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Section>

          <Section title="Numbers">
            <List cols="grid-cols-[1fr_6.5rem_6.5rem] sm:grid-cols-[1fr_8rem_8rem]" headers={[{ label: 'Metric' }, { label: 'Strategy', align: 'right' }, { label: 'Buy and hold', align: 'right' }]}>
              {ROWS.map(r => (
                <ListRow key={r.label}>
                  <Cell className="text-muted-foreground">{r.label}</Cell>
                  <Cell align="right" num className="font-medium">
                    {r.get(data.metrics)}
                  </Cell>
                  <Cell align="right" num>
                    {r.get(data.benchmark_metrics)}
                  </Cell>
                </ListRow>
              ))}
            </List>
          </Section>

          {data.model_skill && (
            <Section title="Out-of-sample model skill" description="Judged only on days the model never saw">
              <div className="border-t border-border px-5 py-3 sm:px-6">
                <DefList
                  items={[
                    { label: 'R-squared against a zero forecast', value: String(data.model_skill.oos_r2_vs_zero) },
                    { label: 'Direction accuracy', value: frac(data.model_skill.directional_accuracy, 1) },
                    { label: 'Always guessing the majority direction', value: frac(data.model_skill.naive_majority_accuracy, 1) },
                    { label: 'Chance of this beating the majority guess', value: String(data.model_skill.directional_p_value_vs_naive) },
                    { label: 'Out-of-sample days', value: String(data.model_skill.n_oos) },
                  ]}
                />
                <p className="mt-2 text-caption text-muted-foreground">{data.model_skill.interpretation}.</p>
              </div>
            </Section>
          )}
          <p className="px-1 text-caption text-muted-foreground">{data.assumptions}. Past performance does not predict future results.</p>
        </>
      )}
    </div>
  );
}
