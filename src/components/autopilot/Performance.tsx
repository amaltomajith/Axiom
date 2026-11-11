import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { FileCheck2, LineChart as LineIcon } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/kit/EmptyState';
import { Cell, List, ListRow } from '@/components/kit/List';
import { Section } from '@/components/kit/Surface';
import { useChartTheme } from '@/hooks/useChartTheme';
import { trader } from '@/lib/api';
import { money, num, pct } from '@/lib/format';
import type { TradeContract } from '@/lib/types';
import { notTakenLine } from './deskModel';
import { cn } from '@/lib/utils';
import { strategyLabel } from './labels';
import { TRADER_KEY, shortDate, shortTime } from './useTrader';

/** Paper equity against an equal-weight buy-and-hold of the same symbols from the same start. */
export function EquityChart({ session, className }: { session: string; className?: string }) {
  const t = useChartTheme();
  const { data = [] } = useQuery({
    queryKey: [TRADER_KEY, 'equity', session],
    queryFn: () => trader.equity(session),
    refetchInterval: 20_000,
  });
  const step = Math.max(1, Math.floor(data.length / 500));
  const points = data.filter((_, i) => i % step === 0 || i === data.length - 1);
  const tick = { fill: t.axis, fontSize: 12, fontFamily: t.mono };
  const intraday = points.length > 1 && points[points.length - 1].ts - points[0].ts < 10 * 86_400;
  const values = points.flatMap(p => (p.benchmark == null ? [p.equity] : [p.equity, p.benchmark]));
  const span = values.length ? Math.max(...values) - Math.min(...values) : 0;
  // A flat or nearly flat curve would print the same "100k" on every tick: use whole dollars instead.
  const yTick = (v: number) => (span < 5_000 ? money(v, 0) : `${(v / 1000).toFixed(0)}k`);
  return (
    <Section className={cn('flex h-full flex-col', className)} title="Equity against buy-and-hold" description="Same symbols, same starting cash, no risk rules for the benchmark">
      {points.length < 2 ? (
        <EmptyState
          icon={LineIcon}
          title="No equity history yet"
          description="The curve fills in as the Autopilot ticks or a Time Machine run replays history."
          className="flex-1 justify-center border-t border-border py-10"
        />
      ) : (
        <div className="border-t border-border px-2 pb-3 pt-4 sm:px-4">
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={t.grid} vertical={false} />
              <XAxis
                dataKey="ts"
                type="number"
                domain={['dataMin', 'dataMax']}
                tick={tick}
                tickFormatter={(v: number) => (intraday ? shortTime(v) : shortDate(v))}
                tickLine={false}
                axisLine={false}
                minTickGap={48}
                tickMargin={8}
              />
              <YAxis tick={tick} tickFormatter={yTick} tickLine={false} axisLine={false} width={span < 5_000 ? 76 : 44} domain={['auto', 'auto']} orientation="right" />
              <Tooltip
                contentStyle={{
                  background: t.surface,
                  border: `1px solid ${t.border}`,
                  borderRadius: 10,
                  fontSize: 12,
                  fontFamily: t.mono,
                  color: t.text,
                }}
                labelStyle={{ color: t.axis }}
                labelFormatter={(v: number) => shortTime(v)}
                formatter={(v: number) => money(v, 0)}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} iconType="plainline" />
              <Line type="monotone" dataKey="benchmark" name="Buy and hold" stroke={t.benchmark} strokeWidth={1.75} dot={false} connectNulls />
              <Line type="monotone" dataKey="equity" name="Autopilot" stroke={t.accent} strokeWidth={2.25} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Section>
  );
}

const GRADE_VARIANT = {
  A: 'solid',
  B: 'default',
  C: 'warning',
  D: 'destructive',
} as const;

function ContractRow({ c }: { c: TradeContract }) {
  const r = c.result;
  return (
    <ListRow>
      <Cell>
        <span className="font-mono font-medium">{c.symbol}</span>
        {c.shadow && <span className="ml-1.5 text-caption text-muted-foreground">shadow</span>}
        <span
          className="block text-caption text-muted-foreground"
          title={[`${c.strategy}, ${c.source} brain`, c.horizon_bars ? `${c.horizon_bars} bar horizon` : '', c.thesis ?? ''].filter(Boolean).join('. ')}
        >
          {strategyLabel(c.strategy)}
        </span>
      </Cell>
      <Cell num align="right">
        {c.confidence != null ? `${Math.round(c.confidence * 100)}%` : 'n/a'}
      </Cell>
      <Cell num align="right" hideBelow="sm">
        {c.expected_move_pct != null ? pct(c.expected_move_pct, 1, true) : 'n/a'}
      </Cell>
      <Cell num align="right">
        {r?.return_pct != null ? pct(r.return_pct, 2, true) : c.status}
      </Cell>
      <Cell align="right">{r ? <Badge variant={GRADE_VARIANT[r.grade]}>{r.grade}</Badge> : <Badge variant="neutral">{c.status}</Badge>}</Cell>
    </ListRow>
  );
}

/** Trade contracts and calibration: did the agent's stated confidence match what happened? */
export function Contracts({ session, className }: { session: string; className?: string }) {
  const t = useChartTheme();
  const contracts = useQuery({
    queryKey: [TRADER_KEY, 'contracts', session],
    queryFn: () => trader.contracts(session),
    refetchInterval: 30_000,
  });
  const cal = useQuery({
    queryKey: [TRADER_KEY, 'calibration', session],
    queryFn: () => trader.calibration(session),
    refetchInterval: 30_000,
  });
  const all = cal.data?.all;
  const refused = notTakenLine(cal.data?.not_taken?.vetoes);
  const rows = [...(contracts.data ?? [])].sort((a, b) => b.created_at - a.created_at).slice(0, 25);
  const buckets = (all?.buckets ?? []).map(b => ({
    band: `${Math.round(b.lo * 100)} to ${Math.round(b.hi * 100)}%`,
    stated: Math.round(b.mean_confidence * 100),
    actual: Math.round(b.win_rate * 100),
    n: b.n,
  }));
  const tick = { fill: t.axis, fontSize: 12, fontFamily: t.mono };

  return (
    <Section
      className={cn('flex flex-col', className)}
      title="Trade contracts and calibration"
      description="Before each entry the agent states its odds, target and exits. Each contract is graded when it closes."
      actions={all?.brier != null && <Badge variant={all.brier <= 0.25 ? 'default' : 'warning'}>Brier {num(all.brier, 3)}</Badge>}
    >
      {refused && (
        <div className="shrink-0 border-t border-border px-5 py-4 sm:px-6" aria-label="Trades not taken">
          <p className="text-caption font-medium uppercase tracking-[0.12em] text-muted-foreground">Trades not taken</p>
          <p className="mt-1.5 text-small leading-relaxed">{refused}</p>
          {cal.data?.not_taken?.vetoes.avg_return_pct != null && (
            <p className="mt-1 text-caption text-muted-foreground">
              Average result of the refused trades: {cal.data.not_taken.vetoes.avg_return_pct > 0 ? '+' : ''}
              {cal.data.not_taken.vetoes.avg_return_pct.toFixed(2)}%. Refusals are graded apart and never count toward the agent's own record.
            </p>
          )}
        </div>
      )}
      {!all?.n && !rows.length ? (
        <EmptyState
          icon={FileCheck2}
          title="No contracts yet"
          description="The first one opens with the first entry (or the first would-be entry in shadow mode)."
          className="flex-1 justify-center border-t border-border py-10"
        />
      ) : (
        <>
          {all && all.n > 0 && (
            <div className="shrink-0 border-t border-border px-5 py-4 sm:px-6">
              <dl className="grid grid-cols-3 gap-4">
                <div>
                  <dt className="text-caption text-muted-foreground">Graded</dt>
                  <dd className="tnum mt-1 text-h3">
                    {all.n}
                    {all.shadow ? <span className="text-small text-muted-foreground"> ({all.shadow} shadow)</span> : null}
                  </dd>
                </div>
                <div>
                  <dt className="text-caption text-muted-foreground">Ended in profit</dt>
                  <dd className="tnum mt-1 text-h3">{all.win_rate != null ? `${Math.round(all.win_rate * 100)}%` : 'n/a'}</dd>
                </div>
                <div>
                  <dt className="text-caption text-muted-foreground">Stated odds</dt>
                  <dd className="tnum mt-1 text-h3">{all.mean_confidence != null ? `${Math.round(all.mean_confidence * 100)}%` : 'n/a'}</dd>
                </div>
              </dl>
              <div className="mt-4 flex flex-wrap items-center gap-2" aria-label="Grades">
                {(['A', 'B', 'C', 'D'] as const).map(g => (
                  <Badge key={g} variant={GRADE_VARIANT[g]} className="tnum">
                    {g} <span className="opacity-80">{all.grades[g] ?? 0}</span>
                  </Badge>
                ))}
              </div>
              {buckets.length > 0 && (
                <div aria-label="Calibration chart" className="mt-4">
                  <ResponsiveContainer width="100%" height={170}>
                    <BarChart data={buckets} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke={t.grid} vertical={false} />
                      <XAxis dataKey="band" tick={tick} tickLine={false} axisLine={false} />
                      <YAxis tick={tick} domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} tickLine={false} axisLine={false} width={44} orientation="right" />
                      <Tooltip
                        contentStyle={{
                          background: t.surface,
                          border: `1px solid ${t.border}`,
                          borderRadius: 10,
                          fontSize: 12,
                          fontFamily: t.mono,
                          color: t.text,
                        }}
                        formatter={(v: number, name: string) => [`${v}%`, name]}
                      />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Bar dataKey="stated" name="Stated confidence" fill={t.benchmark} radius={[3, 3, 0, 0]} isAnimationActive={false} />
                      <Bar dataKey="actual" name="Actually profitable" fill={t.accent} radius={[3, 3, 0, 0]} isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
              <p className="mt-3 text-caption text-muted-foreground">
                Brier score: 0 is perfect, 0.25 is a coin flip. A is a profit that reached the target, C is a loss closed by the contract's own exit.
              </p>
            </div>
          )}
          {rows.length > 0 && (
            <div className="max-h-[560px] min-h-0 flex-1 overflow-y-auto lg:max-h-none">
              <List
                stickyHeader
                cols="grid-cols-[minmax(0,1fr)_3.5rem_4.5rem_3rem] sm:grid-cols-[minmax(0,1fr)_3.5rem_4.5rem_4.75rem_3rem]"
                headers={[
                  { label: 'Contract' },
                  { label: 'Odds', align: 'right' },
                  { label: 'Target', align: 'right', hideBelow: 'sm' },
                  { label: 'Result', align: 'right' },
                  { label: 'Grade', align: 'right' },
                ]}
              >
                {rows.map(c => (
                  <ContractRow key={c.id} c={c} />
                ))}
              </List>
            </div>
          )}
        </>
      )}
    </Section>
  );
}
