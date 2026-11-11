import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { ArrowRight } from 'lucide-react';
import { Line, LineChart, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useChartTheme } from '@/hooks/useChartTheme';
import { frac, num, shortDate } from '@/lib/format';
import { spring, useReducedMotion } from '@/lib/motion';
import report from '../../docs/backtest-report.json';
import { REPO } from './data';

const BACKTEST_DOC = `${REPO}/blob/main/docs/backtest-report.md`;

/** The real Time Machine report (docs/backtest-report.json, written by `python -m axiom.trading backtest`). */
function ReportPreview() {
  const t = useChartTheme();
  const { agent, benchmark, verdict, contracts, risk_events: risk, period, universe } = report;
  const blocked = Object.values(risk.blocked as Record<string, number>).reduce((a, b) => a + b, 0);
  const rows: { label: string; a: string; b: string }[] = [
    { label: 'Return', a: frac(agent.total_return, 1, true), b: frac(benchmark.total_return, 1, true) },
    { label: 'Sharpe', a: num(agent.sharpe, 2), b: num(benchmark.sharpe, 2) },
    { label: 'Worst drawdown', a: frac(agent.max_drawdown, 1), b: frac(benchmark.max_drawdown, 1) },
  ];
  return (
    <div className="surface overflow-hidden shadow-md">
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 pb-1 pt-5 sm:px-6">
        <div>
          <p className="text-small font-medium">Time Machine backtest</p>
          <p className="text-caption text-muted-foreground">
            {universe.length} symbols, {period.years} years, the live engine replayed bar by bar
          </p>
        </div>
        <Badge variant={verdict.verdict === 'edge_detected' ? 'success' : 'warning'} className="font-mono">
          {verdict.verdict}
        </Badge>
      </div>
      <div className="h-[200px] px-2 pt-2 sm:px-3" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={report.curve} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
            <XAxis dataKey="date" hide />
            <YAxis hide domain={['auto', 'auto']} />
            <Line dataKey="benchmark" stroke={t.benchmark} strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Line dataKey="agent" stroke={t.accent} strokeWidth={2.25} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="border-t border-border px-5 py-4 sm:px-6">
        <table className="w-full text-small">
          <thead>
            <tr className="text-caption text-muted-foreground">
              <th className="pb-1.5 text-left font-normal" scope="col">
                <span className="sr-only">Metric</span>
              </th>
              <th className="pb-1.5 text-right font-normal text-primary" scope="col">
                Autopilot
              </th>
              <th className="pb-1.5 text-right font-normal" scope="col">
                Buy and hold
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.label}>
                <th className="py-1 text-left font-normal text-muted-foreground" scope="row">
                  {r.label}
                </th>
                <td className="tnum py-1 text-right font-medium">{r.a}</td>
                <td className="tnum py-1 text-right">{r.b}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="tnum mt-3 text-caption text-muted-foreground">
          {contracts.n} trade contracts graded, Brier {num(contracts.brier, 3)}. {risk.stop_outs} stop-outs, {blocked} entries blocked by the risk kernel, {risk.daily_loss_halts} daily loss halts.
        </p>
      </div>
    </div>
  );
}

/** Hero: headline, one sentence, two actions, one real preview. Nothing else competes with them. */
export function Hero() {
  const reduce = useReducedMotion();
  const item = (delay: number) =>
    reduce
      ? { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { duration: 0.2, delay } }
      : { initial: { opacity: 0, y: 16 }, animate: { opacity: 1, y: 0 }, transition: { ...spring.default, delay } };

  return (
    <section className="mx-auto grid min-h-[min(calc(100dvh-4rem),44rem)] max-w-[1200px] items-center gap-12 px-4 pb-16 pt-12 sm:px-6 lg:grid-cols-12 lg:gap-10">
      <div className="lg:col-span-5">
        <motion.h1 {...item(0)} className="text-display">
          A trading agent that earns autonomy.
        </motion.h1>
        <motion.p {...item(0.08)} className="mt-5 max-w-[34ch] text-h3 font-normal leading-snug text-muted-foreground">
          It trades paper money inside risk rules it cannot override, states its odds before every trade, and gets graded.
        </motion.p>
        <motion.div {...item(0.16)} className="mt-8 flex flex-wrap items-center gap-3">
          <Button asChild size="lg">
            <Link to="/app">
              Open terminal <ArrowRight />
            </Link>
          </Button>
          <Button asChild size="lg" variant="secondary">
            <a href={BACKTEST_DOC} target="_blank" rel="noreferrer">
              Read the backtest
            </a>
          </Button>
        </motion.div>
      </div>
      <motion.div {...item(0.2)} className="lg:col-span-7">
        <ReportPreview />
        <p className="mt-3 px-1 text-caption text-muted-foreground">
          The real report, generated {shortDate(report.generated_at)}. {verdict(report.verdict.message)} It is shown here anyway.
        </p>
      </motion.div>
    </section>
  );
}

const verdict = (m: string) => (m.endsWith('.') ? m : `${m}.`);
