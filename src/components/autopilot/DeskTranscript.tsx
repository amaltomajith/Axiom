import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Drawer } from 'vaul';
import { Check, FileText, Minus, X } from 'lucide-react';
import { CitationChip } from '@/components/MemoPanel';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SkeletonBlock } from '@/components/kit/Skeleton';
import { useIsMobile } from '@/hooks/use-mobile';
import { trader } from '@/lib/api';
import { ratingLabel } from '@/lib/format';
import type { DeskClaim, DeskRun, EvidenceRef } from '@/lib/types';
import { cn } from '@/lib/utils';
import { STANCE, TRIGGER, outcomeLabel, transcript, type ToolStep } from './deskModel';
import { TRADER_KEY, shortTime } from './useTrader';

type Sources = Record<string, EvidenceRef>;

function Claims({ claims, sources }: { claims: DeskClaim[]; sources: Sources }) {
  return (
    <ul className="mt-2 space-y-1.5">
      {claims.map((c, i) => (
        <li key={i} className="text-small leading-relaxed">
          {c.text}
          {c.evidence.map(id => (
            <CitationChip key={id} id={id} result={{ evidence: sources }} />
          ))}
        </li>
      ))}
    </ul>
  );
}

function Tools({ tools }: { tools: ToolStep[] }) {
  if (!tools.length) return null;
  return (
    <ul className="mt-2 space-y-1.5" aria-label="Tools called">
      {tools.map((t, i) => (
        <li key={i} className="flex items-start gap-2 text-caption">
          <span
            className={cn(
              'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full',
              t.ok === null ? 'bg-muted text-muted-foreground' : t.ok ? 'bg-success/15 text-success' : 'bg-destructive/15 text-destructive',
            )}
          >
            {t.ok === null ? <Minus aria-hidden className="h-2.5 w-2.5" /> : t.ok ? <Check aria-hidden className="h-2.5 w-2.5" /> : <X aria-hidden className="h-2.5 w-2.5" />}
          </span>
          <span className="min-w-0 break-words">
            <span className="font-mono text-foreground">{t.tool}</span>
            <span className="font-mono text-muted-foreground">({t.args})</span>
            <span className="text-muted-foreground"> {t.result}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function Part({ step, title, who, children }: { step: number; title: string; who?: string; children: React.ReactNode }) {
  return (
    <section className="grid grid-cols-[1.75rem_1fr] gap-x-3 border-t border-border px-5 py-4 first:border-t-0">
      <span className="tnum flex h-7 w-7 items-center justify-center rounded-full border border-border text-caption text-muted-foreground" aria-hidden>
        {step}
      </span>
      <div className="min-w-0">
        <h3 className="flex flex-wrap items-baseline gap-x-2 text-small font-medium">
          {title}
          {who && <span className="text-caption font-normal text-muted-foreground">{who}</span>}
        </h3>
        {children}
      </div>
    </section>
  );
}

const muted = 'mt-1.5 text-small leading-relaxed text-muted-foreground';

/** One desk review from start to finish, in the order it happened. */
export function TranscriptBody({ run }: { run: DeskRun }) {
  const t = transcript(run);
  const r = run.review;
  const sources: Sources = { ...(r.sources ?? {}), ...(run.sources ?? {}) };
  const out = outcomeLabel(run.outcome, Boolean(run.strategy));
  const plan = run.plan as { shares?: number; stop_price?: number | null; position_pct?: number | null; notes?: string[] } | undefined;
  let n = 0;
  return (
    <div>
      <Part step={++n} title="Why this review started">
        <p className={muted}>
          {TRIGGER[run.trigger] ?? run.trigger}
          {run.strategy ? `, on the ${run.strategy.replace(/_/g, ' ')} strategy` : ', with no strategy signalling a buy'}. Started {shortTime(run.started_at)}
          {run.finished_at ? `, took ${Math.max(1, Math.round(run.finished_at - run.started_at))} seconds` : ''}.
        </p>
      </Part>

      {t.analysts.map(a => (
        <Part key={a.name} step={++n} title={a.name} who={a.job}>
          <Tools tools={a.tools} />
          {a.finding ? (
            <>
              <p className="mt-3 flex flex-wrap items-center gap-2 text-small">
                <Badge variant={(STANCE[a.finding.stance] ?? STANCE.neutral).tone}>{(STANCE[a.finding.stance] ?? STANCE.neutral).text}</Badge>
                <span className="tnum text-caption text-muted-foreground">confidence {Math.round(a.finding.confidence * 100)}%</span>
              </p>
              <p className="mt-2 text-small leading-relaxed">{a.finding.summary}</p>
              <Claims claims={a.finding.claims} sources={sources} />
              {a.finding.caveats.length > 0 && <p className={muted}>Caveats: {a.finding.caveats.join(' ')}</p>}
            </>
          ) : (
            <p className={muted}>{a.failed ? `Could not finish: ${a.failed}` : 'No finding was recorded.'}</p>
          )}
        </Part>
      ))}

      <Part step={++n} title="Risk Guard" who="Code, not a model: measures risk and the size the rules allow">
        <Tools tools={t.risk} />
        {plan && (plan.notes?.length || plan.stop_price != null) ? (
          <p className={muted}>
            {plan.stop_price != null ? `Suggested stop ${plan.stop_price.toLocaleString()}. ` : ''}
            {plan.position_pct != null ? `Position at most ${(plan.position_pct * 100).toFixed(1)}% of equity. ` : ''}
            {(plan.notes ?? []).join(' ')}
          </p>
        ) : (
          !t.risk.length && <p className={muted}>No risk figures were recorded.</p>
        )}
      </Part>

      <Part step={++n} title="Lead Synthesizer" who="Reads every finding and argues both sides">
        {run.memo ? (
          <>
            <div className="mt-2 grid gap-4 sm:grid-cols-2">
              <div>
                <p className="text-caption font-medium uppercase tracking-[0.12em] text-success">The case for</p>
                <Claims claims={run.memo.bull_case} sources={sources} />
              </div>
              <div>
                <p className="text-caption font-medium uppercase tracking-[0.12em] text-destructive">The case against</p>
                <Claims claims={run.memo.bear_case} sources={sources} />
              </div>
            </div>
            {t.draft && t.draft !== r.rating && (
              <p className={muted}>
                First draft: {ratingLabel(t.draft)}. Final: {ratingLabel(r.rating ?? 'NO_CALL')}.
              </p>
            )}
            <p className="mt-3 flex flex-wrap items-center gap-2 text-small">
              <Badge variant="default">{ratingLabel(r.rating ?? 'NO_CALL')}</Badge>
              <span className="tnum text-caption text-muted-foreground">conviction {r.conviction?.toFixed(2) ?? 'n/a'}</span>
            </p>
            <p className="mt-2 text-small leading-relaxed">{r.thesis}</p>
            {run.memo.key_risks.length > 0 && <p className={muted}>Main risks: {run.memo.key_risks.join(' ')}</p>}
            {run.memo.what_would_change_my_mind.length > 0 && <p className={muted}>What would change its mind: {run.memo.what_would_change_my_mind.join(' ')}</p>}
          </>
        ) : (
          <p className={muted}>{r.error ? `No plan was written: ${r.error}.` : 'No plan was recorded.'}</p>
        )}
      </Part>

      <Part step={++n} title="Risk Critic" who="Argues against the plan; the Synthesizer may revise once">
        {r.critic_ok == null ? (
          <p className={muted}>The Critic did not run on this plan.</p>
        ) : r.critic_ok ? (
          <p className={muted}>Found nothing to object to.</p>
        ) : (
          <ul className="mt-2 list-disc space-y-1 pl-4 text-small leading-relaxed">
            {(t.issues.length ? t.issues : r.critic_issues).map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        )}
      </Part>

      <Part step={++n} title="Policy checks" who="Code caps the rating when the evidence is thin">
        {t.guards.length ? (
          <ul className="mt-2 space-y-1 text-small leading-relaxed">
            {t.guards.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        ) : (
          <p className={muted}>No cap was needed.</p>
        )}
      </Part>

      <Part step={++n} title="What the desk did with it">
        <p className="mt-2 flex flex-wrap items-center gap-2 text-small">
          <Badge variant={out.tone}>{out.text}</Badge>
        </p>
        <p className={muted}>{out.detail}</p>
        <p className={muted}>The desk never sets a quantity. Any order still has to pass the six gate checks, and in Supervised mode a human approves it.</p>
      </Part>
    </div>
  );
}

function TranscriptDrawer({ runId, recorded, onClose }: { runId?: string; recorded?: boolean; onClose: () => void }) {
  const mobile = useIsMobile();
  const q = useQuery({
    queryKey: [TRADER_KEY, 'desk-run', recorded ? 'recorded' : runId],
    queryFn: () => (recorded ? trader.deskRecorded() : trader.deskRun(runId as string)),
    retry: false,
    staleTime: 60_000,
  });
  const run = q.data;
  return (
    <Drawer.Root open onOpenChange={o => !o && onClose()} direction={mobile ? 'bottom' : 'right'} shouldScaleBackground={false}>
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-50 bg-background/70" />
        <Drawer.Content
          aria-describedby={undefined}
          className={cn(
            'fixed z-50 flex flex-col bg-card shadow-md outline-none',
            mobile ? 'inset-x-0 bottom-0 h-[90dvh] rounded-t-xl border-t border-border' : 'inset-y-3 right-3 w-[min(720px,calc(100vw-1.5rem))] rounded-xl border border-border',
          )}
        >
          {mobile && <div className="mx-auto mt-2 h-1.5 w-10 rounded-full bg-border" aria-hidden />}
          <header className="flex items-start justify-between gap-4 px-5 pb-3 pt-4">
            <div className="min-w-0">
              <Drawer.Title className="text-h3">Desk review{run ? `, ${run.symbol}` : ''}</Drawer.Title>
              <p className="mt-1 flex flex-wrap items-center gap-2 text-caption text-muted-foreground">
                {run ? `${shortTime(run.started_at)}, ${run.events.length} recorded steps` : 'Loading the review'}
                {run?.recorded && <Badge variant="warning">Recorded earlier, not live</Badge>}
              </p>
            </div>
            <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close review">
              <X />
            </Button>
          </header>
          <div className="flex-1 overflow-y-auto overscroll-contain border-t border-border">
            {q.isLoading && <SkeletonBlock className="m-5 h-64" />}
            {q.isError && <p className="px-5 py-6 text-small text-muted-foreground">{recorded ? 'No recorded review is bundled with this build.' : 'This review is no longer stored.'}</p>}
            {run && <TranscriptBody run={run} />}
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
}

/** A button that opens the full transcript of one desk review (or of the bundled recorded one). */
export function TranscriptLink({ runId, recorded, label, className }: { runId?: string | null; recorded?: boolean; label?: string; className?: string }) {
  const [open, setOpen] = useState(false);
  if (!runId && !recorded) return null;
  return (
    <>
      <Button variant="outline" size="xs" className={className} onClick={() => setOpen(true)}>
        <FileText aria-hidden />
        {label ?? 'Read the full review'}
      </Button>
      {open && <TranscriptDrawer runId={runId ?? undefined} recorded={recorded} onClose={() => setOpen(false)} />}
    </>
  );
}
