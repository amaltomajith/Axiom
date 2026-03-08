import { SignalResult } from '@/lib/indicators';
import { TrendingUp, TrendingDown, Minus, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { motion } from 'framer-motion';

interface SignalsPanelProps {
  signal: SignalResult | null;
}

export function SignalsPanel({ signal }: SignalsPanelProps) {
  if (!signal) return null;

  const icon = signal.signal === 'BUY'
    ? <ArrowUpRight className="h-5 w-5" />
    : signal.signal === 'SELL'
    ? <ArrowDownRight className="h-5 w-5" />
    : <Minus className="h-5 w-5" />;

  const config = {
    BUY: { bg: 'bg-success/5', border: 'border-success/20', text: 'text-success', glow: 'glow-success' },
    SELL: { bg: 'bg-destructive/5', border: 'border-destructive/20', text: 'text-destructive', glow: 'glow-destructive' },
    HOLD: { bg: 'bg-warning/5', border: 'border-warning/20', text: 'text-warning', glow: 'glow-warning' },
  };
  const c = config[signal.signal];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`glass-card rounded-xl ${c.border} border ${c.glow} overflow-hidden`}
    >
      <div className={`${c.bg} px-5 py-4`}>
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${c.text} bg-background/50`}>
            {icon}
          </div>
          <div>
            <div className={`text-2xl font-bold font-display tracking-tight ${c.text}`}>
              {signal.signal}
            </div>
            <div className="text-[11px] text-muted-foreground font-mono uppercase tracking-wider">Signal</div>
          </div>
        </div>
      </div>
      <div className="px-5 py-4 space-y-3">
        <p className="text-xs text-muted-foreground leading-relaxed">
          {signal.reasoning}
        </p>
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: 'RSI', value: signal.rsi.toString() },
            { label: 'Volume', value: signal.volumeTrend },
            { label: 'Trend', value: signal.predictionTrend },
          ].map(item => (
            <div key={item.label} className="rounded-lg bg-muted/50 p-2.5 text-center">
              <div className="text-[10px] text-muted-foreground font-mono uppercase tracking-wider">{item.label}</div>
              <div className="font-mono text-sm font-semibold capitalize mt-0.5">{item.value}</div>
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}
