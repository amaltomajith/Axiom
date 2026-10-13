import { cn } from '@/lib/utils';

export const Kbd = ({ className, ...p }: React.HTMLAttributes<HTMLElement>) => (
  <kbd
    className={cn('inline-flex h-5 min-w-5 items-center justify-center rounded-sm border border-border bg-muted px-1 font-sans text-caption text-muted-foreground', className)}
    {...p}
  />
);
