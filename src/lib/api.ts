import { supabase } from '@/integrations/supabase/client';
import { OHLCVData } from './stockData';
import { NewsItem } from './news';

// --- In-memory cache with TTL ---
interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

const cache = new Map<string, CacheEntry<unknown>>();

const CACHE_TTL = {
  stockData: 5 * 60 * 1000,   // 5 minutes for price data
  news: 15 * 60 * 1000,       // 15 minutes for news
};

function getCached<T>(key: string, ttl: number): T | null {
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.timestamp > ttl) {
    cache.delete(key);
    return null;
  }
  return entry.data as T;
}

function setCache<T>(key: string, data: T): void {
  cache.set(key, { data, timestamp: Date.now() });
}

export function clearCache(ticker?: string): void {
  if (ticker) {
    for (const key of cache.keys()) {
      if (key.includes(ticker)) cache.delete(key);
    }
  } else {
    cache.clear();
  }
}

// --- API functions with caching ---

export async function fetchStockData(ticker: string, outputsize: number = 60): Promise<OHLCVData[]> {
  const cacheKey = `stock:${ticker}:${outputsize}`;
  const cached = getCached<OHLCVData[]>(cacheKey, CACHE_TTL.stockData);
  if (cached) return cached;

  const { data, error } = await supabase.functions.invoke('stock-data', {
    body: { ticker, outputsize },
  });

  if (error) throw new Error(`Stock data error: ${error.message}`);
  if (data?.error) throw new Error(data.error);

  const result = data.data as OHLCVData[];
  setCache(cacheKey, result);
  return result;
}

export interface FinnhubNewsItem {
  id: string;
  headline: string;
  summary: string;
  source: string;
  url: string;
  date: string;
  image: string;
  category: string;
}

export interface FinnhubSentiment {
  buzz?: { articlesInLastWeek: number; buzz: number; weeklyAverage: number };
  companyNewsScore?: number;
  sectorAverageBullishPercent?: number;
  sectorAverageNewsScore?: number;
  sentiment?: { bearishPercent: number; bullishPercent: number };
}

export async function fetchStockNews(ticker: string): Promise<{ news: FinnhubNewsItem[]; sentiment: FinnhubSentiment | null }> {
  const cacheKey = `news:${ticker}`;
  const cached = getCached<{ news: FinnhubNewsItem[]; sentiment: FinnhubSentiment | null }>(cacheKey, CACHE_TTL.news);
  if (cached) return cached;

  const { data, error } = await supabase.functions.invoke('stock-news', {
    body: { ticker },
  });

  if (error) throw new Error(`News error: ${error.message}`);
  if (data?.error) throw new Error(data.error);

  const result = { news: data.news, sentiment: data.sentiment };
  setCache(cacheKey, result);
  return result;
}

// Convert Finnhub news to app NewsItem format with simple sentiment scoring
export function convertToNewsItems(finnhubNews: FinnhubNewsItem[]): NewsItem[] {
  const positiveWords = ['beat', 'surge', 'upgrade', 'growth', 'record', 'buy', 'bullish', 'strong', 'gain', 'profit', 'rise', 'soar', 'boost', 'rally', 'outperform'];
  const negativeWords = ['miss', 'fall', 'downgrade', 'decline', 'loss', 'sell', 'bearish', 'weak', 'drop', 'crash', 'cut', 'lawsuit', 'investigation', 'recall', 'concern'];

  return finnhubNews.slice(0, 5).map((n) => {
    const text = (n.headline + ' ' + (n.summary || '')).toLowerCase();
    let score = 0;
    positiveWords.forEach(w => { if (text.includes(w)) score += 0.15; });
    negativeWords.forEach(w => { if (text.includes(w)) score -= 0.15; });
    score = Math.max(-1, Math.min(1, score));

    const sentiment: NewsItem['sentiment'] = score > 0.1 ? 'Positive' : score < -0.1 ? 'Negative' : 'Neutral';

    return {
      id: n.id,
      headline: n.headline,
      sentiment,
      score: +score.toFixed(2),
      date: n.date,
      source: n.source,
    };
  });
}
