import { cn } from '@/lib/utils';

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-col items-center px-6 py-14 text-center', className)}>
      {Icon && (
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-primary/25 bg-gradient-to-b from-primary/15 to-primary/[0.03] text-primary shadow-[0_0_24px_-8px_hsl(var(--primary)/0.7)]">
          <Icon className="h-5 w-5" />
        </div>
      )}
      <p className="text-body font-medium">{title}</p>
      {description && <p className="mt-1 max-w-[42ch] text-small text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
