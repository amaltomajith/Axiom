import { useId } from 'react';
import { motion } from 'motion/react';
import { spring, useReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/utils';

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  badge?: number;
}

interface SegmentedProps<T extends string> {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (v: T) => void;
  ariaLabel: string;
  size?: 'sm' | 'md';
  className?: string;
  /** allow horizontal scrolling on narrow screens (labels are never hidden) */
  scroll?: boolean;
}

/**
 * Segmented control with a shared-layout indicator. The indicator is a spring, so changing selection
 * mid-slide re-targets from where it is (interruptible); under reduced motion it jumps without animating.
 */
export function Segmented<T extends string>({ options, value, onChange, ariaLabel, size = 'md', className, scroll }: SegmentedProps<T>) {
  const id = useId();
  const reduce = useReducedMotion();
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn(
        'inline-flex max-w-full items-center gap-0.5 rounded-full border border-border bg-muted p-1',
        scroll && 'overflow-x-auto [scrollbar-width:none]',
        className,
      )}
    >
      {options.map(o => {
        const active = o.value === value;
        const Icon = o.icon;
        return (
          <button
            key={o.value}
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(o.value)}
            onKeyDown={e => {
              const i = options.findIndex(x => x.value === value);
              if (e.key === 'ArrowRight') onChange(options[(i + 1) % options.length].value);
              if (e.key === 'ArrowLeft') onChange(options[(i - 1 + options.length) % options.length].value);
            }}
            className={cn(
              'relative inline-flex shrink-0 select-none items-center gap-2 rounded-full font-medium transition-colors duration-100 active:scale-[0.97]',
              size === 'md' ? 'h-8 px-3.5 text-small' : 'h-7 px-3 text-caption',
              active ? 'text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {active && (
              <motion.span
                layoutId={`seg-${id}`}
                className="absolute inset-0 rounded-full border border-border bg-card shadow-sm"
                transition={reduce ? { duration: 0 } : spring.snappy}
              />
            )}
            <span className="relative inline-flex items-center gap-2">
              {Icon && <Icon className="h-4 w-4" />}
              {o.label}
              {o.badge ? <span className="tnum rounded-full bg-primary px-1.5 text-caption text-primary-foreground">{o.badge}</span> : null}
            </span>
          </button>
        );
      })}
    </div>
  );
}
