import { ArrowDownRight, ArrowUpRight, RefreshCw, Sparkles, Square, Star } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SkeletonBlock, SkeletonLine } from '@/components/kit/Skeleton';
import { money, pct, shortDate } from '@/lib/format';
import { cn } from '@/lib/utils';

interface Props {
  ticker: string;
  loading: boolean;
  last?: number;
  change: number;
  changePct: number;
  asOf?: string;
  provider?: string;
  watched: boolean;
  onToggleWatch: () => void;
  onRefresh: () => void;
  running: boolean;
  canRun: boolean;
  onRun: () => void;
  onCancel: () => void;
}

/**
 * The page's anchor (Apple Stocks style): who, how much, how it moved, and the ONE primary action.
 * Fixed height so the page below never shifts while prices load.
 */
export function QuoteStrip(p: Props) {
  const up = p.change >= 0;
  const Arrow = up ? ArrowUpRight : ArrowDownRight;
  return (
    <div className="flex flex-col gap-4 py-6 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h1 translate="no" className="font-mono text-h2 tracking-tight">{p.ticker}</h1>
          <Button variant="ghost" size="icon-sm" onClick={p.onToggleWatch} aria-pressed={p.watched} aria-label={p.watched ? `Remove ${p.ticker} from watchlist` : `Add ${p.ticker} to watchlist`}>
            <Star className={cn(p.watched && 'fill-warning text-warning')} />
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={p.onRefresh} aria-label="Refresh data">
            <RefreshCw />
          </Button>
        </div>
        {p.loading ? (
          <div className="mt-2 space-y-2" aria-hidden>
            <SkeletonBlock className="h-10 w-44" />
            <SkeletonLine className="w-56" />
          </div>
        ) : (
          <>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="tnum text-display leading-none">{money(p.last)}</span>
              <span className={cn('tnum inline-flex items-center gap-1 text-h3', up ? 'text-success' : 'text-destructive')}>
                <Arrow className="h-5 w-5" />
                {up ? '+' : ''}
                {p.change.toFixed(2)} <span className="text-body">({pct(p.changePct, 2, true)})</span>
              </span>
            </div>
            <p className="mt-2 text-small text-muted-foreground">
              Daily close, {shortDate(p.asOf)}. Source: {p.provider ?? 'n/a'}.
            </p>
          </>
        )}
      </div>

      <div className="shrink-0">
        {p.running ? (
          <Button size="lg" variant="secondary" onClick={p.onCancel} className="w-full sm:w-auto">
            <Square className="fill-current" /> Stop
          </Button>
        ) : (
          <Button size="lg" onClick={p.onRun} disabled={!p.canRun} className="w-full sm:w-auto">
            <Sparkles /> Run analysis
          </Button>
        )}
      </div>
    </div>
  );
}
