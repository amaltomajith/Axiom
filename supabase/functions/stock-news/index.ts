import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version',
};

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  const FINNHUB_API_KEY = Deno.env.get('FINNHUB_API_KEY');
  if (!FINNHUB_API_KEY) {
    return new Response(JSON.stringify({ error: 'FINNHUB_API_KEY is not configured' }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }

  try {
    const { ticker } = await req.json();
    if (!ticker) {
      return new Response(JSON.stringify({ error: 'ticker is required' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    // Get date range: last 7 days
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - 7);
    const fromStr = from.toISOString().split('T')[0];
    const toStr = to.toISOString().split('T')[0];

    const url = `https://finnhub.io/api/v1/company-news?symbol=${encodeURIComponent(ticker)}&from=${fromStr}&to=${toStr}&token=${FINNHUB_API_KEY}`;

    const response = await fetch(url);
    const articles = await response.json();

    if (!Array.isArray(articles)) {
      return new Response(JSON.stringify({ error: 'Finnhub API error', details: articles }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    // Take top 10 articles and format
    const news = articles.slice(0, 10).map((a: any, i: number) => ({
      id: `news-${ticker}-${i}`,
      headline: a.headline,
      summary: a.summary,
      source: a.source,
      url: a.url,
      date: new Date(a.datetime * 1000).toISOString().split('T')[0],
      image: a.image,
      category: a.category,
    }));

    // Also fetch sentiment from Finnhub
    const sentimentUrl = `https://finnhub.io/api/v1/news-sentiment?symbol=${encodeURIComponent(ticker)}&token=${FINNHUB_API_KEY}`;
    let sentiment = null;
    try {
      const sentRes = await fetch(sentimentUrl);
      sentiment = await sentRes.json();
    } catch {
      // Sentiment is optional
    }

    return new Response(JSON.stringify({ news, sentiment }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'Unknown error';
    return new Response(JSON.stringify({ error: msg }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
