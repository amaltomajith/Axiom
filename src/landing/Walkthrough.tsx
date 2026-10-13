import { useRef, useState } from 'react';
import { AnimatePresence, motion, useMotionValueEvent, useScroll } from 'motion/react';
import { describeEvent } from '@/components/AgentTraceDrawer';
import { ClaimList } from '@/components/MemoPanel';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DefList } from '@/components/kit/DefList';
import { frac, ratingLabel, ratingTone, TONE_TEXT } from '@/lib/format';
import { spring, useReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/utils';
import { snapshot } from './data';

const STEPS = [
  { id: 'gather', title: 'Gather', text: 'Two analysts call open tools for prices, indicators, filings and news. Every result is saved with an id.' },
  { id: 'debate', title: 'Debate', text: 'They argue both sides. Each claim must cite those ids, and every number is checked against them.' },
  { id: 'guard', title: 'Guard', text: 'Code, not the model, caps the rating when analysts disagree, evidence is thin, or no backtest shows an edge.' },
  { id: 'approve', title: 'Approve', text: 'Agents only propose actions. You see the exact payload first, and each step runs at most once.' },
  { id: 'score', title: 'Score', text: 'Every memo is stored, then scored against what the price actually did.' },
] as const;

const STANCE = { bullish: 'success', bearish: 'destructive', neutral: 'neutral', insufficient_data: 'warning' } as const;

function Gather() {
  const lines = snapshot.events
    .filter(e => ['tool_call', 'tool_result'].includes(e.type) && e.agent !== 'Risk Guard')
    .slice(0, 12)
    .map(describeEvent)
    .filter((l): l is NonNullable<ReturnType<typeof describeEvent>> => l !== null);
  return (
    <ul className="space-y-2.5 p-5 sm:p-6" aria-label="Recorded tool calls">
      {lines.map(l => (
        <li key={l.key} className="grid grid-cols-[7.5rem_1fr] gap-x-3 text-small sm:grid-cols-[9rem_1fr]">
          <span className="truncate font-medium text-foreground/80">{l.agent}</span>
          <span className={cn('min-w-0 break-words font-mono text-caption', l.tone === 'ok' ? 'text-foreground' : 'text-muted-foreground')}>{l.text}</span>
        </li>
      ))}
    </ul>
  );
}

function Debate() {
  const { memo, evidence, findings } = snapshot.result;
  return (
    <div className="space-y-5 p-5 sm:p-6">
      <div>
        <h4 className="mb-2 text-small font-semibold">Bull case</h4>
        <ClaimList claims={memo.bull_case.slice(0, 2)} result={{ evidence }} />
      </div>
      <div>
        <h4 className="mb-2 text-small font-semibold">Bear case</h4>
        <ClaimList claims={memo.bear_case.slice(0, 2)} result={{ evidence }} />
      </div>
      <div className="flex flex-wrap gap-2 border-t border-border pt-4">
        {findings.map(f => (
          <Badge key={f.agent} variant={STANCE[f.stance]}>{`${f.agent}: ${f.stance.replace('_', ' ')} ${frac(f.confidence, 0)}`}</Badge>
        ))}
      </div>
    </div>
  );
}

function Guard() {
  const draft = snapshot.events.find(e => e.type === 'memo_draft')?.data;
  const final = snapshot.events.find(e => e.type === 'final')?.data;
  const ran = snapshot.events.filter(e => e.type === 'guardrail');
  const finalTone = ratingTone(String(final?.rating));
  return (
    <div className="space-y-5 p-5 sm:p-6">
      <DefList
        items={[
          { label: 'The model wrote', value: `${ratingLabel(String(draft?.rating))} at ${frac(Number(draft?.conviction), 0)}` },
          { label: 'After the policy checks', value: <span className={TONE_TEXT[finalTone]}>{`${ratingLabel(String(final?.rating))} at ${frac(Number(final?.conviction), 0)}`}</span> },
        ]}
      />
      <div>
        <h4 className="mb-2 text-small font-semibold">Rules enforced on every memo</h4>
        <ul className="space-y-1.5 text-small text-muted-foreground">
          <li>Analysts disagree: the rating becomes Hold.</li>
          <li>Strong ratings need agreement and a backtest edge.</li>
          <li>Thin evidence caps conviction at 50%.</li>
          <li>Unknown numbers and unknown sources are rejected.</li>
        </ul>
      </div>
      {ran.length > 0 && (
        <div className="border-t border-border pt-4">
          <h4 className="mb-2 text-small font-semibold">Fired during this run</h4>
          <ul className="space-y-1.5 text-caption text-muted-foreground">
            {ran.map(e => (
              <li key={e.seq}>
                <span className="font-mono text-foreground">{String(e.data.name)}</span>: {String(e.data.detail)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Approve() {
  const plan = snapshot.approval.plan;
  const sheet = plan?.steps.find(s => s.kind === 'sheet_row');
  return (
    <div className="space-y-4 p-5 sm:p-6">
      <p className="text-caption text-muted-foreground">{snapshot.approval.source}</p>
      <ul className="divide-y divide-border rounded-md border border-border text-small">
        {plan?.steps.map(s => (
          <li key={s.idempotency_key} className="px-3.5 py-2.5">
            {s.title}
          </li>
        ))}
      </ul>
      {sheet && (
        <div>
          <p className="mb-1.5 text-caption text-muted-foreground">Exactly what the spreadsheet step would write</p>
          <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-sm bg-muted p-3 font-mono text-caption">{JSON.stringify((sheet.preview as { values: unknown[] }).values)}</pre>
        </div>
      )}
      <div className="flex gap-2" aria-hidden>
        <Button size="sm" tabIndex={-1}>Approve and run</Button>
        <Button size="sm" variant="ghost" tabIndex={-1}>Reject</Button>
      </div>
      <p className="text-caption text-muted-foreground">A preview of the approval screen. Nothing here can send anything.</p>
    </div>
  );
}

function Score() {
  const { scorecard, result } = snapshot;
  const m = result.memo;
  return (
    <div className="space-y-5 p-5 sm:p-6">
      <DefList
        items={[
          { label: 'Theses recorded', value: String(scorecard.n_scored + scorecard.n_pending) },
          { label: 'Scored so far', value: String(scorecard.n_scored) },
          { label: 'This memo', value: `${snapshot.ticker}, ${ratingLabel(m.rating)}, ${frac(m.conviction, 0)}` },
          { label: 'Scored after', value: `${m.horizon_days} trading days` },
        ]}
      />
      <p className="rounded-md bg-muted px-3.5 py-3 text-small text-muted-foreground">{scorecard.sample_note}</p>
    </div>
  );
}

const VISUALS = [Gather, Debate, Guard, Approve, Score];

function Panel({ index }: { index: number }) {
  const Visual = VISUALS[index];
  return (
    <div className="surface overflow-hidden shadow-md" aria-live="polite">
      <div className="flex items-center justify-between border-b border-border px-5 py-3.5 sm:px-6">
        <p className="text-small font-semibold">{STEPS[index].title}</p>
        <p className="text-caption text-muted-foreground">Recorded run, {snapshot.ticker}</p>
      </div>
      <Visual />
    </div>
  );
}

/**
 * Pinned scroll story (Motion useScroll, no scroll listeners). The pin exists to keep the visual in view while the
 * steps change, which is the one place motion carries meaning. Phones and reduced-motion users get a plain stack.
 */
export function Walkthrough() {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  const [active, setActive] = useState(0);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end end'] });
  useMotionValueEvent(scrollYProgress, 'change', v => {
    const next = Math.min(STEPS.length - 1, Math.max(0, Math.floor(v * STEPS.length)));
    setActive(prev => (prev === next ? prev : next));
  });

  const header = (
    <div className="max-w-[60ch]">
      <h2 className="text-h1">How a run works</h2>
      <p className="mt-3 text-body text-muted-foreground">Five steps. Each is visible while it happens and kept afterwards.</p>
    </div>
  );

  const stacked = (
    <div className={cn('space-y-12', !reduce && 'lg:hidden')}>
      {STEPS.map((s, i) => (
        <div key={s.id} className="space-y-4">
          <div>
            <h3 className="text-h2">{s.title}</h3>
            <p className="mt-1.5 max-w-[52ch] text-body text-muted-foreground">{s.text}</p>
          </div>
          <Panel index={i} />
        </div>
      ))}
    </div>
  );

  return (
    <section id="how" className="mx-auto max-w-[1200px] px-4 py-24 sm:px-6 sm:py-32">
      {header}
      <div className="mt-12">{stacked}</div>
      {!reduce && (
        <div ref={ref} className="relative hidden h-[420dvh] lg:block">
          <div className="sticky top-24 grid h-[calc(100dvh-8rem)] grid-cols-12 items-center gap-10">
            <ol className="col-span-5 space-y-1" aria-label="Steps">
              {STEPS.map((s, i) => (
                <li key={s.id} aria-current={i === active ? 'step' : undefined}>
                  <div className={cn('rounded-xl px-5 py-4 transition-[background-color,opacity] duration-200', i === active ? 'bg-muted' : 'opacity-55')}>
                    <h3 className="text-h3">{s.title}</h3>
                    <p className="mt-1.5 text-small text-muted-foreground">{s.text}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="col-span-7">
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={active}
                  initial={{ opacity: 0, y: 12, filter: 'blur(4px)' }}
                  animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                  exit={{ opacity: 0, y: -8, filter: 'blur(4px)' }}
                  transition={spring.snappy}
                >
                  <Panel index={active} />
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
