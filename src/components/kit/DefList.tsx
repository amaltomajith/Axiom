import { cn } from '@/lib/utils';

/** Label on the left, value right-aligned: the calm alternative to a grid of tiles. */
export function DefList({ items, className }: { items: { label: string; value: React.ReactNode }[]; className?: string }) {
  return (
    <dl className={cn('divide-y divide-border text-small', className)}>
      {items.map(i => (
        <div key={i.label} className="flex items-baseline justify-between gap-6 py-2.5">
          <dt className="text-muted-foreground">{i.label}</dt>
          <dd className="tnum text-right font-medium">{i.value}</dd>
        </div>
      ))}
    </dl>
  );
}
