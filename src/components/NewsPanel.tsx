import { ShieldAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Section } from '@/components/kit/Surface';
import { List, ListRow, Cell } from '@/components/kit/List';
import { SkeletonRows } from '@/components/kit/Skeleton';
import { EmptyState } from '@/components/kit/EmptyState';
import { shortDate } from '@/lib/format';
import type { NewsResponse } from '@/lib/types';

const NET_VARIANT = { positive: 'success', negative: 'destructive', neutral: 'neutral' } as const;
const DOT = { positive: 'bg-success', negative: 'bg-destructive', neutral: 'bg-muted-foreground/40' } as const;

export function NewsPanel({ news, loading }: { news: NewsResponse | null; loading?: boolean }) {
  return (
    <Section
      title="News"
      description={news ? `${news.n_articles} recent headlines` : 'Recent headlines'}
      actions={news && news.items.length > 0 && <Badge variant={NET_VARIANT[news.net_label]}>{`Keyword score ${news.net_sentiment > 0 ? '+' : ''}${news.net_sentiment}`}</Badge>}
    >
      {loading ? (
        <SkeletonRows rows={4} className="border-t border-border" />
      ) : !news || news.items.length === 0 ? (
        <div className="border-t border-border">
          <EmptyState title="No headlines found" description="Try refreshing, or check that a news source is reachable." />
        </div>
      ) : (
        <>
          <List cols="grid-cols-[auto_1fr] md:grid-cols-[auto_1fr_9rem_6.5rem]" className="border-t border-border">
            {news.items.map((n, i) => (
              <ListRow key={`${n.headline}-${i}`} className="items-start">
                <Cell className="pt-1.5">
                  {n.injection_suspected ? <ShieldAlert className="h-4 w-4 text-warning" aria-label="Redacted as a suspected prompt injection" /> : <span className={`block h-2 w-2 rounded-full ${DOT[n.label]}`} role="img" aria-label={n.label} />}
                </Cell>
                <Cell>
                  <p className={n.injection_suspected ? 'italic text-warning' : ''}>{n.headline}</p>
                  <p className="mt-0.5 text-caption text-muted-foreground md:hidden">{[n.source, shortDate(n.date)].filter(Boolean).join(', ')}</p>
                </Cell>
                <Cell hideBelow="md" className="truncate text-muted-foreground">
                  {n.source ?? 'Unknown'}
                </Cell>
                <Cell hideBelow="md" align="right" num className="text-muted-foreground">
                  {shortDate(n.date)}
                </Cell>
              </ListRow>
            ))}
          </List>
          <p className="border-t border-border px-5 py-3 text-caption text-muted-foreground sm:px-6">
            {news.sentiment_method}. Source: {news.provider.replace(/_/g, ' ')}.
            {news.injection_flagged > 0 && ` ${news.injection_flagged} headline(s) were redacted as suspected prompt injection.`}
          </p>
        </>
      )}
    </Section>
  );
}
