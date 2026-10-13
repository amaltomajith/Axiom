import { Activity, TriangleAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PipelineStepper } from '@/components/PipelineStepper';
import { Section } from '@/components/kit/Surface';
import { MemoPanel } from '@/components/MemoPanel';
import type { StreamStatus } from '@/hooks/useAgentStream';
import { useTraceProgress } from '@/hooks/useTraceProgress';
import type { AnalysisResult, TraceEvent } from '@/lib/types';

interface Props {
  status: StreamStatus;
  events: TraceEvent[];
  result: AnalysisResult | null;
  error: string | null;
  onOpenTrace: () => void;
}

/**
 * One panel that is always in the same place and cycles idle, running, result in place: the page grid never re-flows.
 */
export function AgentPanel({ status, events, result, error, onOpenTrace }: Props) {
  const { steps, tokens, guardrails } = useTraceProgress(events, status);
  const running = status === 'running' || status === 'queued';

  if (result) return <MemoPanel result={result} onOpenTrace={onOpenTrace} />;

  if (status === 'error') {
    return (
      <Section title="Analysis stopped" description="Nothing was recorded for this run">
        <div role="alert" className="flex gap-2.5 border-t border-border px-5 py-4 text-small sm:px-6">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <p className="text-muted-foreground">{error}</p>
        </div>
        {events.length > 0 && (
          <div className="border-t border-border px-5 py-3 sm:px-6">
            <Button variant="ghost" size="xs" onClick={onOpenTrace}>
              <Activity /> Open the trace
            </Button>
          </div>
        )}
      </Section>
    );
  }

  return (
    <Section
      title="Agent analysis"
      description={running ? (status === 'queued' ? 'Queued behind another run' : 'Working through the pipeline') : 'Every number is cited'}
    >
      <div className="border-t border-border px-5 py-5 sm:px-6">
        <PipelineStepper steps={steps} />
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-border px-5 py-3 sm:px-6">
        {running ? (
          <>
            <p className="tnum text-caption text-muted-foreground" aria-live="polite">
              {tokens.toLocaleString()} tokens{guardrails > 0 ? `, ${guardrails} guardrail events` : ''}
            </p>
            <Button variant="ghost" size="xs" onClick={onOpenTrace}>
              <Activity /> Open trace
            </Button>
          </>
        ) : (
          <p className="text-caption text-muted-foreground">Press Run analysis. Each claim in the memo links to the tool call that produced it.</p>
        )}
      </div>
    </Section>
  );
}
