import { useEffect, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/hooks/use-toast';
import { ApiError, trader } from '@/lib/api';

/** Every trader query key starts with this, so one invalidation refreshes the whole cockpit. */
export const TRADER_KEY = 'trader';

/**
 * Subscribe to the trader's server-sent events for one session and refresh the cockpit when something
 * happens. Events are coalesced (at most one refresh every 700ms) so a fast Time Machine run cannot flood
 * the browser. Returns whether the stream is connected; without it the live queries poll every 5 seconds, so a
 * dropped stream only makes the cockpit a little slower, never stale.
 */
export function useTraderStream(session: string): boolean {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (typeof EventSource === 'undefined') return;
    const es = new EventSource(trader.streamUrl(session));
    const refresh = () => {
      if (timer.current != null) return;
      timer.current = window.setTimeout(() => {
        timer.current = null;
        qc.invalidateQueries({ queryKey: [TRADER_KEY] });
      }, 700);
    };
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    for (const kind of ['journal', 'order', 'state', 'tick', 'pending', 'replay', 'desk', 'desk_done']) es.addEventListener(kind, refresh);
    return () => {
      es.close();
      if (timer.current != null) window.clearTimeout(timer.current);
      timer.current = null;
      setConnected(false);
    };
  }, [session, qc]);

  // No stream (for example behind a Cloudflare quick tunnel, which does not carry SSE): poll the live parts faster.
  useEffect(() => {
    if (connected) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === 'hidden') return; // a background tab does not need to poll
      qc.invalidateQueries({ predicate: q => q.queryKey[0] === TRADER_KEY && LIVE_KEYS.has(String(q.queryKey[1])) });
    }, 5_000);
    return () => window.clearInterval(id);
  }, [connected, qc]);

  return connected;
}

const LIVE_KEYS = new Set(['status', 'positions', 'journal', 'equity', 'replays', 'desk']);

/** A trader control (POST) with the standard error toast and a cockpit refresh afterwards. */
export function useTraderAction<A, R>(fn: (arg: A) => Promise<R>, success?: (r: R) => string | null) {
  const qc = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: fn,
    onSuccess: r => {
      const msg = success?.(r);
      if (msg) toast({ title: msg });
    },
    onError: (e: unknown) => {
      const needsToken = e instanceof ApiError && (e.status === 401 || e.status === 403);
      toast({
        title: needsToken ? 'API token required' : 'The trader refused',
        description: needsToken ? `${(e as ApiError).message}. Set the token with the key icon in the header.` : e instanceof Error ? e.message : 'Unknown error',
        variant: 'destructive',
      });
    },
    onSettled: () => qc.invalidateQueries({ queryKey: [TRADER_KEY] }),
  });
}

export const shortTime = (ts: number): string =>
  new Date(ts * 1000).toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });

export const shortDate = (ts: number): string =>
  new Date(ts * 1000).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: '2-digit',
  });
