import { Link } from 'react-router-dom';
import { Logo, LogoMark } from '@/components/Logo';
import { ThemeToggle } from '@/components/ThemeToggle';
import { TokenDialog } from '@/components/TokenDialog';
import { StatusPopover } from '@/components/shell/StatusPopover';
import { TickerCommand } from '@/components/shell/TickerCommand';
import type { Health } from '@/lib/types';

interface Props {
  ticker: string;
  onTicker: (t: string) => void;
  health: Health | undefined;
  offline: boolean;
}

/** 64px, one line at every width. Only global things live here; stock-specific actions live in the quote strip. */
export function AppHeader({ ticker, onTicker, health, offline }: Props) {
  return (
    <header className="material sticky top-0 z-40">
      <div className="mx-auto flex h-16 max-w-[1280px] items-center gap-3 px-4 sm:px-6">
        <Link to="/" aria-label="Axiom home" className="shrink-0 rounded-md">
          <Logo className="hidden sm:inline-flex" />
          <LogoMark className="sm:hidden" />
        </Link>
        <div className="mx-1 hidden h-5 w-px bg-border sm:block" />
        <TickerCommand ticker={ticker} onSelect={onTicker} />
        <div className="ml-auto flex items-center gap-0.5">
          <StatusPopover health={health} offline={offline} />
          <ThemeToggle />
          <TokenDialog />
        </div>
      </div>
    </header>
  );
}
