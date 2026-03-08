// Seeded random number generator for deterministic data per ticker
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

export interface OHLCVData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

const BASE_PRICES: Record<string, number> = {
  AAPL: 178,
  TSLA: 245,
  NVDA: 480,
  MSFT: 375,
  AMZN: 155,
  GOOGL: 140,
  META: 360,
  AMD: 120,
};

export const POPULAR_TICKERS = ['AAPL', 'TSLA', 'NVDA', 'MSFT', 'AMZN', 'GOOGL'];

export function generateHistoricalData(ticker: string, days: number = 60, endDate?: Date): OHLCVData[] {
  const rand = seededRandom(ticker + (endDate?.toISOString() || 'default'));
  const basePrice = BASE_PRICES[ticker.toUpperCase()] || (50 + seededRandom(ticker)() * 400);
  const data: OHLCVData[] = [];
  let price = basePrice;
  const end = endDate || new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - days);

  for (let i = 0; i < days; i++) {
    const date = new Date(start);
    date.setDate(date.getDate() + i);
    if (date.getDay() === 0 || date.getDay() === 6) continue;

    const drift = (rand() - 0.48) * 0.03;
    const volatility = (rand() - 0.5) * 0.04;
    const change = drift + volatility;
    price = price * (1 + change);
    price = Math.max(price, 1);

    const open = price * (1 + (rand() - 0.5) * 0.01);
    const close = price;
    const high = Math.max(open, close) * (1 + rand() * 0.015);
    const low = Math.min(open, close) * (1 - rand() * 0.015);
    const volume = Math.floor(5000000 + rand() * 50000000);

    data.push({
      date: date.toISOString().split('T')[0],
      open: +open.toFixed(2),
      high: +high.toFixed(2),
      low: +low.toFixed(2),
      close: +close.toFixed(2),
      volume,
    });
  }

  return data;
}

export function getCurrentPrice(ticker: string): number {
  const data = generateHistoricalData(ticker, 60);
  return data[data.length - 1]?.close || 100;
}
