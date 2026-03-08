import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { POPULAR_TICKERS } from '@/lib/stockData';
import { Star, Search } from 'lucide-react';
import { addToWatchlist, getWatchlist } from '@/lib/storage';

interface TickerSelectorProps {
  selected: string;
  onSelect: (ticker: string) => void;
}

export function TickerSelector({ selected, onSelect }: TickerSelectorProps) {
  const [custom, setCustom] = useState('');
  const watchlist = getWatchlist();
  const isWatched = watchlist.some(w => w.ticker === selected);

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <div className="flex items-center gap-1.5 p-1 rounded-xl bg-muted/30 border border-border/50">
        {POPULAR_TICKERS.map(t => (
          <Button
            key={t}
            variant="ghost"
            size="sm"
            onClick={() => onSelect(t)}
            className={`font-mono text-xs px-3 py-1.5 h-auto rounded-lg transition-all duration-200 ${
              selected === t
                ? 'bg-primary/10 text-primary border border-primary/20'
                : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50 border border-transparent'
            }`}
          >
            {t}
          </Button>
        ))}
      </div>
      <div className="flex items-center gap-1.5">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="Search ticker..."
            value={custom}
            onChange={e => setCustom(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && custom && onSelect(custom)}
            className="w-36 h-8 pl-8 font-mono text-xs bg-muted/30 border-border/50 focus:border-primary/50 rounded-lg"
          />
        </div>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => custom && onSelect(custom)}
          className="h-8 font-mono text-xs rounded-lg"
        >
          GO
        </Button>
      </div>
      {selected && !isWatched && (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => addToWatchlist(selected)}
          className="h-8 w-8 p-0 text-muted-foreground hover:text-warning transition-colors"
        >
          <Star className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}
