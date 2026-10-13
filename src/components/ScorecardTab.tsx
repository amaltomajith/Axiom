import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Info, Loader2, Target } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Cell, List, ListRow } from '@/components/kit/List';
import { DefList } from '@/components/kit/DefList';
import { EmptyState } from '@/components/kit/EmptyState';
import { SkeletonBlock, SkeletonRows } from '@/components/kit/Skeleton';
import { Stat, StatRow } from '@/components/kit/Stat';
import { Section } from '@/components/kit/Surface';
import { useToast } from '@/hooks/use-toast';
import { api, ApiError } from '@/lib/api';
import { frac, num, pct, ratingLabel, ratingTone, shortDate } from '@/lib/format';
import type { RateBucket, Thesis } from '@/lib/types';
import { cn } from '@/lib/utils';

const RATING_VARIANT = { gain: 'success', loss: 'destructive', warn: 'warning', neutral: 'neutral' } as const;

const buckets = (data: Record<string, RateBucket>) =>
  Object.entries(data).map(([label, v]) => ({ label, value: v.hit_rate == null ? `n/a (${v.n})` : `${frac(v.hit_rate, 0)} of ${v.n}` }));

function outcome(t: Thesis): { text: string; cls: string } {
  const o = t.outcome;
  if (!o) return { text: `Pending, ${t.horizon_days} day horizon`, cls: 'text-muted-foreground' };
  const vs = o.excess_ret_pct == null ? '' : `, ${pct(o.excess_ret_pct, 1, true)} vs SPY`;
  const cls = o.direction_hit === 1 ? 'text-success' : o.direction_hit === 0 ? 'text-destructive' : 'text-muted-foreground';
  const tag = o.direction_hit === 1 ? 'Right: ' : o.direction_hit === 0 ? 'Wrong: ' : '';
  return { text: `${tag}${pct(o.ret_pct, 1, true)}${vs}`, cls };
}

export function ScorecardTab() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { data: card, isLoading } = useQuery({ queryKey: ['scorecard'], queryFn: api.scorecard });
  const { data: theses = [], isLoading: thesesLoading } = useQuery({ queryKey: ['theses'], queryFn: api.theses });
  const score = useMutation({
    mutationFn: api.scoreNow,
    onSuccess: r => {
      toast({ title: 'Scoring complete', description: `${r.scored} scored, ${r.not_yet_due} not yet due${r.failed ? `, ${r.failed} failed` : ''}.` });
      qc.invalidateQueries({ queryKey: ['scorecard'] });
      qc.invalidateQueries({ queryKey: ['theses'] });
    },
    onError: (e: unknown) => toast({ title: e instanceof ApiError && e.status === 401 ? 'API token required' : 'Could not score', description: e instanceof Error ? e.message : 'Unknown error', variant: 'destructive' }),
  });

  return (
    <div className="space-y-6">
      <Section
        title="Track record"
        description="Every memo is stored as a thesis, then scored against what the price did"
        actions={
          <Button variant="secondary" onClick={() => score.mutate()} disabled={score.isPending}>
            {score.isPending && <Loader2 className="animate-spin" />}
            Score matured theses
          </Button>
        }
      >
        {isLoading || !card ? (
          <div className="border-t border-border px-5 py-5 sm:px-6">
            <SkeletonBlock className="h-16 w-full" />
          </div>
        ) : (
          <>
            <div className={cn('flex gap-2.5 border-t border-border px-5 py-3 text-small sm:px-6', card.sufficient_sample ? 'text-muted-foreground' : 'bg-warning/10 text-warning')} role="note">
              <Info className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{card.sample_note}</span>
            </div>
            <StatRow className="border-t border-border">
              <Stat label="Scored, pending" value={`${card.n_scored}, ${card.n_pending}`} />
              <Stat label="Direction hit rate" value={frac(card.direction_hit_rate, 0)} sub={`Always bullish would score ${frac(card.baseline_up_rate, 0)}`} />
              <Stat label="Beat SPY" value={frac(card.beat_benchmark_rate, 0)} sub={card.mean_excess_return_pct == null ? undefined : `Average excess ${pct(card.mean_excess_return_pct, 2, true)}`} />
              <Stat label="Brier skill" value={num(card.brier_skill_vs_coinflip)} sub="Above 0 beats a coin flip" />
            </StatRow>
          </>
        )}
      </Section>

      {card && (Object.keys(card.by_conviction).length > 0 || Object.keys(card.by_agent).length > 0) && (
        <div className="grid gap-6 md:grid-cols-2">
          <Section title="By conviction" description="Hit rate when the memo was this sure">
            <div className="border-t border-border px-5 py-1 sm:px-6">
              <DefList items={buckets(card.by_conviction)} />
            </div>
          </Section>
          <Section title="By analyst" description="Each analyst's own stance, scored">
            <div className="border-t border-border px-5 py-1 sm:px-6">
              <DefList items={buckets(card.by_agent)} />
            </div>
          </Section>
        </div>
      )}

      <Section title="Theses">
        {thesesLoading ? (
          <SkeletonRows rows={3} className="border-t border-border" />
        ) : theses.length === 0 ? (
          <div className="border-t border-border">
            <EmptyState icon={Target} title="No theses yet" description="Run an analysis on the Analyze tab. Each memo is recorded here and scored once its horizon passes." />
          </div>
        ) : (
          <List
            cols="grid-cols-[4.5rem_1fr] md:grid-cols-[6.5rem_5rem_7rem_4.5rem_1fr]"
            headers={[{ label: 'Date', hideBelow: 'md' }, { label: 'Ticker' }, { label: 'Rating', hideBelow: 'md' }, { label: 'Conviction', align: 'right', hideBelow: 'md' }, { label: 'Outcome', align: 'right' }]}
          >
            {theses.map(t => {
              const o = outcome(t);
              return (
                <ListRow key={t.id} className="max-md:grid-cols-[4.5rem_1fr]">
                  <Cell hideBelow="md" num className="text-muted-foreground">
                    {shortDate(t.issue_date)}
                  </Cell>
                  <Cell className="font-mono text-body font-medium">{t.ticker}</Cell>
                  <Cell hideBelow="md">
                    <Badge variant={RATING_VARIANT[ratingTone(t.rating)]}>{ratingLabel(t.rating)}</Badge>
                  </Cell>
                  <Cell hideBelow="md" align="right" num className="text-muted-foreground">
                    {frac(t.conviction, 0)}
                  </Cell>
                  <Cell align="right" num className={cn('truncate', o.cls)}>
                    {o.text}
                  </Cell>
                </ListRow>
              );
            })}
          </List>
        )}
      </Section>
    </div>
  );
}
