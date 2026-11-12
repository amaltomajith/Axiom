// A fixed public address for the Autopilot. KV key "origin" is where visitors go: the deployed cockpit on Vercel, or
// a laptop behind a Cloudflare quick tunnel whose URL changes on every restart (scripts/live-demo.sh writes it).
// This Worker sends each visitor there with a redirect, after checking it answers. KV key "ping" is the always-on
// Autopilot API on Render's free plan, which sleeps after 15 idle minutes: a cron trigger calls it every 10.
//
// It redirects instead of proxying so a cockpit tab that polls every few seconds talks to the tunnel directly
// and does not use up the free plan's daily Worker requests (one request per visit, not one per poll).
// No secrets pass through here: the API token travels from the visitor's browser to the tunnel only.

const PAGE = (title, body) =>
  new Response(
    `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="20"><title>${title}</title>
<style>
:root{color-scheme:dark;--bg:#0a0d12;--fg:#e6edf5;--muted:#93a1b3;--accent:#38bdf8;--line:#1e2633}
body{margin:0;min-height:100dvh;display:grid;place-items:center;background:var(--bg);color:var(--fg);
font:16px/1.6 system-ui,-apple-system,Segoe UI,sans-serif;padding:16px}
main{max-width:560px;border:1px solid var(--line);border-radius:16px;padding:32px}
h1{font-size:22px;margin:0 0 8px}p{color:var(--muted);margin:8px 0}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--accent);margin-right:8px;animation:p 1.6s infinite}
@keyframes p{50%{opacity:.3}}
</style></head><body><main><h1><span class="dot"></span>${title}</h1>${body}</main></body></html>`,
    { status: 503, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store', 'retry-after': '20' } },
  );

const allowed = origin => !!origin && /^https:\/\/[a-z0-9-]+\.(trycloudflare\.com|vercel\.app|onrender\.com)$/.test(origin);

export default {
  async scheduled(_event, env, ctx) {
    const origin = await env.ORIGIN.get('ping');
    if (allowed(origin)) ctx.waitUntil(fetch(`${origin}/api/health`, { signal: AbortSignal.timeout(20000) }).catch(() => null));
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/favicon.ico') return new Response(null, { status: 204 });
    const origin = await env.ORIGIN.get('origin', { cacheTtl: 60 });
    if (!allowed(origin)) {
      return PAGE('Axiom Autopilot is offline', '<p>The paper-trading agent is not connected right now.</p><p>This page checks again every 20 seconds.</p>');
    }
    try {
      const health = await fetch(`${origin}/api/health`, { signal: AbortSignal.timeout(6000), cf: { cacheTtl: 0 } });
      if (!health.ok) throw new Error(`health ${health.status}`);
    } catch {
      return PAGE('Axiom Autopilot is reconnecting', '<p>The agent is restarting or waking up. This usually takes under a minute.</p><p>This page checks again every 20 seconds.</p>');
    }
    const path = url.pathname === '/' ? '/app' : url.pathname;
    return Response.redirect(`${origin}${path}${url.search}`, 302);
  },
};
