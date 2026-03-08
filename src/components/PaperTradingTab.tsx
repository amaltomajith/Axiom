import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { getTrades, addTrade, removeTrade, PaperTrade } from '@/lib/storage';
import { fetchStockData } from '@/lib/api';
import { Trash2, Loader2, ShoppingCart, Wallet } from 'lucide-react';
import { motion } from 'framer-motion';

interface PaperTradingTabProps {
  ticker: string;
}

export function PaperTradingTab({ ticker }: PaperTradingTabProps) {
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [quantity, setQuantity] = useState('10');
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => { setTrades(getTrades()); }, []);

  useEffect(() => {
    const tickers = [...new Set(trades.map(t => t.ticker))];
    tickers.forEach(async (t) => {
      if (prices[t]) return;
      try {
        const data = await fetchStockData(t, 5);
        if (data.length > 0) setPrices(prev => ({ ...prev, [t]: data[data.length - 1].close }));
      } catch { /* ignore */ }
    });
  }, [trades]);

  const handleBuy = async () => {
    setLoading(true);
    try {
      const data = await fetchStockData(ticker, 5);
      const price = data.length > 0 ? data[data.length - 1].close : 0;
      if (price > 0) {
        addTrade({ ticker, entryPrice: price, quantity: parseInt(quantity) || 10, entryDate: new Date().toISOString().split('T')[0], type: 'BUY' });
        setTrades(getTrades());
        setPrices(prev => ({ ...prev, [ticker]: price }));
      }
    } catch { /* ignore */ }
    setLoading(false);
  };

  const handleRemove = (id: string) => { removeTrade(id); setTrades(getTrades()); };

  const totalPnL = trades.reduce((sum, t) => {
    const current = prices[t.ticker] || t.entryPrice;
    return sum + (current - t.entryPrice) * t.quantity * (t.type === 'BUY' ? 1 : -1);
  }, 0);

  return (
    <div className="space-y-5">
      <div className="glass-card rounded-xl p-5">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <ShoppingCart className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h3 className="text-sm font-semibold font-display">Paper Trade</h3>
              <p className="text-xs text-muted-foreground">{ticker} — simulated orders</p>
            </div>
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <Input
              type="number"
              value={quantity}
              onChange={e => setQuantity(e.target.value)}
              className="w-20 h-8 font-mono text-xs bg-muted/30 border-border/50 rounded-lg"
              placeholder="Qty"
            />
            <Button
              onClick={handleBuy}
              disabled={loading}
              size="sm"
              className="font-mono text-xs gap-1.5 bg-success/10 text-success border border-success/20 hover:bg-success/20 shadow-none"
            >
              {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : 'BUY'}
            </Button>
          </div>
        </div>
      </div>

      <div className="glass-card rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-border/50">
          <div className="flex items-center gap-2">
            <Wallet className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground font-semibold">Portfolio</h3>
          </div>
          <span className={`font-mono text-sm font-bold ${totalPnL >= 0 ? 'text-success' : 'text-destructive'}`}>
            P&L: {totalPnL >= 0 ? '+' : ''}${totalPnL.toFixed(2)}
          </span>
        </div>
        <div>
          {trades.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-sm text-muted-foreground font-mono">No open trades</p>
              <p className="text-xs text-muted-foreground/60 mt-1">Buy a position to start tracking</p>
            </div>
          ) : (
            <div className="divide-y divide-border/30">
              {trades.map((t, idx) => {
                const current = prices[t.ticker] || t.entryPrice;
                const pnl = (current - t.entryPrice) * t.quantity * (t.type === 'BUY' ? 1 : -1);
                return (
                  <motion.div
                    key={t.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: idx * 0.05 }}
                    className="flex items-center justify-between px-5 py-3.5 hover:bg-muted/20 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <Badge variant="secondary" className="font-mono text-[10px]">{t.type}</Badge>
                      <span className="font-mono font-bold text-sm">{t.ticker}</span>
                      <span className="text-xs text-muted-foreground font-mono">{t.quantity} @ ${t.entryPrice.toFixed(2)}</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <div className="font-mono text-[11px] text-muted-foreground">Now ${current.toFixed(2)}</div>
                        <div className={`font-mono text-sm font-bold ${pnl >= 0 ? 'text-success' : 'text-destructive'}`}>
                          {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                        </div>
                      </div>
                      <Button size="icon" variant="ghost" onClick={() => handleRemove(t.id)}
                        className="text-muted-foreground hover:text-destructive h-7 w-7 rounded-lg">
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
