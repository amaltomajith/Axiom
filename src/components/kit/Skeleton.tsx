import { cn } from '@/lib/utils';

/** Skeletons mirror the final layout (same heights and widths) so nothing shifts when data arrives. */
export const SkeletonLine = ({ className }: { className?: string }) => <div className={cn('skeleton h-3.5', className)} aria-hidden />;
export const SkeletonBlock = ({ className }: { className?: string }) => <div className={cn('skeleton', className)} aria-hidden />;

export function SkeletonRows({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('divide-y divide-border', className)} role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center justify-between gap-6 px-5 py-4 sm:px-6">
          <SkeletonLine className="w-24" />
          <SkeletonLine className="w-16" />
        </div>
      ))}
    </div>
  );
}
