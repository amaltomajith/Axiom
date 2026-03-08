import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version',
};

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  const TWELVEDATA_API_KEY = Deno.env.get('TWELVEDATA_API_KEY');
  if (!TWELVEDATA_API_KEY) {
    return new Response(JSON.stringify({ error: 'TWELVEDATA_API_KEY is not configured' }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }

  try {
    const { ticker, outputsize } = await req.json();
    if (!ticker) {
      return new Response(JSON.stringify({ error: 'ticker is required' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const size = outputsize || 60;
    const url = `https://api.twelvedata.com/time_series?symbol=${encodeURIComponent(ticker)}&interval=1day&outputsize=${size}&apikey=${TWELVEDATA_API_KEY}`;

    const response = await fetch(url);
    const data = await response.json();

    if (data.status === 'error') {
      return new Response(JSON.stringify({ error: data.message || 'Twelve Data API error' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    // Transform to OHLCV format
    const values = data.values || [];
    const ohlcv = values.map((v: any) => ({
      date: v.datetime,
      open: parseFloat(v.open),
      high: parseFloat(v.high),
      low: parseFloat(v.low),
      close: parseFloat(v.close),
      volume: parseInt(v.volume) || 0,
    })).reverse(); // API returns newest first, we want oldest first

    return new Response(JSON.stringify({ data: ohlcv, meta: data.meta }), {
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
