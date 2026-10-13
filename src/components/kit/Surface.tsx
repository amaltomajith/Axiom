import * as React from 'react';
import { cn } from '@/lib/utils';

/** The only container: flat neutral, 1px hairline, 16px radius. Never nest a Surface inside a Surface. */
export const Surface = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement> & { quiet?: boolean }>(
  ({ className, quiet, ...props }, ref) => (
    <div ref={ref} className={cn(quiet ? 'surface-quiet' : 'surface', className)} {...props} />
  ),
);
Surface.displayName = 'Surface';

interface SectionProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}

/** Title row + body. Inner groups are separated by dividers, not boxes. */
export function Section({ title, description, actions, className, children, ...props }: SectionProps) {
  return (
    <section className={cn('surface overflow-hidden', className)} {...props}>
      <header className="flex items-start justify-between gap-4 px-5 pb-3 pt-4 sm:px-6">
        <div className="min-w-0">
          <h2 className="text-h3">{title}</h2>
          {description && <p className="mt-0.5 text-small text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </header>
      {children}
    </section>
  );
}
