import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { getWatchlist, removeFromWatchlist, WatchlistItem } from '@/lib/storage';
import { fetchStockData } from '@/lib/api';
import { runPredictions, getConfidenceGrade, getPredictedDirection } from '@/lib/models';
import { Trash2, TrendingUp, TrendingDown, Loader2, Eye } from 'lucide-react';
import { motion } from 'framer-motion';

interface WatchlistTabProps {
  onSelectTicker: (ticker: string) => void;
}

interface WatchlistItemData {
  ticker: string;
  price: number;
  direction: 'up' | 'down';
  grade: string;
  loading: boolean;
}

export function WatchlistTab({ onSelectTicker }: WatchlistTabProps) {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [itemData, setItemData] = useState<Record<string, WatchlistItemData>>({});

  useEffect(() => {
    const list = getWatchlist();
    setItems(list);
    list.forEach(item => loadTickerData(item.ticker));
  }, []);

  const loadTickerData = async (ticker: string) => {
    setItemData(prev => ({ ...prev, [ticker]: { ticker, price: 0, direction: 'up', grade: '-', loading: true } }));
    try {
      const data = await fetchStockData(ticker, 60);
      if (data.length > 0) {
        const price = data[data.length - 1].close;
        const preds = runPredictions(data, 14);
        const direction = getPredictedDirection(preds, price);
        const grade = getConfidenceGrade(preds);
        setItemData(prev => ({ ...prev, [ticker]: { ticker, price, direction, grade, loading: false } }));
      }
    } catch {
      setItemData(prev => ({ ...prev, [ticker]: { ticker, price: 0, direction: 'up', grade: '?', loading: false } }));
    }
  };

  const handleRemove = (ticker: string) => { removeFromWatchlist(ticker); setItems(getWatchlist()); };

  if (items.length === 0) {
    return (
      <div className="glass-card rounded-xl py-16 text-center">
        <Eye className="h-8 w-8 text-muted-foreground/30 mx-auto mb-3" />
        <p className="text-sm text-muted-foreground font-mono">No tickers in watchlist</p>
        <p className="text-xs text-muted-foreground/60 mt-1">Click the ★ icon next to a ticker to add it</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {items.map((item, idx) => {
        const d = itemData[item.ticker];
        return (
          <motion.div
            key={item.ticker}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.05 }}
            className="glass-card rounded-xl hover:border-primary/20 transition-all duration-200 cursor-pointer"
            onClick={() => onSelectTicker(item.ticker)}
          >
            <div className="flex items-center justify-between px-5 py-4">
              <div className="flex items-center gap-4">
                <span className="font-mono text-lg font-bold">{item.ticker}</span>
                {d?.loading ? (
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                ) : (
                  <span className="font-mono text-sm text-muted-foreground">${d?.price?.toFixed(2) || '—'}</span>
                )}
              </div>
              <div className="flex items-center gap-3">
                {d && !d.loading && (
                  <>
                    <div className={`flex items-center gap-1 ${d.direction === 'up' ? 'text-success' : 'text-destructive'}`}>
                      {d.direction === 'up' ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                    </div>
                    <Badge className={`font-mono text-[10px] border ${
                      d.grade === 'A' || d.grade === 'B' ? 'bg-success/10 text-success border-success/20' :
                      d.grade === 'C' ? 'bg-warning/10 text-warning border-warning/20' :
                      'bg-destructive/10 text-destructive border-destructive/20'
                    } hover:opacity-100`}>
                      {d.grade}
                    </Badge>
                  </>
                )}
                <Button size="icon" variant="ghost" onClick={e => { e.stopPropagation(); handleRemove(item.ticker); }}
                  className="text-muted-foreground hover:text-destructive h-7 w-7 rounded-lg">
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
