import { useCallback, useEffect, useRef, useState } from 'react';
import { API_BASE, authHeaders } from '@/lib/api';
import { streamSse } from '@/lib/sse';
import type { AnalysisResult, TraceEvent } from '@/lib/types';

export type StreamStatus = 'idle' | 'queued' | 'running' | 'done' | 'error';

export interface AgentStream {
  status: StreamStatus;
  events: TraceEvent[];
  result: AnalysisResult | null;
  error: string | null;
  start: (ticker: string, equity?: number) => void;
  cancel: () => void;
  reset: () => void;
}

/** Runs an agent analysis and exposes its live trace. Aborts cleanly on unmount or restart. */
export function useAgentStream(): AgentStream {
  const [status, setStatus] = useState<StreamStatus>('idle');
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ctrl = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    ctrl.current?.abort();
    ctrl.current = null;
    setStatus(s => (s === 'running' || s === 'queued' ? 'idle' : s));
  }, []);

  const reset = useCallback(() => {
    cancel();
    setStatus('idle');
    setEvents([]);
    setResult(null);
    setError(null);
  }, [cancel]);

  const start = useCallback(
    (ticker: string, equity = 100_000) => {
      ctrl.current?.abort();
      const c = new AbortController();
      ctrl.current = c;
      setEvents([]);
      setResult(null);
      setError(null);
      setStatus('running');

      streamSse({
        url: `${API_BASE}/api/analyze`,
        body: { ticker, equity },
        headers: authHeaders(),
        signal: c.signal,
        onMessage: ({ event, data }) => {
          if (c.signal.aborted) return;
          const payload = JSON.parse(data);
          if (event === 'trace') setEvents(prev => [...prev, payload as TraceEvent]);
          else if (event === 'queued') setStatus('queued');
          else if (event === 'result') {
            setResult(payload as AnalysisResult);
            setStatus('done');
          } else if (event === 'error') {
            setError(payload.error ?? 'Analysis failed');
            setStatus('error');
          }
        },
      }).catch((e: unknown) => {
        if (c.signal.aborted) return;
        setError(e instanceof Error ? e.message : 'Connection lost');
        setStatus('error');
      });
    },
    [],
  );

  useEffect(() => () => ctrl.current?.abort(), []);

  return { status, events, result, error, start, cancel, reset };
}
