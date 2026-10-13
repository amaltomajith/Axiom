import { useEffect, useMemo, useRef, useState } from 'react';
import { Drawer } from 'vaul';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Segmented } from '@/components/kit/Segmented';
import { useIsMobile } from '@/hooks/use-mobile';
import type { StreamStatus } from '@/hooks/useAgentStream';
import type { TraceEvent } from '@/lib/types';
import { cn } from '@/lib/utils';

const str = (v: unknown): string => (typeof v === 'string' ? v : JSON.stringify(v));

export interface TraceLine {
  key: number;
  agent: string;
  tag: string;
  text: string;
  tone?: 'warn' | 'ok' | 'err' | 'dim';
  detail?: string;
  group: 'tools' | 'guards' | 'other';
}

/** Raw trace events to readable lines. Pure, so it is unit-tested. */
export function describeEvent(e: TraceEvent): TraceLine | null {
  const d = e.data;
  const base = { key: e.seq, agent: e.agent };
  switch (e.type) {
    case 'run_start':
      return { ...base, tag: 'Run', text: `Analysis started for ${str(d.ticker)}`, group: 'other' };
    case 'agent_start':
      return { ...base, tag: 'Agent', text: `Started with ${(d.tools as string[] | undefined)?.length ?? 0} tools`, group: 'other' };
    case 'handoff':
      return { ...base, tag: 'Handoff', text: `To ${str(d.to)}: ${str(d.reason)}`, group: 'other' };
    case 'tool_call':
      return {
        ...base,
        tag: 'Tool',
        text: `${str(d.tool)}(${Object.entries((d.args as object) ?? {}).map(([k, v]) => `${k}=${str(v)}`).join(', ')})`,
        detail: JSON.stringify(d.args, null, 2),
        group: 'tools',
      };
    case 'tool_result':
      return {
        ...base,
        tag: d.ok ? 'Result' : 'Failed',
        text: `${str(d.tool)} ${d.ok ? `saved as ${str(d.evidence_id)}` : 'returned an error'}, ${str(d.latency_ms)} ms`,
        tone: d.ok ? 'ok' : 'err',
        detail: str(d.preview),
        group: 'tools',
      };
    case 'llm_call':
      return {
        ...base,
        tag: 'Model',
        text: `${str(d.provider)} ${str(d.model)}, ${str(d.prompt_tokens)} in / ${str(d.completion_tokens)} out${d.cached ? ', cached' : ''}`,
        tone: 'dim',
        group: 'other',
      };
    case 'guardrail':
      return { ...base, tag: 'Guard', text: `${str(d.name)}: ${str(d.detail ?? '')}`, tone: 'warn', group: 'guards' };
    case 'finding':
      return { ...base, tag: 'Finding', text: `${str(d.stance)} at ${Math.round(Number(d.confidence) * 100)}%: ${str(d.summary)}`, tone: 'ok', group: 'other' };
    case 'critique':
      return { ...base, tag: 'Review', text: d.ok ? 'No issues found' : `Issues: ${(d.issues as string[]).join('; ')}`, tone: d.ok ? 'ok' : 'warn', group: 'other' };
    case 'memo_draft':
      return { ...base, tag: 'Draft', text: `Draft rating ${str(d.rating)} at ${Math.round(Number(d.conviction) * 100)}%, before policy checks`, group: 'other' };
    case 'final':
      return { ...base, tag: 'Final', text: `Rating ${str(d.rating)}, conviction ${Math.round(Number(d.conviction) * 100)}%`, tone: 'ok', group: 'other' };
    case 'agent_error':
    case 'error':
      return { ...base, tag: 'Error', text: str(d.message ?? d.error), tone: 'err', group: 'other' };
    case 'run_end':
      return { ...base, tag: 'Done', text: 'Run complete', tone: 'ok', group: 'other' };
    default:
      return null;
  }
}

const TONE = { warn: 'text-warning', ok: 'text-foreground', err: 'text-destructive', dim: 'text-muted-foreground' } as const;
type Filter = 'all' | 'tools' | 'guards';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  events: TraceEvent[];
  status: StreamStatus;
  error: string | null;
}

/**
 * The agent trace as a drawer. vaul gives momentum and velocity-aware dismissal for free: it slides in from the
 * right on desktop and up from the bottom on phones, and leaves along the same path it arrived.
 */
export function AgentTraceDrawer({ open, onOpenChange, events, status, error }: Props) {
  const mobile = useIsMobile();
  const [filter, setFilter] = useState<Filter>('all');
  const lines = useMemo(() => events.map(describeEvent).filter((l): l is TraceLine => l !== null), [events]);
  const shown = lines.filter(l => filter === 'all' || l.group === filter);
  const tokens = useMemo(
    () => events.filter(e => e.type === 'llm_call' && !e.data.cached).reduce((s, e) => s + Number(e.data.prompt_tokens ?? 0) + Number(e.data.completion_tokens ?? 0), 0),
    [events],
  );
  const guards = lines.filter(l => l.group === 'guards').length;
  const endRef = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);

  useEffect(() => {
    if (open && pinned.current) endRef.current?.scrollIntoView({ block: 'end' });
  }, [shown.length, open]);

  return (
    <Drawer.Root open={open} onOpenChange={onOpenChange} direction={mobile ? 'bottom' : 'right'} shouldScaleBackground={false}>
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-50 bg-foreground/25" />
        <Drawer.Content
          aria-describedby={undefined}
          className={cn(
            'fixed z-50 flex flex-col bg-card shadow-md outline-none',
            mobile ? 'inset-x-0 bottom-0 h-[88dvh] rounded-t-xl border-t border-border' : 'inset-y-3 right-3 w-[min(560px,calc(100vw-1.5rem))] rounded-xl border border-border',
          )}
        >
          {mobile && <div className="mx-auto mt-2 h-1.5 w-10 rounded-full bg-border" aria-hidden />}
          <header className="flex items-start justify-between gap-4 px-5 pb-3 pt-4">
            <div>
              <Drawer.Title className="text-h3">Agent trace</Drawer.Title>
              <p className="mt-0.5 tnum text-caption text-muted-foreground">
                {status === 'queued' ? 'Queued behind another run' : status}, {lines.length} events, {tokens.toLocaleString()} tokens
                {guards > 0 && <span className="text-warning">, {guards} guardrail events</span>}
              </p>
            </div>
            <Button variant="ghost" size="icon-sm" onClick={() => onOpenChange(false)} aria-label="Close trace">
              <X />
            </Button>
          </header>
          <div className="px-5 pb-3">
            <Segmented<Filter>
              size="sm"
              ariaLabel="Filter events"
              value={filter}
              onChange={setFilter}
              options={[
                { value: 'all', label: 'All' },
                { value: 'tools', label: 'Tools' },
                { value: 'guards', label: 'Guardrails', badge: guards || undefined },
              ]}
            />
          </div>
          <div
            className="flex-1 overflow-y-auto overscroll-contain border-t border-border px-5 py-3"
            onScroll={e => {
              const el = e.currentTarget;
              pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
            }}
          >
            {shown.length === 0 && <p className="py-6 text-small text-muted-foreground">{lines.length === 0 ? 'Waiting for the first event…' : 'Nothing in this filter yet.'}</p>}
            <ul className="space-y-2.5">
              {shown.map(l => (
                <li key={l.key} className="grid grid-cols-[5.25rem_1fr] gap-x-3 text-small sm:grid-cols-[7.5rem_3.75rem_1fr]">
                  <span className="truncate font-medium text-foreground/80 max-sm:col-span-2 sm:col-span-1">{l.agent}</span>
                  <span className="text-caption text-muted-foreground max-sm:pt-0.5 sm:pt-0.5">{l.tag}</span>
                  <div className="min-w-0">
                    <p className={cn('break-words', l.tone && TONE[l.tone], l.tag === 'Tool' && 'font-mono text-caption')}>{l.text}</p>
                    {l.detail && (
                      <details className="mt-1">
                        <summary className="w-fit cursor-pointer text-caption text-muted-foreground hover:text-foreground">Details</summary>
                        <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-sm bg-muted p-2 font-mono text-caption">{l.detail}</pre>
                      </details>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            {error && <p className="pt-3 text-small text-destructive">{error}</p>}
            <div ref={endRef} />
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
