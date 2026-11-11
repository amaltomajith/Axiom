import { useQuery } from '@tanstack/react-query';
import { Hand, Wallet } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/kit/EmptyState';
import { Cell, List, ListRow } from '@/components/kit/List';
import { Section } from '@/components/kit/Surface';
import { trader } from '@/lib/api';
import { money, num, timeAgo } from '@/lib/format';
import type { PendingEntry } from '@/lib/types';
import { cn } from '@/lib/utils';
import { strategyLabel } from './labels';
import { TRADER_KEY, useTraderAction } from './useTrader';

const qty = (q: number) => (Number.isInteger(q) ? String(q) : q.toFixed(6).replace(/0+$/, '').replace(/\.$/, ''));

/** Open positions with the stop the broker holds for each one. */
export function Positions({ className }: { className?: string }) {
  const { data = [] } = useQuery({
    queryKey: [TRADER_KEY, 'positions'],
    queryFn: trader.positions,
    refetchInterval: 15_000,
  });
  return (
    <Section className={cn('flex flex-col', className)} title="Positions" description="Every position has a stop-loss held at the broker">
      {data.length === 0 ? (
        <EmptyState icon={Wallet} title="Flat" description="No open positions. Holding cash is a decision too: the journal says why." className="flex-1 justify-center border-t border-border py-10" />
      ) : (
        <List
          cols="grid-cols-[1fr_6rem_6rem] md:grid-cols-[1fr_6rem_7rem_7rem_7rem]"
          headers={[
            { label: 'Symbol' },
            { label: 'Quantity', align: 'right', hideBelow: 'md' },
            { label: 'Price', align: 'right' },
            { label: 'Stop', align: 'right', hideBelow: 'md' },
            { label: 'Unrealized', align: 'right' },
          ]}
        >
          {data.map(p => (
            <ListRow key={p.symbol}>
              <Cell>
                <span className="font-mono font-medium">{p.symbol}</span>
                <span className="block text-caption text-muted-foreground">{strategyLabel(p.strategy)}</span>
              </Cell>
              <Cell num align="right" hideBelow="md">
                {qty(p.qty)}
              </Cell>
              <Cell num align="right">
                {money(p.market_price)}
              </Cell>
              <Cell num align="right" hideBelow="md">
                {money(p.stop_price)}
              </Cell>
              <Cell num align="right" className={cn(p.unrealized_pl > 0 ? 'text-success' : p.unrealized_pl < 0 ? 'text-destructive' : '')}>
                {money(p.unrealized_pl)}
              </Cell>
            </ListRow>
          ))}
        </List>
      )}
    </Section>
  );
}

function Proposal({ p }: { p: PendingEntry }) {
  const approve = useTraderAction(
    () => trader.approve(p.id),
    r => (r.ok ? `Approved: bought ${p.intent.symbol}` : `Blocked on re-check: ${r.reason}`),
  );
  const reject = useTraderAction(
    () => trader.reject(p.id),
    () => 'Rejected',
  );
  const busy = approve.isPending || reject.isPending;
  return (
    <li className="px-5 py-4 sm:px-6">
      <p className="text-small">
        Buy <span className="tnum font-medium">{qty(p.verdict.qty)}</span> <span className="font-mono font-medium">{p.intent.symbol}</span> at about{' '}
        <span className="tnum">{money(p.verdict.price)}</span> ({money(p.verdict.notional)}), stop at <span className="tnum">{money(p.intent.stop_price)}</span>. At risk:{' '}
        <span className="tnum">{money(p.verdict.risk_amount)}</span>.
      </p>
      <p className="mt-1 text-caption text-muted-foreground">
        {strategyLabel(p.intent.strategy)}
        {p.intent.confidence != null ? `, stated confidence ${num(p.intent.confidence * 100, 0)}%` : ''}, proposed {timeAgo(p.created_at)}. {p.decision.reason}
      </p>
      <div className="mt-2.5 flex gap-2">
        <Button size="sm" disabled={busy} onClick={() => approve.mutate(undefined)}>
          Approve
        </Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => reject.mutate(undefined)}>
          Reject
        </Button>
      </div>
      <p className="mt-2 text-caption text-muted-foreground">Approving re-runs every kernel rule at the current price before anything is sent.</p>
    </li>
  );
}

/** SUPERVISED mode: entries wait here for a human. */
export function Approvals({ pending }: { pending: PendingEntry[] }) {
  if (!pending.length) return null;
  return (
    <Section title={`Waiting for approval (${pending.length})`} description="Supervised mode: the agent proposes, a human decides" actions={<Hand className="h-4 w-4 text-warning" />}>
      <ul className="divide-y divide-border border-t border-border">
        {pending.map(p => (
          <Proposal key={p.id} p={p} />
        ))}
      </ul>
    </Section>
  );
}
