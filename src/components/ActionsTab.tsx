import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CircleAlert, CircleCheck, CircleDashed, Loader2, ScrollText, ShieldCheck } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ConfirmButton } from '@/components/kit/ConfirmButton';
import { EmptyState } from '@/components/kit/EmptyState';
import { SkeletonRows } from '@/components/kit/Skeleton';
import { Section } from '@/components/kit/Surface';
import { useToast } from '@/hooks/use-toast';
import { api, ApiError } from '@/lib/api';
import { ratingLabel, ratingTone, timeAgo } from '@/lib/format';
import type { ActionPlan, ActionStep } from '@/lib/types';

const STEP_ICON = {
  done: <CircleCheck className="h-4 w-4 text-success" aria-label="Done" />,
  failed: <CircleAlert className="h-4 w-4 text-destructive" aria-label="Failed" />,
  skipped: <CircleDashed className="h-4 w-4 text-muted-foreground" aria-label="Skipped" />,
  pending: <CircleDashed className="h-4 w-4 text-warning" aria-label="Waiting for approval" />,
} as const;

const STATUS_VARIANT = { proposed: 'warning', executed: 'success', partial: 'warning', failed: 'destructive', rejected: 'neutral' } as const;
const RATING_VARIANT = { gain: 'success', loss: 'destructive', warn: 'warning', neutral: 'neutral' } as const;

type Kind = 'approve' | 'reject' | 'retry';

function Step({ step }: { step: ActionStep }) {
  return (
    <li className="flex items-start gap-3 px-5 py-3 sm:px-6">
      <span className="mt-0.5">{STEP_ICON[step.status]}</span>
      <div className="min-w-0 flex-1">
        <p className="text-small">{step.title}</p>
        {step.error && <p className="mt-0.5 text-caption text-destructive">{step.error}</p>}
        <details className="mt-1">
          <summary className="w-fit cursor-pointer text-caption text-muted-foreground hover:text-foreground">Exactly what will be written</summary>
          <pre className="mt-1.5 max-h-44 overflow-auto whitespace-pre-wrap break-words rounded-sm bg-muted p-2.5 font-mono text-caption leading-relaxed">{JSON.stringify(step.preview, null, 2)}</pre>
        </details>
      </div>
    </li>
  );
}

function PlanCard({ plan, onAction, busy }: { plan: ActionPlan; onAction: (kind: Kind, id: string) => void; busy: boolean }) {
  const live = plan.executor === 'composio';
  const retryable = plan.status === 'partial' || plan.status === 'failed';
  return (
    <section className="surface overflow-hidden" aria-label={`${plan.ticker} action plan`}>
      <header className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 sm:px-6">
        <div className="flex items-center gap-2.5">
          <span className="font-mono text-h3">{plan.ticker}</span>
          <Badge variant={RATING_VARIANT[ratingTone(plan.rating)]}>{ratingLabel(plan.rating)}</Badge>
          <span className="text-caption text-muted-foreground">{timeAgo(plan.created_at)}</span>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={live ? 'destructive' : 'neutral'}>{live ? 'Live: writes to your apps' : 'Dry run: nothing is sent'}</Badge>
          <Badge variant={STATUS_VARIANT[plan.status]}>{plan.status}</Badge>
        </div>
      </header>
      <ul className="divide-y divide-border border-t border-border">
        {plan.steps.map(s => (
          <Step key={s.idempotency_key} step={s} />
        ))}
      </ul>
      {(plan.status === 'proposed' || retryable) && (
        <footer className="flex flex-wrap gap-2 border-t border-border px-5 py-3 sm:px-6">
          {plan.status === 'proposed' ? (
            <>
              <Button size="sm" disabled={busy} onClick={() => onAction('approve', plan.id)}>
                {busy && <Loader2 className="animate-spin" />}
                Approve and run
              </Button>
              <ConfirmButton title={`Reject the ${plan.ticker} plan?`} description="Nothing will be written. The plan stays in History as rejected and cannot be approved later." confirmLabel="Reject plan" onConfirm={() => onAction('reject', plan.id)}>
                <Button size="sm" variant="ghost" disabled={busy}>
                  Reject
                </Button>
              </ConfirmButton>
            </>
          ) : (
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => onAction('retry', plan.id)}>
              Retry the failed steps
            </Button>
          )}
        </footer>
      )}
    </section>
  );
}

export function ActionsTab() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [busyId, setBusyId] = useState<string | null>(null);
  const { data: plans = [], isLoading } = useQuery({ queryKey: ['actions'], queryFn: api.actions, refetchInterval: 15_000 });

  const mutation = useMutation({
    mutationFn: ({ kind, id }: { kind: Kind; id: string }) => api[kind](id),
    onMutate: ({ id }) => setBusyId(id),
    onSettled: () => {
      setBusyId(null);
      qc.invalidateQueries({ queryKey: ['actions'] });
      qc.invalidateQueries({ queryKey: ['trades'] });
    },
    onError: (e: unknown) => {
      const needsToken = e instanceof ApiError && (e.status === 401 || e.status === 403);
      toast({
        title: needsToken ? 'API token required' : 'Action failed',
        description: needsToken ? `${(e as ApiError).message}. Set the token with the key icon in the header.` : e instanceof Error ? e.message : 'Unknown error',
        variant: 'destructive',
      });
    },
  });

  const open = plans.filter(p => p.status === 'proposed');
  const history = plans.filter(p => p.status !== 'proposed');
  const act = (kind: Kind, id: string) => mutation.mutate({ kind, id });

  return (
    <div className="space-y-6">
      <div className="surface-quiet flex gap-3 px-5 py-4">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
        <p className="max-w-[70ch] text-small text-muted-foreground">
          Agents only <span className="font-medium text-foreground">propose</span> actions. Nothing is written until you approve it here, each step runs at most once, and the exact payload is shown first. Axiom paper trades only: there is no brokerage connection.
        </p>
      </div>

      {isLoading && (
        <div className="surface">
          <SkeletonRows rows={3} />
        </div>
      )}
      {!isLoading && plans.length === 0 && (
        <div className="surface">
          <EmptyState icon={ScrollText} title="No action plans yet" description="A confident buy or sell analysis proposes a plan here for your approval." />
        </div>
      )}

      {open.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-h3">Awaiting approval</h2>
          {open.map(p => (
            <PlanCard key={p.id} plan={p} busy={busyId === p.id} onAction={act} />
          ))}
        </div>
      )}
      {history.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-h3">History</h2>
          {history.map(p => (
            <PlanCard key={p.id} plan={p} busy={busyId === p.id} onAction={act} />
          ))}
        </div>
      )}
    </div>
  );
}
