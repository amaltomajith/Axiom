import { Children } from 'react';
import { cn } from '@/lib/utils';

interface StatProps {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: 'default' | 'gain' | 'loss' | 'warn';
  className?: string;
}

const TONE = { default: '', gain: 'text-success', loss: 'text-destructive', warn: 'text-warning' } as const;

/** Label above, figure below. Numbers are tabular so a row of stats lines up. */
export function Stat({ label, value, sub, tone = 'default', className }: StatProps) {
  return (
    <div className={cn('min-w-0', className)}>
      <dt className="text-caption text-muted-foreground">{label}</dt>
      <dd className={cn('tnum mt-1 truncate text-h2', TONE[tone])}>{value}</dd>
      {sub && <p className="mt-0.5 text-caption text-muted-foreground">{sub}</p>}
    </div>
  );
}

/** A horizontal run of stats separated by hairlines (no boxes inside the surface). */
export function StatRow({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <dl className={cn('grid grid-cols-2 divide-border sm:grid-cols-4 sm:divide-x', className)}>
      {Children.toArray(children).map((c, i) => (
        <div key={i} className="px-5 py-4 sm:px-6">
          {c}
        </div>
      ))}
    </dl>
  );
}
