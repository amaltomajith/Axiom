import { Link } from 'react-router-dom';
import { LogoMark } from '@/components/Logo';
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
      <div className="mx-auto flex h-[72px] max-w-[1320px] items-center gap-3 px-4 sm:px-6">
        <Link to="/" aria-label="Axiom home" className="shrink-0 rounded-md">
          <span className="flex items-center gap-3">
            <LogoMark className="h-8 w-8 drop-shadow-[0_0_12px_hsl(var(--primary)/0.55)]" />
            <span translate="no" className="lp-silver hidden text-[0.95rem] font-semibold tracking-[0.34em] sm:inline">
              AXIOM
            </span>
          </span>
        </Link>
        <div className="mx-2 hidden h-5 w-px bg-white/10 sm:block" />
        <TickerCommand ticker={ticker} onSelect={onTicker} />
        <div className="ml-auto flex items-center gap-0.5">
          <StatusPopover health={health} offline={offline} />
          <TokenDialog />
        </div>
      </div>
    </header>
  );
}
