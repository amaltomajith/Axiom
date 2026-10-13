import { Link } from 'react-router-dom';
import { Logo } from '@/components/Logo';
import { ThemeToggle } from '@/components/ThemeToggle';
import { Button } from '@/components/ui/button';

const LINKS = [
  { href: '#how', label: 'How it works' },
  { href: '#evidence', label: 'Evidence' },
  { href: '#mcp', label: 'MCP' },
];

/** One line at every width, 64px. The anchors collapse away on phones; the call to action never does. */
export function Nav() {
  return (
    <header className="material sticky top-0 z-40">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between gap-4 px-4 sm:px-6">
        <Link to="/" aria-label="Axiom home" className="rounded-md">
          <Logo />
        </Link>
        <nav aria-label="Page" className="hidden items-center gap-1 md:flex">
          {LINKS.map(l => (
            <a key={l.href} href={l.href} className="rounded-md px-3 py-2 text-small text-muted-foreground transition-colors hover:text-foreground">
              {l.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-1.5">
          <ThemeToggle />
          <Button asChild size="sm">
            <Link to="/app">Open terminal</Link>
          </Button>
        </div>
      </div>
    </header>
  );
}
