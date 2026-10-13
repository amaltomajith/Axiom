import { CartesianGrid, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { useChartTheme } from '@/hooks/useChartTheme';
import { reveal, useReducedMotion } from '@/lib/motion';
import { motion } from 'motion/react';
import { cn } from '@/lib/utils';
import { snapshot } from './data';

/**
 * The message the faithfulness checker sends a model that cites the wrong source for a figure
 * (format from backend/axiom/agents/faithfulness.py; the situation happened in a live run on NVDA).
 */
const REPAIR = "number '$269.14 billion' not found in cited evidence ['T2']; that figure appears in T3 (fetch_sec_filing_summary): cite the correct evidence id";

function Cell({ className, delay = 0, children, label }: { className?: string; delay?: number; children: React.ReactNode; label: string }) {
  const reduce = useReducedMotion();
  return (
    <motion.article {...reveal(reduce, delay)} aria-label={label} className={cn('surface flex flex-col overflow-hidden p-6 sm:p-7', className)}>
      {children}
    </motion.article>
  );
}

const H = ({ children }: { children: React.ReactNode }) => <h3 className="text-h2">{children}</h3>;
const P = ({ children, className }: { children: React.ReactNode; className?: string }) => <p className={cn('mt-2 max-w-[48ch] text-small text-muted-foreground', className)}>{children}</p>;

function MiniCurve() {
  const t = useChartTheme();
  return (
    <div className="mt-5 flex-1 min-h-[150px]" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={snapshot.backtest.equity_curve} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={t.grid} vertical={false} />
          <XAxis dataKey="date" hide />
          <YAxis hide domain={['auto', 'auto']} />
          <Line dataKey="benchmark" stroke={t.benchmark} strokeWidth={1.5} dot={false} isAnimationActive={false} />
          <Line dataKey="strategy" stroke={t.accent} strokeWidth={2.25} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Five cells for five claims, varied on purpose: plain, chart, tinted, dotted, wide. */
export function Honest() {
  const { evals, backtest, scorecard, approval } = snapshot;
  const sheet = approval.plan?.steps.find(s => s.kind === 'sheet_row');
  return (
    <section id="evidence" className="mx-auto max-w-[1200px] px-4 pb-24 sm:px-6 sm:pb-32">
      <div className="max-w-[60ch]">
        <h2 className="text-h1">Built to be honest</h2>
        <p className="mt-3 text-body text-muted-foreground">Five places where Axiom picks a true answer over an impressive one.</p>
      </div>

      <div className="mt-12 grid gap-4 md:grid-cols-6">
        <Cell label="Numbers have receipts" className="md:col-span-4">
          <H>Numbers have receipts</H>
          <P>If a claim cites the wrong source, the model is told which source holds the figure and tries again. A number that exists nowhere is removed.</P>
          <pre className="mt-5 whitespace-pre-wrap break-words rounded-md bg-muted p-4 font-mono text-caption leading-relaxed text-muted-foreground">{REPAIR}</pre>
          <p className="mt-2 text-caption text-muted-foreground">What the checker tells a model that cited the wrong source.</p>
        </Cell>

        <Cell label="A backtest can say no" delay={0.05} className="md:col-span-2 md:row-span-2">
          <H>A backtest can say no</H>
          <P>
            {snapshot.ticker}, 20/50 moving-average cross, four years. {backtest.message}
          </P>
          <MiniCurve />
          <p className="mt-3 text-caption text-muted-foreground">
            <span className="text-primary">Strategy</span> against <span>buy and hold</span>, with costs.
          </p>
        </Cell>

        <Cell label="Attacks are measured" delay={0.1} className="bg-primary/10 md:col-span-2">
          <H>Attacks are measured</H>
          <div className="mt-4 flex items-baseline gap-5">
            <div>
              <p className="tnum text-display leading-none">{evals.control_obeyed.replace('/', ' of ')}</p>
              <p className="mt-2 text-caption text-muted-foreground">obeyed a planted instruction with no defences</p>
            </div>
          </div>
          <p className="mt-4 text-small">
            With defences on, <span className="font-medium">{evals.injection.split('/')[0]} of {evals.injection.split('/')[1]}</span> attack runs ended with a normal call.
          </p>
        </Cell>

        <Cell label="You approve every action" delay={0.15} className="dot-grid md:col-span-2">
          <H>You approve every action</H>
          <P>Nothing is written until you say so.</P>
          {sheet && <pre className="mt-4 overflow-hidden whitespace-pre-wrap break-words rounded-md bg-card/90 p-3 font-mono text-caption">{JSON.stringify((sheet.preview as { values: unknown[] }).values)}</pre>}
        </Cell>

        <Cell label="Track record" delay={0.2} className="md:col-span-6">
          <div className="grid gap-6 md:grid-cols-12 md:items-end">
            <div className="md:col-span-7">
              <H>A track record that admits its size</H>
              <P>Every memo is scored against the price after its horizon, then compared with an always-bullish guess so luck does not pass for skill.</P>
            </div>
            <p className="rounded-md bg-muted px-4 py-3.5 text-small md:col-span-5">{scorecard.sample_note}</p>
          </div>
        </Cell>
      </div>
    </section>
  );
}
