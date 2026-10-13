import { cn } from '@/lib/utils';

/**
 * Axiom mark: an "A" built from two strokes with an up-and-right arrow. A single geometric glyph
 * (no gradients, no hand-drawn detail) so it stays crisp at 16px and on both themes.
 * The original raster logo stays in /public for the favicon and social card.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn('h-7 w-7 shrink-0', className)} fill="none" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5.5 26 15 6.5 24.5 26" stroke="hsl(var(--foreground))" strokeWidth="3" />
      <path d="M15.5 20.5 27 9" stroke="hsl(var(--primary))" strokeWidth="3" />
      <path d="M20.5 8.5H27.5V15.5" stroke="hsl(var(--primary))" strokeWidth="3" />
    </svg>
  );
}

export function Logo({ className, wordmark = true }: { className?: string; wordmark?: boolean }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <LogoMark />
      {wordmark && <span translate="no" className="text-h3 font-semibold tracking-[-0.02em]">Axiom</span>}
    </span>
  );
}
