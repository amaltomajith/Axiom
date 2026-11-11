import { Link } from 'react-router-dom';
import { Logo } from '@/components/Logo';
import { NAV_LINKS } from './data';
import { StartLink } from './ui';

/** Logo on the left, a floating glass pill of links in the middle, the one action on the right. */
export function Nav() {
  return (
    <header className="fixed inset-x-0 top-0 z-40">
      <div className="mx-auto flex h-[72px] max-w-[1320px] items-center justify-between gap-4 px-4 sm:px-8">
        <Link to="/" aria-label="Axiom home" className="shrink-0 rounded-md bg-background/40 backdrop-blur-sm">
          <Logo />
        </Link>
        <nav aria-label="Page" className="hidden rounded-full border border-white/10 bg-[hsl(222_26%_8%/0.7)] p-1 shadow-[0_8px_30px_-10px_hsl(var(--primary)/0.35)] backdrop-blur-md md:block">
          <ul className="flex items-center">
            {NAV_LINKS.map(l => (
              <li key={l.href}>
                <a href={l.href} className="block rounded-full px-4 py-2 text-small font-medium text-foreground/80 transition-colors hover:bg-white/[0.06] hover:text-foreground">
                  {l.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <StartLink size="sm" />
      </div>
    </header>
  );
}
