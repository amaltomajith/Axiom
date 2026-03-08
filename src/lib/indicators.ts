import { OHLCVData } from './stockData';

export function calculateRSI(data: OHLCVData[], period: number = 14): number {
  if (data.length < period + 1) return 50;
  const changes = data.slice(-period - 1).map((d, i, arr) =>
    i === 0 ? 0 : d.close - arr[i - 1].close
  ).slice(1);

  const gains = changes.filter(c => c > 0);
  const losses = changes.filter(c => c < 0).map(c => Math.abs(c));
  const avgGain = gains.reduce((a, b) => a + b, 0) / period;
  const avgLoss = losses.reduce((a, b) => a + b, 0) / period;

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return +(100 - 100 / (1 + rs)).toFixed(1);
}

export function calculateSMA(data: OHLCVData[], period: number): number {
  const slice = data.slice(-period);
  return +(slice.reduce((sum, d) => sum + d.close, 0) / slice.length).toFixed(2);
}

export function getVolumeTrend(data: OHLCVData[]): 'increasing' | 'decreasing' | 'stable' {
  if (data.length < 10) return 'stable';
  const recent = data.slice(-5).reduce((s, d) => s + d.volume, 0) / 5;
  const older = data.slice(-10, -5).reduce((s, d) => s + d.volume, 0) / 5;
  const ratio = recent / older;
  if (ratio > 1.15) return 'increasing';
  if (ratio < 0.85) return 'decreasing';
  return 'stable';
}

export type Signal = 'BUY' | 'HOLD' | 'SELL';

export interface SignalResult {
  signal: Signal;
  reasoning: string;
  rsi: number;
  volumeTrend: string;
  predictionTrend: string;
}

export function generateSignal(
  data: OHLCVData[],
  predictions: { lstm: number[]; prophet: number[]; xgboost: number[] }
): SignalResult {
  const rsi = calculateRSI(data);
  const volumeTrend = getVolumeTrend(data);
  const lastClose = data[data.length - 1].close;

  const lstmTrend = predictions.lstm[predictions.lstm.length - 1] > lastClose ? 'up' : 'down';
  const prophetTrend = predictions.prophet[predictions.prophet.length - 1] > lastClose ? 'up' : 'down';
  const xgbTrend = predictions.xgboost[predictions.xgboost.length - 1] > lastClose ? 'up' : 'down';

  const upVotes = [lstmTrend, prophetTrend, xgbTrend].filter(t => t === 'up').length;
  const predictionTrend = upVotes >= 2 ? 'bullish' : 'bearish';

  let score = 0;
  const reasons: string[] = [];

  if (rsi < 30) { score += 2; reasons.push(`RSI is oversold at ${rsi}`); }
  else if (rsi > 70) { score -= 2; reasons.push(`RSI is overbought at ${rsi}`); }
  else { reasons.push(`RSI is neutral at ${rsi}`); }

  if (predictionTrend === 'bullish') {
    score += upVotes === 3 ? 2 : 1;
    reasons.push(`${upVotes}/3 models predict upside`);
  } else {
    score -= (3 - upVotes) === 3 ? 2 : 1;
    reasons.push(`${3 - upVotes}/3 models predict downside`);
  }

  if (volumeTrend === 'increasing') {
    score += predictionTrend === 'bullish' ? 1 : -1;
    reasons.push('volume increasing');
  } else if (volumeTrend === 'decreasing') {
    reasons.push('volume decreasing');
  } else {
    reasons.push('volume stable');
  }

  const signal: Signal = score >= 2 ? 'BUY' : score <= -2 ? 'SELL' : 'HOLD';
  const sentiment = signal === 'BUY' ? 'Bullish' : signal === 'SELL' ? 'Bearish' : 'Neutral';

  return {
    signal,
    reasoning: `${reasons.join(', ')} — ${sentiment} signal`,
    rsi,
    volumeTrend,
    predictionTrend,
  };
}
