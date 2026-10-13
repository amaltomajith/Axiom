import { useState } from 'react';
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { Briefcase, Loader2, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Cell, List, ListRow } from '@/components/kit/List';
import { ConfirmButton } from '@/components/kit/ConfirmButton';
import { EmptyState } from '@/components/kit/EmptyState';
import { SkeletonRows } from '@/components/kit/Skeleton';
import { Section } from '@/components/kit/Surface';
import { useToast } from '@/hooks/use-toast';
import { api, ApiError } from '@/lib/api';
import { money } from '@/lib/format';
import type { PaperTrade } from '@/lib/types';
import { cn } from '@/lib/utils';

const pnl = (t: PaperTrade, price: number | undefined): number => ((t.exit_price ?? price ?? t.entry_price) - t.entry_price) * t.quantity;
const signed = (v: number) => `${v >= 0 ? '+' : ''}${money(v)}`;

export function PaperTradingTab({ ticker }: { ticker: string }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [quantity, setQuantity] = useState('10');
  const { data: trades = [], isLoading } = useQuery({ queryKey: ['trades'], queryFn: api.trades });

  const open = [...new Set(trades.filter(t => t.exit_price == null).map(t => t.ticker))];
  const prices = useQueries({ queries: open.map(t => ({ queryKey: ['mark', t], queryFn: () => api.ohlcv(t, 5), staleTime: 5 * 60_000, retry: false })) });
  const mark: Record<string, number | undefined> = {};
  open.forEach((t, i) => {
    const bars = prices[i]?.data?.bars;
    mark[t] = bars?.[bars.length - 1]?.close;
  });

  const onError = (e: unknown) =>
    toast({ title: e instanceof ApiError && e.status === 401 ? 'API token required' : 'That did not work', description: e instanceof Error ? e.message : 'Unknown error', variant: 'destructive' });
  const refresh = () => qc.invalidateQueries({ queryKey: ['trades'] });
  const qty = Math.max(1, parseInt(quantity) || 1);
  const buy = useMutation({ mutationFn: () => api.buy(ticker, qty), onSuccess: refresh, onError });
  const close = useMutation({ mutationFn: api.closeTrade, onSuccess: refresh, onError });
  const del = useMutation({ mutationFn: api.deleteTrade, onSuccess: refresh, onError });
  const total = trades.reduce((s, t) => s + pnl(t, mark[t.ticker]), 0);

  return (
    <div className="space-y-6">
      <Section title={`Buy ${ticker}`} description="Simulated. Fills at the last daily close, with no brokerage connection">
        <form
          className="flex flex-wrap items-end gap-3 border-t border-border px-5 py-4 sm:px-6"
          onSubmit={e => {
            e.preventDefault();
            buy.mutate();
          }}
        >
          <div className="w-32">
            <label htmlFor="qty" className="mb-1.5 block text-caption text-muted-foreground">
              Shares
            </label>
            <Input id="qty" name="shares" autoComplete="off" type="number" min={1} inputMode="numeric" value={quantity} onChange={e => setQuantity(e.target.value)} className="tnum" />
          </div>
          <Button type="submit" disabled={buy.isPending}>
            {buy.isPending && <Loader2 className="animate-spin" />}
            Buy {qty} {ticker}
          </Button>
        </form>
      </Section>

      <Section
        title="Portfolio"
        actions={<span className={cn('tnum text-h3', total >= 0 ? 'text-success' : 'text-destructive')}>{signed(total)}</span>}
        description="Profit and loss across open and closed trades"
      >
        {isLoading ? (
          <SkeletonRows rows={3} className="border-t border-border" />
        ) : trades.length === 0 ? (
          <div className="border-t border-border">
            <EmptyState icon={Briefcase} title="No trades yet" description="Buy a position above, or approve an agent's plan on the Actions tab." />
          </div>
        ) : (
          <List
            cols="grid-cols-[1fr_auto_auto] md:grid-cols-[5.5rem_1fr_6.5rem_6.5rem_7rem_auto]"
            headers={[
              { label: 'Ticker' },
              { label: 'Position', hideBelow: 'md' },
              { label: 'Entry', align: 'right', hideBelow: 'md' },
              { label: 'Now', align: 'right', hideBelow: 'md' },
              { label: 'Profit and loss', align: 'right' },
              { label: '' },
            ]}
          >
            {trades.map(t => {
              const now = t.exit_price ?? mark[t.ticker];
              const p = pnl(t, mark[t.ticker]);
              return (
                <ListRow key={t.id}>
                  <Cell className="flex items-center gap-2">
                    <span className="font-mono text-body font-medium">{t.ticker}</span>
                    <Badge variant={t.exit_price != null ? 'neutral' : 'default'}>{t.exit_price != null ? 'Closed' : 'Open'}</Badge>
                  </Cell>
                  <Cell hideBelow="md" className="text-muted-foreground">
                    {t.quantity} shares{t.thesis_id ? ', from an agent plan' : ''}
                  </Cell>
                  <Cell hideBelow="md" align="right" num>
                    {money(t.entry_price)}
                  </Cell>
                  <Cell hideBelow="md" align="right" num>
                    {money(now)}
                  </Cell>
                  <Cell align="right" num className={cn('font-medium', p >= 0 ? 'text-success' : 'text-destructive')}>
                    {signed(p)}
                  </Cell>
                  <Cell align="right" className="flex items-center justify-end gap-1">
                    {t.exit_price == null && (
                      <Button variant="ghost" size="xs" onClick={() => close.mutate(t.id)}>
                        Close
                      </Button>
                    )}
                    <ConfirmButton title={`Delete this ${t.ticker} trade?`} description="It is removed from your paper portfolio and its profit and loss. This cannot be undone." confirmLabel="Delete trade" onConfirm={() => del.mutate(t.id)}>
                      <Button variant="ghost" size="icon-sm" aria-label={`Delete ${t.ticker} trade`}>
                        <Trash2 />
                      </Button>
                    </ConfirmButton>
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
