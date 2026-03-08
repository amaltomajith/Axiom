import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { runBacktestFromData, BacktestResult } from '@/lib/backtesting';
import { fetchStockData } from '@/lib/api';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts';
import { Trophy, Loader2, BarChart3 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { motion } from 'framer-motion';

interface BacktestTabProps {
  ticker: string;
}

export function BacktestTab({ ticker }: BacktestTabProps) {
  const [results, setResults] = useState<BacktestResult[] | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { toast } = useToast();

  const handleRun = async () => {
    setIsLoading(true);
    try {
      const data = await fetchStockData(ticker, 90);
      if (data.length < 30) {
        toast({ title: 'Not enough data', description: 'Need at least 30 data points for backtesting', variant: 'destructive' });
        setIsLoading(false);
        return;
      }
      const res = runBacktestFromData(data);
      setResults(res);
    } catch (err: any) {
      toast({ title: 'Backtest error', description: err.message || 'Failed to fetch data', variant: 'destructive' });
    }
    setIsLoading(false);
  };

  const chartData = results?.[0]?.dates.map((date, i) => {
    const point: any = { date, actual: results[0].actualPrices[i] };
    results.forEach(r => { point[r.model] = r.predictedPrices[i]; });
    return point;
  }) || [];

  const bestModel = results?.reduce((best, r) => r.rmse < best.rmse ? r : best, results[0]);

  return (
    <div className="space-y-5">
      <div className="glass-card rounded-xl p-5">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <BarChart3 className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h3 className="text-sm font-semibold font-display">Backtest {ticker}</h3>
              <p className="text-xs text-muted-foreground">Using last 90 days of real market data</p>
            </div>
          </div>
          <Button onClick={handleRun} disabled={isLoading} size="sm" className="font-mono text-xs gap-1.5 bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 shadow-none">
            {isLoading ? <><Loader2 className="h-3 w-3 animate-spin" /> RUNNING...</> : 'RUN BACKTEST'}
          </Button>
        </div>
      </div>

      {results && results.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-5">
          <div className="glass-card rounded-xl overflow-hidden">
            <div className="px-5 py-3.5 border-b border-border/50">
              <h3 className="text-sm font-semibold font-display">{ticker} Backtest — Real Data</h3>
            </div>
            <div className="p-4">
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(225, 15%, 10%)" />
                  <XAxis dataKey="date" tick={{ fill: 'hsl(220, 12%, 40%)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="hsl(225, 15%, 10%)" tickFormatter={v => v.slice(5)} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fill: 'hsl(220, 12%, 40%)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="hsl(225, 15%, 10%)" tickFormatter={v => `$${v.toFixed(0)}`} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ backgroundColor: 'hsl(225, 20%, 6%)', border: '1px solid hsl(225, 15%, 14%)', borderRadius: '10px', fontSize: 11, fontFamily: 'JetBrains Mono' }} />
                  <Legend wrapperStyle={{ fontSize: 10, fontFamily: 'JetBrains Mono' }} iconType="circle" iconSize={6} />
                  <Line type="monotone" dataKey="actual" stroke="hsl(168, 80%, 48%)" strokeWidth={2.5} dot={false} name="Actual" />
                  {results.map(r => (
                    <Line key={r.model} type="monotone" dataKey={r.model} stroke={r.color} strokeWidth={2} strokeDasharray="6 3" dot={false} name={r.model} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {results.map((r, idx) => (
              <motion.div
                key={r.model}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.08 }}
                className={`stat-card ${r.model === bestModel?.model ? 'glow-primary gradient-border' : ''}`}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: r.color }} />
                    <span className="font-mono text-sm font-semibold">{r.model}</span>
                  </div>
                  {r.model === bestModel?.model && <Trophy className="h-4 w-4 text-primary" />}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg bg-muted/50 p-3">
                    <div className="text-[10px] text-muted-foreground font-mono uppercase tracking-wider">RMSE</div>
                    <div className="font-mono text-lg font-bold mt-0.5">${r.rmse}</div>
                  </div>
                  <div className="rounded-lg bg-muted/50 p-3">
                    <div className="text-[10px] text-muted-foreground font-mono uppercase tracking-wider">Accuracy</div>
                    <div className="font-mono text-lg font-bold mt-0.5">{r.directionalAccuracy}%</div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}
