import { useQuery } from '@tanstack/react-query';
import { Check, CircleDashed, Loader2, Minus, Users, X } from 'lucide-react';
import { CitationChip } from '@/components/MemoPanel';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/kit/EmptyState';
import { Section } from '@/components/kit/Surface';
import { trader } from '@/lib/api';
import { frac } from '@/lib/format';
import type { DeskStatus, JournalEntry } from '@/lib/types';
import { cn } from '@/lib/utils';
import { deskSteps, gateRows, type StepState } from './deskModel';
import { TRADER_KEY, shortTime } from './useTrader';

function StepIcon({ state }: { state: StepState }) {
  const Icon = state === 'done' ? Check : state === 'working' ? Loader2 : state === 'failed' ? Minus : CircleDashed;
  return (
    <span
      className={cn(
        'mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border',
        state === 'done' ? 'border-primary/30 bg-primary/10 text-primary' : state === 'working' ? 'border-primary/30 text-primary' : 'border-border text-muted-foreground',
      )}
    >
      <Icon aria-hidden className={cn('h-3.5 w-3.5', state === 'working' && 'animate-spin')} />
    </span>
  );
}

function Agents({ desk }: { desk: DeskStatus }) {
  const latest = Object.entries(desk.runs).sort((a, b) => b[1].started_at - a[1].started_at)[0];
  if (!latest) {
    return (
      <p className="px-5 py-6 text-small text-muted-foreground sm:px-6">No review yet. The four agents step in the next time a strategy wants to buy, and each step shows up here as it happens.</p>
    );
  }
  const [symbol, run] = latest;
  const running = desk.reviewing.includes(symbol);
  const steps = deskSteps(run.events, run.review, running);
  const r = run.review;
  return (
    <div>
      <p className="flex flex-wrap items-center gap-2 px-5 pt-4 text-small sm:px-6">
        <span className="font-mono font-medium">{symbol}</span>
        <span className="text-muted-foreground">review started {shortTime(run.started_at)}</span>
        {running && <Badge variant="default">Reviewing now</Badge>}
        {!running && r?.error && <Badge variant="warning">No view, the rules decided</Badge>}
      </p>
      <ol className="px-5 py-3 sm:px-6" aria-label="Agent steps">
        {steps.map(s => (
          <li key={s.name} className="flex gap-3 py-2.5">
            <StepIcon state={s.state} />
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-center gap-2 text-small font-medium">
                {s.name}
                {s.badge && <Badge variant={s.badge.tone}>{s.badge.text}</Badge>}
              </p>
              <p className="mt-0.5 text-caption text-muted-foreground">{s.result ?? s.job}</p>
            </div>
          </li>
        ))}
      </ol>
      {r && !r.error && r.evidence.length > 0 && (
        <p className="border-t border-border px-5 py-3 text-caption text-muted-foreground sm:px-6">
          Evidence the plan cites:
          {r.evidence.map(id => (
            <CitationChip key={id} id={id} result={{ evidence: r.sources }} />
          ))}
        </p>
      )}
      {r?.error && <p className="border-t border-border px-5 py-3 text-caption text-muted-foreground sm:px-6">Why there was no view: {r.error}.</p>}
    </div>
  );
}

function Gate({ entry, limit }: { entry: JournalEntry | undefined; limit: string }) {
  if (!entry) {
    return <p className="px-5 py-6 text-small text-muted-foreground sm:px-6">No order has reached the gate yet. When one does, each check and its result appear here.</p>;
  }
  const { rows, also } = gateRows(entry, limit);
  const passed = rows.every(x => x.ok !== false) && also.every(c => c.ok);
  return (
    <div>
      <p className="flex flex-wrap items-center gap-2 px-5 pt-4 text-small sm:px-6">
        <span className="font-mono font-medium">{entry.symbol}</span>
        <span className="text-muted-foreground">{shortTime(entry.ts)}</span>
        <Badge variant={passed ? 'success' : 'destructive'}>{passed ? (entry.kind === 'proposal' ? 'Passed, waiting for you' : 'Passed') : 'Blocked'}</Badge>
      </p>
      <ul className="px-5 py-3 sm:px-6" aria-label="Policy gate checks">
        {rows.map(x => (
          <li key={x.label} className="flex gap-3 py-2">
            <span
              className={cn(
                'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full',
                x.ok === null ? 'bg-muted text-muted-foreground' : x.ok ? 'bg-success/15 text-success' : 'bg-destructive/15 text-destructive',
              )}
            >
              {x.ok === null ? <Minus aria-hidden className="h-3 w-3" /> : x.ok ? <Check aria-hidden className="h-3 w-3" /> : <X aria-hidden className="h-3 w-3" />}
              <span className="sr-only">{x.ok === null ? 'Not reached' : x.ok ? 'Passed' : 'Failed'}</span>
            </span>
            <div className="min-w-0">
              <p className="text-small font-medium">{x.label}</p>
              <p className="text-caption text-muted-foreground">{x.detail}</p>
            </div>
          </li>
        ))}
      </ul>
      {also.length > 0 && (
        <p className="border-t border-border px-5 py-3 text-caption text-muted-foreground sm:px-6">
          Also checked: allowed symbol, fresh prices, trades per day, cool-down after a stop and permission level. {also.every(c => c.ok) ? 'All passed.' : `Failed: ${also.find(c => !c.ok)?.detail}`}
        </p>
      )}
    </div>
  );
}

/** The desk at work: each agent's step as it happens, then the gate every order has to pass. */
export function DeskRun({ session, lossLimit, className }: { session: string; lossLimit?: number; className?: string }) {
  const live = session === 'live';
  const desk = useQuery({
    queryKey: [TRADER_KEY, 'desk'],
    queryFn: trader.desk,
    enabled: live,
    refetchInterval: q => (q.state.data?.reviewing.length ? 3_000 : 20_000),
    retry: false,
  });
  const journal = useQuery({
    queryKey: [TRADER_KEY, 'journal', session],
    queryFn: () => trader.journal(session, 300),
    refetchInterval: 15_000,
  });
  const gated = [...(journal.data ?? [])].reverse().find(e => Array.isArray(e.facts.checks) && ['entry', 'proposal', 'blocked'].includes(e.kind));
  const limit = frac(lossLimit ?? 0.025, 1);
  const d = desk.data;
  const nothing = !gated && !(d?.enabled && Object.keys(d.runs).length);

  return (
    <Section
      className={className}
      title="Live run"
      description="Four agents review each trade idea, then plain code decides if it may go ahead"
      actions={d?.enabled && d.runs_left != null ? <Badge variant="neutral">{d.runs_left} reviews left this hour</Badge> : undefined}
    >
      {nothing && !d?.enabled ? (
        <EmptyState
          icon={Users}
          title="Nothing to show yet"
          description="When a strategy wants to buy, the order check appears here. Start the backend with TRADER_BRAIN=desk to have the four agents review each idea first."
          className="border-t border-border"
        />
      ) : (
        <div className="grid border-t border-border lg:grid-cols-2 lg:divide-x lg:divide-border">
          <div>
            <h3 className="px-5 pt-4 text-caption font-medium uppercase tracking-[0.12em] text-muted-foreground sm:px-6">The agents</h3>
            {!live ? (
              <p className="px-5 py-6 text-small text-muted-foreground sm:px-6">Replays use the rules only. An AI is never replayed over the past, because it may remember what happened next.</p>
            ) : d?.enabled ? (
              <Agents desk={d} />
            ) : (
              <p className="px-5 py-6 text-small text-muted-foreground sm:px-6">
                The four-agent review is switched off, so the rules decide alone. Start the backend with TRADER_BRAIN=desk to turn it on.
              </p>
            )}
          </div>
          <div className="border-t border-border lg:border-t-0">
            <h3 className="px-5 pt-4 text-caption font-medium uppercase tracking-[0.12em] text-muted-foreground sm:px-6">Policy gate, six checks in plain code</h3>
            <Gate entry={gated} limit={limit} />
          </div>
        </div>
      )}
    </Section>
  );
}
