import { useMemo } from 'react';
import type { StreamStatus } from '@/hooks/useAgentStream';
import type { TraceEvent } from '@/lib/types';

export type StepId = 'technical' | 'fundamental' | 'risk' | 'synthesis' | 'policy';
export type StepState = 'pending' | 'active' | 'done' | 'warn';

export interface Step {
  id: StepId;
  label: string;
  state: StepState;
  /** short live description: what it is doing now, or what it produced */
  detail: string;
}

const AGENT: Record<StepId, string> = {
  technical: 'Technical Analyst',
  fundamental: 'Fundamental Auditor',
  risk: 'Risk Guard',
  synthesis: 'Lead Synthesizer',
  policy: 'Policy',
};

const LABEL: Record<StepId, string> = {
  technical: 'Technical analysis',
  fundamental: 'Fundamental review',
  risk: 'Risk and sizing',
  synthesis: 'Debate and memo',
  policy: 'Policy checks',
};

const ORDER: StepId[] = ['technical', 'fundamental', 'risk', 'synthesis', 'policy'];

/**
 * Pure derivation of pipeline progress from the raw trace. Kept separate from the hook so it is unit-testable
 * and the UI never invents progress: a step is only "done" when the backend said so.
 */
export function deriveProgress(events: TraceEvent[], status: StreamStatus): Step[] {
  const by = (agent: string) => events.filter(e => e.agent === agent);
  const has = (agent: string, type: string) => events.some(e => e.agent === agent && e.type === type);
  const finalSeen = events.some(e => e.type === 'final');
  const draftSeen = events.some(e => e.type === 'memo_draft');
  const finished = status === 'done' || finalSeen;

  return ORDER.map<Step>(id => {
    const agent = AGENT[id];
    const mine = by(agent);
    const tools = mine.filter(e => e.type === 'tool_call');
    const lastTool = tools[tools.length - 1]?.data.tool as string | undefined;
    let state: StepState = 'pending';
    let detail = '';

    if (id === 'technical' || id === 'fundamental') {
      if (has(agent, 'agent_error')) {
        state = 'warn';
        detail = 'Could not complete; conviction is capped';
      } else if (has(agent, 'finding')) {
        const f = mine.find(e => e.type === 'finding');
        state = 'done';
        detail = `${String(f?.data.stance ?? '').replace('_', ' ')} at ${Math.round(Number(f?.data.confidence ?? 0) * 100)}% confidence`;
      } else if (has(agent, 'agent_start')) {
        state = 'active';
        detail = lastTool ? `Calling ${lastTool}` : 'Reading the data';
      }
    } else if (id === 'risk') {
      const handedToRisk = events.some(e => e.type === 'handoff' && e.data.to === 'Risk Guard');
      const handedOn = events.some(e => e.type === 'handoff' && e.data.to === 'Lead Synthesizer');
      if (handedOn || finished) {
        state = 'done';
        detail = `${tools.length} risk tool calls`;
      } else if (handedToRisk) {
        state = 'active';
        detail = lastTool ? `Calling ${lastTool}` : 'Sizing the position';
      }
    } else if (id === 'synthesis') {
      if (draftSeen || finished) {
        state = 'done';
        detail = 'Both sides argued, draft written';
      } else if (has(agent, 'agent_start') || events.some(e => e.agent === 'Risk Critic')) {
        state = 'active';
        detail = events.some(e => e.agent === 'Risk Critic') ? 'A critic is reviewing the draft' : 'Writing the memo';
      }
    } else if (id === 'policy') {
      const caps = events.filter(e => e.type === 'guardrail' && e.agent === 'Policy').length;
      if (finished) {
        state = 'done';
        detail = caps ? `${caps} adjustment${caps > 1 ? 's' : ''} applied` : 'No adjustments needed';
      } else if (draftSeen) {
        state = 'active';
        detail = 'Checking the call against the evidence';
      }
    }
    return { id, label: LABEL[id], state, detail };
  });
}

export function useTraceProgress(events: TraceEvent[], status: StreamStatus) {
  return useMemo(() => {
    const steps = deriveProgress(events, status);
    const tokens = events
      .filter(e => e.type === 'llm_call' && !e.data.cached)
      .reduce((s, e) => s + Number(e.data.prompt_tokens ?? 0) + Number(e.data.completion_tokens ?? 0), 0);
    const guardrails = events.filter(e => e.type === 'guardrail').length;
    return { steps, tokens, guardrails };
  }, [events, status]);
}
