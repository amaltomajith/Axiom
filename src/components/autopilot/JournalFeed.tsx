import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link2, Link2Off, ScrollText } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/kit/EmptyState';
import { Segmented } from '@/components/kit/Segmented';
import { SkeletonRows } from '@/components/kit/Skeleton';
import { Section } from '@/components/kit/Surface';
import { trader } from '@/lib/api';
import { CitationChip } from '@/components/MemoPanel';
import { ratingLabel } from '@/lib/format';
import type { DeskReview, JournalEntry, JournalKind } from '@/lib/types';
import { cn } from '@/lib/utils';
import { TRADER_KEY, shortTime } from './useTrader';

type Variant = 'default' | 'solid' | 'neutral' | 'warning' | 'destructive' | 'outline';

const KIND: Record<JournalKind, { label: string; variant: Variant }> = {
  entry: { label: 'Bought', variant: 'default' },
  exit: { label: 'Sold', variant: 'outline' },
  stop: { label: 'Stop-loss', variant: 'warning' },
  blocked: { label: 'Blocked', variant: 'destructive' },
  proposal: { label: 'Proposal', variant: 'warning' },
  tournament: { label: 'Strategy check', variant: 'neutral' },
  halt: { label: 'Halt', variant: 'destructive' },
  kill: { label: 'Kill switch', variant: 'destructive' },
  resume: { label: 'Resumed', variant: 'default' },
  autonomy: { label: 'Autonomy', variant: 'default' },
  note: { label: 'Note', variant: 'neutral' },
  contract: { label: 'Contract graded', variant: 'default' },
  shadow: { label: 'Shadow trade', variant: 'neutral' },
  veto: { label: 'Vetoed', variant: 'warning' },
  flag: { label: 'Flagged', variant: 'destructive' },
};

const ALERT: { label: string; variant: Variant } = { label: 'Alert', variant: 'warning' };

type Filter = 'all' | 'trades' | 'guardrails';
const TRADES: JournalKind[] = ['entry', 'exit', 'stop', 'contract', 'shadow', 'proposal'];
const GUARDRAILS: JournalKind[] = ['blocked', 'halt', 'kill', 'resume', 'veto', 'flag', 'autonomy'];

function Row({ e }: { e: JournalEntry }) {
  const k = e.kind === 'note' && e.facts.alert ? ALERT : (KIND[e.kind] ?? KIND.note);
  const desk = e.facts.desk as DeskReview | undefined;
  return (
    <li className="px-5 py-3 sm:px-6">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={k.variant}>{k.label}</Badge>
        {e.symbol && <span className="font-mono text-small font-medium">{e.symbol}</span>}
        <span className="tnum text-caption text-muted-foreground">{shortTime(e.ts)}</span>
        <span className="ml-auto font-mono text-caption text-muted-foreground" title={`hash ${e.hash}`}>
          #{e.seq}
        </span>
      </div>
      <p className="mt-1.5 max-w-[80ch] text-small leading-relaxed">{e.text}</p>
      {desk?.rating && (
        <p className="mt-1.5 text-caption text-muted-foreground">
          Desk review: {ratingLabel(desk.rating)}, conviction {desk.conviction?.toFixed(2) ?? 'n/a'}.{desk.evidence?.length ? ' Evidence:' : ''}
          {(desk.evidence ?? []).map(id => (
            <CitationChip key={id} id={id} result={{ evidence: desk.sources ?? {} }} />
          ))}
        </p>
      )}
      {Object.keys(e.facts).length > 0 && (
        <details className="mt-1">
          <summary className="w-fit cursor-pointer text-caption text-muted-foreground hover:text-foreground">Facts behind this entry</summary>
          <pre className="mt-1.5 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-sm bg-muted p-2.5 font-mono text-caption leading-relaxed">{JSON.stringify(e.facts, null, 2)}</pre>
        </details>
      )}
    </li>
  );
}

/** The plain-language journal, newest first, with the hash-chain check that proves nothing was edited. */
export function JournalFeed({ session, className }: { session: string; className?: string }) {
  const [filter, setFilter] = useState<Filter>('all');
  const journal = useQuery({
    queryKey: [TRADER_KEY, 'journal', session],
    queryFn: () => trader.journal(session, 300),
    refetchInterval: 15_000,
  });
  const chain = useQuery({
    queryKey: [TRADER_KEY, 'verify', session],
    queryFn: () => trader.verify(session),
    refetchInterval: 30_000,
  });

  const rows = [...(journal.data ?? [])].reverse().filter(e => filter === 'all' || (filter === 'trades' ? TRADES : GUARDRAILS).includes(e.kind));

  return (
    <Section
      className={cn('flex flex-col', className)}
      title="Journal"
      description="Every decision in plain language, including the trades it did not take"
      actions={
        chain.data &&
        (chain.data.ok ? (
          <Badge variant="default" title={`Chain head ${chain.data.head ?? ''}`}>
            <Link2 className="h-3.5 w-3.5" /> {chain.data.n} entries, chain intact
          </Badge>
        ) : (
          <Badge variant="destructive" title={chain.data.why}>
            <Link2Off className="h-3.5 w-3.5" /> Chain broken at #{chain.data.broken_at}
          </Badge>
        ))
      }
    >
      <div className="border-t border-border px-5 py-2.5 sm:px-6">
        <Segmented<Filter>
          options={[
            { value: 'all', label: 'Everything' },
            { value: 'trades', label: 'Trades' },
            { value: 'guardrails', label: 'Guardrails' },
          ]}
          value={filter}
          onChange={setFilter}
          ariaLabel="Journal filter"
        />
      </div>
      {journal.isLoading ? (
        <SkeletonRows rows={5} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={ScrollText}
          title="Nothing journaled yet"
          description="Start the Autopilot or run the Time Machine; every decision lands here."
          className="flex-1 justify-center border-t border-border"
        />
      ) : (
        <ol className="max-h-[640px] min-h-0 flex-1 divide-y divide-border overflow-y-auto border-t border-border lg:max-h-none">
          {rows.map(e => (
            <Row key={`${e.session}-${e.seq}`} e={e} />
          ))}
        </ol>
      )}
    </Section>
  );
}
