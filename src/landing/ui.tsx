import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';

/** The one primary action on the page. Same words everywhere, always to the cockpit. */
export function StartLink({ className, size = 'md' }: { className?: string; size?: 'sm' | 'md' }) {
  return (
    <Link
      to="/app"
      className={cn(
        'lp-cta inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        size === 'sm' ? 'h-9 px-4 text-small' : 'h-12 px-6 text-body',
        className,
      )}
    >
      Start on paper
      <ArrowRight aria-hidden className={size === 'sm' ? 'h-3.5 w-3.5' : 'h-4 w-4'} />
    </Link>
  );
}

export function GhostLink({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  const external = href.startsWith('http');
  return (
    <a
      href={href}
      {...(external ? { target: '_blank', rel: 'noreferrer' } : {})}
      className={cn(
        'lp-ghost inline-flex h-12 items-center justify-center whitespace-nowrap rounded-full px-6 text-body font-medium text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring',
        className,
      )}
    >
      {children}
    </a>
  );
}

export function Chip({ children, className, live }: { children: ReactNode; className?: string; live?: boolean }) {
  return (
    <span className={cn('lp-chip inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-caption font-medium text-foreground', className)}>
      <span aria-hidden className="relative flex h-1.5 w-1.5">
        {live && <span className="absolute inset-0 animate-ping rounded-full bg-primary/70" />}
        <span className="relative h-1.5 w-1.5 rounded-full bg-primary shadow-[0_0_8px_hsl(var(--primary))]" />
      </span>
      {children}
    </span>
  );
}
