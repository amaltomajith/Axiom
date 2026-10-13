import { Badge } from '@/components/ui/badge';
import { Section } from '@/components/kit/Surface';
import { Stat, StatRow } from '@/components/kit/Stat';
import { SkeletonBlock } from '@/components/kit/Skeleton';
import { num } from '@/lib/format';
import type { IndicatorsResponse, RegimeResponse } from '@/lib/types';

const TREND_VARIANT = { uptrend: 'success', downtrend: 'destructive', sideways: 'warning' } as const;

interface Props {
  indicators: IndicatorsResponse | null;
  regime: RegimeResponse | null;
  loading?: boolean;
}

export function IndicatorPanel({ indicators, regime, loading }: Props) {
  const v = indicators?.values;
  const trend = regime?.trend as keyof typeof TREND_VARIANT | undefined;
  return (
    <Section
      title="Technicals"
      description="Descriptive, not predictive"
      actions={
        regime && (
          <>
            <Badge variant={(trend && TREND_VARIANT[trend]) || 'neutral'}>{regime.trend.replace('_', ' ')}</Badge>
            <Badge>{`${regime.volatility} volatility`}</Badge>
          </>
        )
      }
    >
      {loading || !v ? (
        <div className="px-5 pb-5 sm:px-6" aria-hidden>
          <SkeletonBlock className="h-16 w-full" />
        </div>
      ) : (
        <>
          <StatRow className="border-t border-border">
            <Stat label="RSI (14)" value={num(v.rsi14, 0)} />
            <Stat label="MACD histogram" value={num(v.macd_hist, 2)} tone={v.macd_hist != null && v.macd_hist < 0 ? 'loss' : 'gain'} />
            <Stat label="ATR (14)" value={num(v.atr14, 2)} />
            <Stat label="Volatility (20d)" value={v.vol20_annualized == null ? 'n/a' : `${(v.vol20_annualized * 100).toFixed(0)}%`} />
          </StatRow>
          <ul className="grid gap-x-8 gap-y-1.5 border-t border-border px-5 py-4 text-small text-muted-foreground sm:grid-cols-2 sm:px-6">
            {indicators.reading.map(r => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </>
      )}
    </Section>
  );
}
