import { OHLCVData } from './stockData';

function seededRandom(seed: string) {
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(31, h) + seed.charCodeAt(i) | 0;
  }
  return function () {
    h = Math.imul(h ^ (h >>> 16), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    h ^= h >>> 16;
    return (h >>> 0) / 4294967296;
  };
}

export interface PredictionResult {
  model: string;
  predictions: number[];
  dates: string[];
  color: string;
}

function predictLSTM(data: OHLCVData[], days: number, seed: string): number[] {
  const rand = seededRandom('lstm-' + seed);
  const prices = data.map(d => d.close);
  const last = prices[prices.length - 1];
  const momentum = (prices[prices.length - 1] - prices[prices.length - 5]) / prices[prices.length - 5];
  const results: number[] = [];
  let current = last;
  for (let i = 0; i < days; i++) {
    const trend = momentum * 0.6 + (rand() - 0.45) * 0.02;
    current = current * (1 + trend * (1 / (1 + i * 0.1)));
    results.push(+current.toFixed(2));
  }
  return results;
}

function predictProphet(data: OHLCVData[], days: number, seed: string): number[] {
  const rand = seededRandom('prophet-' + seed);
  const prices = data.map(d => d.close);
  const last = prices[prices.length - 1];
  const sma20 = prices.slice(-20).reduce((a, b) => a + b, 0) / 20;
  const trend = (last - sma20) / sma20;
  const results: number[] = [];
  let current = last;
  for (let i = 0; i < days; i++) {
    const seasonality = Math.sin((i / 7) * Math.PI * 2) * 0.005;
    const drift = trend * 0.3 + seasonality + (rand() - 0.48) * 0.015;
    current = current * (1 + drift);
    results.push(+current.toFixed(2));
  }
  return results;
}

function predictXGBoost(data: OHLCVData[], days: number, seed: string): number[] {
  const rand = seededRandom('xgboost-' + seed);
  const prices = data.map(d => d.close);
  const last = prices[prices.length - 1];
  const volatility = prices.slice(-14).reduce((sum, p, i, arr) => {
    if (i === 0) return 0;
    return sum + Math.abs(p - arr[i - 1]) / arr[i - 1];
  }, 0) / 13;
  const results: number[] = [];
  let current = last;
  for (let i = 0; i < days; i++) {
    const meanReversion = (prices.slice(-30).reduce((a, b) => a + b, 0) / 30 - current) * 0.02;
    const noise = (rand() - 0.48) * volatility * 2;
    current = current * (1 + meanReversion / current + noise);
    results.push(+current.toFixed(2));
  }
  return results;
}

export function runPredictions(data: OHLCVData[], forecastDays: number = 14): PredictionResult[] {
  const seed = data.map(d => d.close).join(',').slice(0, 50);
  const lastDate = new Date(data[data.length - 1].date);
  const dates: string[] = [];
  let d = new Date(lastDate);
  for (let i = 0; i < forecastDays; i++) {
    d.setDate(d.getDate() + 1);
    while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1);
    dates.push(d.toISOString().split('T')[0]);
  }

  return [
    { model: 'LSTM', predictions: predictLSTM(data, forecastDays, seed), dates, color: 'hsl(174, 72%, 50%)' },
    { model: 'Prophet', predictions: predictProphet(data, forecastDays, seed), dates, color: 'hsl(280, 65%, 60%)' },
    { model: 'XGBoost', predictions: predictXGBoost(data, forecastDays, seed), dates, color: 'hsl(38, 92%, 50%)' },
  ];
}

export function getConfidenceGrade(predictions: PredictionResult[]): string {
  const lastPreds = predictions.map(p => p.predictions[p.predictions.length - 1]);
  const avg = lastPreds.reduce((a, b) => a + b, 0) / lastPreds.length;
  const spread = Math.max(...lastPreds) - Math.min(...lastPreds);
  const spreadPct = spread / avg;
  if (spreadPct < 0.02) return 'A';
  if (spreadPct < 0.04) return 'B';
  if (spreadPct < 0.07) return 'C';
  if (spreadPct < 0.12) return 'D';
  return 'F';
}

export function getPredictedDirection(predictions: PredictionResult[], currentPrice: number): 'up' | 'down' {
  const avgFinal = predictions.reduce((s, p) => s + p.predictions[p.predictions.length - 1], 0) / predictions.length;
  return avgFinal > currentPrice ? 'up' : 'down';
}
