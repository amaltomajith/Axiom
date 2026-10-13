import * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * Aligned list. The caller passes ONE grid-template class (responsive allowed) used by the header and every
 * row, so columns line up exactly and numbers right-align with tabular figures. Example:
 *   cols="grid-cols-[1fr_auto] md:grid-cols-[1fr_7rem_7rem_auto]"
 */
interface ListProps extends React.HTMLAttributes<HTMLDivElement> {
  cols: string;
  headers?: { label: string; align?: 'left' | 'right'; hideBelow?: 'sm' | 'md' }[];
}

const ListContext = React.createContext<string>('');

const HIDE = { sm: 'hidden sm:block', md: 'hidden md:block' } as const;

export function List({ cols, headers, className, children, ...props }: ListProps) {
  return (
    <ListContext.Provider value={cols}>
      <div role="table" className={cn('text-small', className)} {...props}>
        {headers && (
          <div
            role="row"
            className={cn('grid items-center gap-x-4 border-y border-border bg-muted/50 px-5 py-2 text-caption text-muted-foreground sm:px-6', cols)}
          >
            {headers.map(h => (
              <div key={h.label} role="columnheader" className={cn(h.align === 'right' && 'text-right', h.hideBelow && HIDE[h.hideBelow])}>
                {h.label}
              </div>
            ))}
          </div>
        )}
        <div className="divide-y divide-border">{children}</div>
      </div>
    </ListContext.Provider>
  );
}

export function ListRow({ className, onClick, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  const cols = React.useContext(ListContext);
  const interactive = Boolean(onClick);
  return (
    <div
      role="row"
      tabIndex={interactive ? 0 : undefined}
      onClick={onClick}
      onKeyDown={
        interactive
          ? e => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                (e.currentTarget as HTMLElement).click();
              }
            }
          : undefined
      }
      className={cn(
        'grid items-center gap-x-4 px-5 py-3 sm:px-6',
        cols,
        interactive && 'cursor-pointer transition-colors hover:bg-accent/60 active:bg-accent',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function Cell({
  align,
  num,
  hideBelow,
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { align?: 'right'; num?: boolean; hideBelow?: 'sm' | 'md' }) {
  return (
    <div
      role="cell"
      className={cn('min-w-0', align === 'right' && 'text-right', num && 'tnum', hideBelow && HIDE[hideBelow], className)}
      {...props}
    />
  );
}
