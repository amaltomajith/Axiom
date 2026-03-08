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

export interface NewsItem {
  id: string;
  headline: string;
  sentiment: 'Positive' | 'Neutral' | 'Negative';
  score: number;
  date: string;
  source: string;
}

const POSITIVE_TEMPLATES = [
  '{ticker} beats Q4 earnings expectations by 12%, shares surge',
  'Analysts upgrade {ticker} to "Strong Buy" on AI growth potential',
  '{ticker} announces $5B share buyback program',
  '{ticker} secures major government contract worth $2.3B',
  'Institutional investors increase {ticker} holdings by 15%',
  '{ticker} launches revolutionary product, pre-orders exceed expectations',
  '{ticker} reports record revenue growth of 28% year-over-year',
];

const NEGATIVE_TEMPLATES = [
  '{ticker} faces SEC investigation over accounting practices',
  'Supply chain disruptions could impact {ticker} Q1 deliveries',
  '{ticker} loses key patent lawsuit, ordered to pay $800M',
  'Short sellers increase bets against {ticker} amid valuation concerns',
  '{ticker} CFO unexpectedly resigns, sparking investor concerns',
  '{ticker} recalls product line due to safety concerns',
];

const NEUTRAL_TEMPLATES = [
  '{ticker} announces new board member appointment',
  '{ticker} to present at upcoming Goldman Sachs tech conference',
  'Market analysts maintain "Hold" rating on {ticker}',
  '{ticker} files patent for next-gen technology platform',
  '{ticker} completes routine facility expansion in Arizona',
];

const SOURCES = ['Bloomberg', 'Reuters', 'CNBC', 'WSJ', 'MarketWatch', 'Barrons', 'Financial Times'];

export function generateNews(ticker: string): NewsItem[] {
  const rand = seededRandom('news-' + ticker + new Date().toDateString());
  const items: NewsItem[] = [];

  for (let i = 0; i < 5; i++) {
    const r = rand();
    let templates: string[];
    let sentiment: NewsItem['sentiment'];
    let score: number;

    if (r < 0.4) {
      templates = POSITIVE_TEMPLATES;
      sentiment = 'Positive';
      score = +(0.3 + rand() * 0.7).toFixed(2);
    } else if (r < 0.7) {
      templates = NEGATIVE_TEMPLATES;
      sentiment = 'Negative';
      score = +(-0.3 - rand() * 0.7).toFixed(2);
    } else {
      templates = NEUTRAL_TEMPLATES;
      sentiment = 'Neutral';
      score = +((rand() - 0.5) * 0.4).toFixed(2);
    }

    const template = templates[Math.floor(rand() * templates.length)];
    const date = new Date();
    date.setDate(date.getDate() - i);

    items.push({
      id: `news-${ticker}-${i}`,
      headline: template.replace('{ticker}', ticker),
      sentiment,
      score,
      date: date.toISOString().split('T')[0],
      source: SOURCES[Math.floor(rand() * SOURCES.length)],
    });
  }

  return items;
}

export function getNetSentiment(news: NewsItem[]): { score: number; label: string } {
  const avg = news.reduce((s, n) => s + n.score, 0) / news.length;
  const label = avg > 0.2 ? 'Bullish' : avg < -0.2 ? 'Bearish' : 'Neutral';
  return { score: +avg.toFixed(2), label };
}
