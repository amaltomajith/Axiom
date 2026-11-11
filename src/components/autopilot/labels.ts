/** Short, readable names for the tournament strategies (the ids stay in tooltips and facts). */
const STRATEGY: Record<string, string> = {
  sma_cross: 'SMA cross',
  macd_trend: 'MACD trend',
  rsi_reversion: 'RSI reversion',
  donchian_breakout: 'Donchian breakout',
  bollinger_reversion: 'Bollinger reversion',
};

export const strategyLabel = (id: string | null | undefined): string => (id ? (STRATEGY[id] ?? id.replace(/_/g, ' ')) : 'no strategy');
