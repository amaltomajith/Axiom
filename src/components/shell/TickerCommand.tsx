import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CornerDownLeft, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { Kbd } from '@/components/kit/Kbd';
import { api, POPULAR_TICKERS } from '@/lib/api';
import { getRecent } from '@/lib/recent';

const TICKER_RE = /^[A-Z][A-Z0-9.-]{0,9}$/;

interface Props {
  ticker: string;
  onSelect: (ticker: string) => void;
}

/** One place to choose a stock: a trigger in the header and a keyboard-first palette (Cmd/Ctrl + K). */
export function TickerCommand({ ticker, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const { data: watchlist = [] } = useQuery({ queryKey: ['watchlist'], queryFn: api.watchlist, enabled: open });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen(o => !o);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const choose = (t: string) => {
    onSelect(t.toUpperCase());
    setOpen(false);
    setQuery('');
  };

  const recent = open ? getRecent().filter(t => t !== ticker) : [];
  const watch = watchlist.map(w => w.ticker);
  const known = new Set([...recent, ...watch, ...POPULAR_TICKERS]);
  const typed = query.trim().toUpperCase();
  const canAnalyzeTyped = TICKER_RE.test(typed) && !known.has(typed);

  const group = (heading: string, list: string[]) =>
    list.length > 0 && (
      <CommandGroup heading={heading}>
        {list.map(t => (
          <CommandItem key={`${heading}-${t}`} value={`${t} ${heading}`} onSelect={() => choose(t)}>
            <span className="font-mono text-body font-medium">{t}</span>
          </CommandItem>
        ))}
      </CommandGroup>
    );

  return (
    <>
      <Button
        variant="outline"
        onClick={() => setOpen(true)}
        aria-label={`Change ticker, currently ${ticker}`}
        className="h-10 min-w-0 justify-between gap-3 px-3 font-normal text-muted-foreground sm:w-60"
      >
        <span className="flex min-w-0 items-center gap-2">
          <Search className="h-4 w-4 shrink-0" />
          <span className="truncate font-mono text-body font-medium text-foreground">{ticker}</span>
        </span>
        <span className="hidden items-center gap-1 sm:flex">
          <Kbd>⌘</Kbd>
          <Kbd>K</Kbd>
        </span>
      </Button>

      <CommandDialog open={open} onOpenChange={o => (setOpen(o), !o && setQuery(''))}>
        <CommandInput placeholder="Search a ticker, e.g. NVDA…" value={query} onValueChange={setQuery} aria-label="Ticker symbol" autoComplete="off" spellCheck={false} />
        <CommandList className="max-h-80">
          <CommandEmpty>
            <span className="text-small text-muted-foreground">Type a US ticker symbol and press Enter.</span>
          </CommandEmpty>
          {canAnalyzeTyped && (
            <CommandGroup heading="Open">
              <CommandItem value={`open ${typed}`} onSelect={() => choose(typed)}>
                <span className="font-mono text-body font-medium">{typed}</span>
                <CornerDownLeft className="ml-auto h-4 w-4 text-muted-foreground" />
              </CommandItem>
            </CommandGroup>
          )}
          {group('Recent', recent)}
          {group('Watchlist', watch)}
          {group('Popular', POPULAR_TICKERS.filter(t => t !== ticker))}
        </CommandList>
      </CommandDialog>
    </>
  );
}
