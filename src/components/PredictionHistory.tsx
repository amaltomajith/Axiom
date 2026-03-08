import { useState, useEffect } from 'react';
import { Badge } from '@/components/ui/badge';
import { getPredictionLogs, PredictionLog } from '@/lib/storage';
import { motion } from 'framer-motion';
import { ClipboardList, BarChart3 } from 'lucide-react';

export function PredictionHistory() {
  const [logs, setLogs] = useState<PredictionLog[]>([]);

  useEffect(() => { setLogs(getPredictionLogs().reverse()); }, []);

  const modelAccuracy = logs.filter(l => l.verified).reduce((acc, l) => {
    l.predictions.forEach(p => {
      if (!acc[p.model]) acc[p.model] = { correct: 0, total: 0 };
      acc[p.model].total++;
      if (l.actualPrice && Math.abs(p.price - l.actualPrice) / l.actualPrice < 0.05) acc[p.model].correct++;
    });
    return acc;
  }, {} as Record<string, { correct: number; total: number }>);

  return (
    <div className="space-y-5">
      {Object.keys(modelAccuracy).length > 0 && (
        <div className="glass-card rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-5 py-3.5 border-b border-border/50">
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground font-semibold">Model Accuracy</h3>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-3 gap-3">
              {Object.entries(modelAccuracy).map(([model, acc]) => (
                <div key={model} className="text-center rounded-lg bg-muted/30 p-4">
                  <div className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">{model}</div>
                  <div className="font-mono text-2xl font-bold mt-1">
                    {acc.total > 0 ? ((acc.correct / acc.total) * 100).toFixed(0) : 0}%
                  </div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">{acc.total} predictions</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="glass-card rounded-xl overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3.5 border-b border-border/50">
          <ClipboardList className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground font-semibold">Prediction Log</h3>
        </div>
        <div>
          {logs.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-sm text-muted-foreground font-mono">No predictions logged yet</p>
              <p className="text-xs text-muted-foreground/60 mt-1">Run a prediction to start tracking</p>
            </div>
          ) : (
            <div className="divide-y divide-border/30">
              {logs.map((log, idx) => (
                <motion.div
                  key={log.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: idx * 0.03 }}
                  className="px-5 py-3.5 hover:bg-muted/20 transition-colors"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-sm">{log.ticker}</span>
                      <span className="text-[10px] text-muted-foreground font-mono">{log.date}</span>
                    </div>
                    <Badge className={`font-mono text-[10px] border ${log.verified ? 'bg-success/10 text-success border-success/20' : 'bg-muted text-muted-foreground border-border'} hover:opacity-100`}>
                      {log.verified ? 'VERIFIED' : 'PENDING'}
                    </Badge>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    {log.predictions.map(p => (
                      <div key={p.model} className="font-mono">
                        <span className="text-muted-foreground">{p.model}:</span>{' '}
                        <span className="font-medium">${p.price.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                  {log.actualPrice && (
                    <div className="mt-1.5 text-xs font-mono text-muted-foreground">
                      Actual: <span className="text-foreground font-medium">${log.actualPrice.toFixed(2)}</span>
                    </div>
                  )}
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
