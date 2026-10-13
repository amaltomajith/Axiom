import { AnimatePresence, motion } from 'motion/react';
import { Check, Circle, Loader2, TriangleAlert } from 'lucide-react';
import type { Step } from '@/hooks/useTraceProgress';
import { spring, useReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/utils';

const ICON = {
  pending: <Circle className="h-4 w-4 text-muted-foreground/50" />,
  active: <Loader2 className="h-4 w-4 animate-spin text-primary" />,
  done: <Check className="h-4 w-4 text-success" />,
  warn: <TriangleAlert className="h-4 w-4 text-warning" />,
} as const;

/**
 * Where the run is, derived from real trace events (see deriveProgress). Each step's detail line changes in place,
 * so the list never reflows while the analysis runs.
 */
export function PipelineStepper({ steps }: { steps: Step[] }) {
  const reduce = useReducedMotion();
  return (
    <ol className="space-y-0" aria-label="Analysis progress">
      {steps.map((s, i) => (
        <li key={s.id} className="relative flex gap-3 pb-4 last:pb-0" aria-current={s.state === 'active' ? 'step' : undefined}>
          {i < steps.length - 1 && <span className="absolute left-[7.5px] top-6 h-[calc(100%-1.25rem)] w-px bg-border" aria-hidden />}
          <span className="relative z-10 mt-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-card">{ICON[s.state]}</span>
          <div className="min-w-0 flex-1">
            <p className={cn('text-small font-medium', s.state === 'pending' && 'text-muted-foreground')}>{s.label}</p>
            <div className="min-h-[1.25rem]">
              <AnimatePresence mode="wait" initial={false}>
                {s.detail && (
                  <motion.p
                    key={s.detail}
                    initial={reduce ? { opacity: 0 } : { opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={reduce ? { duration: 0.15 } : spring.snappy}
                    className={cn('truncate text-caption', s.state === 'warn' ? 'text-warning' : 'text-muted-foreground')}
                  >
                    {s.detail}
                  </motion.p>
                )}
              </AnimatePresence>
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
