import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { Eye, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Cell, List, ListRow } from '@/components/kit/List';
import { EmptyState } from '@/components/kit/EmptyState';
import { SkeletonRows } from '@/components/kit/Skeleton';
import { Section } from '@/components/kit/Surface';
import { useToast } from '@/hooks/use-toast';
import { api, ApiError } from '@/lib/api';
import { money, num, pct } from '@/lib/format';
import { cn } from '@/lib/utils';

const TREND = { uptrend: 'success', downtrend: 'destructive', sideways: 'warning' } as const;

export function WatchlistTab({ onSelectTicker }: { onSelectTicker: (ticker: string) => void }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { data: items = [], isLoading } = useQuery({ queryKey: ['watchlist'], queryFn: api.watchlist });

  const details = useQueries({
    queries: items.map(i => ({
      queryKey: ['watch-detail', i.ticker],
      queryFn: async () => {
        const [px, regime, ind] = await Promise.all([api.ohlcv(i.ticker, 5), api.regime(i.ticker), api.indicators(i.ticker)]);
        return { px, regime, ind };
      },
      staleTime: 5 * 60_000,
      retry: false,
    })),
  });

  const remove = useMutation({
    mutationFn: api.watchRemove,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
    onError: (e: unknown) => toast({ title: e instanceof ApiError && e.status === 401 ? 'API token required' : 'Could not remove', description: e instanceof Error ? e.message : 'Unknown error', variant: 'destructive' }),
  });

  return (
    <Section title="Watchlist" description="The daily briefing analyses this list">
      {isLoading ? (
        <SkeletonRows rows={3} className="border-t border-border" />
      ) : items.length === 0 ? (
        <div className="border-t border-border">
          <EmptyState icon={Eye} title="Nothing watched yet" description="Use the star next to a ticker to add it here." />
        </div>
      ) : (
        <List
          cols="grid-cols-[1fr_auto_2rem] md:grid-cols-[6rem_1fr_6.5rem_5.5rem_4rem_2rem]"
          headers={[
            { label: 'Ticker' },
            { label: 'Regime', hideBelow: 'md' },
            { label: 'Price', align: 'right', hideBelow: 'md' },
            { label: 'Day', align: 'right', hideBelow: 'md' },
            { label: 'RSI', align: 'right', hideBelow: 'md' },
            { label: '' },
          ]}
        >
          {items.map((item, idx) => {
            const q = details[idx];
            const bars = q?.data?.px.bars ?? [];
            const last = bars[bars.length - 1]?.close;
            const prev = bars[bars.length - 2]?.close;
            const chg = last && prev ? (last / prev - 1) * 100 : null;
            const regime = q?.data?.regime;
            return (
              <ListRow key={item.ticker} onClick={() => onSelectTicker(item.ticker)} aria-label={`Open ${item.ticker}`}>
                <Cell>
                  <span className="font-mono text-body font-medium">{item.ticker}</span>
                  <span className="tnum ml-3 text-small text-muted-foreground md:hidden">{money(last)}</span>
                </Cell>
                <Cell hideBelow="md" className="flex flex-wrap gap-1.5">
                  {regime ? (
                    <>
                      <Badge variant={TREND[regime.trend as keyof typeof TREND] ?? 'neutral'}>{regime.trend}</Badge>
                      <Badge>{`${regime.volatility} volatility`}</Badge>
                    </>
                  ) : q?.isError ? (
                    <span className="text-caption text-destructive">No data</span>
                  ) : null}
                </Cell>
                <Cell hideBelow="md" align="right" num>
                  {money(last)}
                </Cell>
                <Cell hideBelow="md" align="right" num className={cn(chg != null && (chg >= 0 ? 'text-success' : 'text-destructive'))}>
                  {chg == null ? 'n/a' : pct(chg, 2, true)}
                </Cell>
                <Cell hideBelow="md" align="right" num className="text-muted-foreground">
                  {num(q?.data?.ind.values.rsi14, 0)}
                </Cell>
                <Cell align="right">
                  <Button variant="ghost" size="icon-sm" onClick={e => { e.stopPropagation(); remove.mutate(item.ticker); }} aria-label={`Remove ${item.ticker}`}>
                    <Trash2 />
                  </Button>
                </Cell>
              </ListRow>
            );
          })}
        </List>
      )}
    </Section>
  );
}
