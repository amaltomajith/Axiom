import { TraceEvent } from '../core/models';
import { RunStatus } from './state/run.reducer';

export type StepId = 'router' | 'technical' | 'fundamental' | 'risk' | 'synthesis' | 'critic' | 'policy';
export type StepState = 'pending' | 'active' | 'done' | 'warn' | 'stopped';

export interface Step {
  id: StepId;
  label: string;
  state: StepState;
  /** what it is doing now, or what it produced */
  detail: string;
}

const LABEL: Record<StepId, string> = {
  router: 'Router',
  technical: 'Technical analyst',
  fundamental: 'Fundamental auditor',
  risk: 'Risk guard',
  synthesis: 'Lead synthesizer',
  critic: 'Risk critic',
  policy: 'Policy',
};

const ORDER: StepId[] = ['router', 'technical', 'fundamental', 'risk', 'synthesis', 'critic', 'policy'];

/**
 * Pipeline progress derived only from trace events (the same rules as the React app's useTraceProgress), so the
 * screen never invents progress: a step is done only when the backend said so.
 */
export function deriveSteps(events: TraceEvent[], status: RunStatus): Step[] {
  const of = (agent: string) => events.filter(e => e.agent === agent);
  const has = (agent: string, type: string) => events.some(e => e.agent === agent && e.type === type);
  const handedTo = (agent: string) => events.some(e => e.type === 'handoff' && e.data['to'] === agent);
  const lastTool = (agent: string) => {
    const calls = of(agent).filter(e => e.type === 'tool_call');
    return calls.length ? String(calls[calls.length - 1].data['tool']) : '';
  };
  const finished = status === 'done' || events.some(e => e.type === 'final');
  const draftSeen = events.some(e => e.type === 'memo_draft');
  const stoppedEarly = status === 'error' || status === 'cancelled';

  const steps = ORDER.map((id): Step => {
    let state: StepState = 'pending';
    let detail = '';
    if (id === 'router') {
      const start = events.find(e => e.type === 'run_start');
      if (start) {
        state = 'done';
        detail = `Routed to ${String(start.data['ticker'] ?? '')}`;
      } else if (status === 'connecting' || status === 'retrying' || status === 'queued') {
        state = 'active';
        detail = status === 'queued' ? 'Waiting for another run to finish' : 'Connecting';
      }
    } else if (id === 'technical' || id === 'fundamental') {
      const agent = id === 'technical' ? 'Technical Analyst' : 'Fundamental Auditor';
      const finding = of(agent).find(e => e.type === 'finding');
      if (has(agent, 'agent_error')) {
        state = 'warn';
        detail = 'Could not complete; conviction is capped';
      } else if (finding) {
        state = 'done';
        const stance = String(finding.data['stance'] ?? '').replace('_', ' ');
        detail = `${stance} at ${Math.round(Number(finding.data['confidence'] ?? 0) * 100)}% confidence`;
      } else if (has(agent, 'agent_start')) {
        state = 'active';
        detail = lastTool(agent) ? `Calling ${lastTool(agent)}` : 'Reading the data';
      }
    } else if (id === 'risk') {
      const calls = of('Risk Guard').filter(e => e.type === 'tool_call').length;
      if (handedTo('Lead Synthesizer') || finished) {
        state = 'done';
        detail = `${calls} risk tool calls`;
      } else if (handedTo('Risk Guard')) {
        state = 'active';
        detail = lastTool('Risk Guard') ? `Calling ${lastTool('Risk Guard')}` : 'Sizing the position';
      }
    } else if (id === 'synthesis') {
      if (has('Lead Synthesizer', 'agent_error')) {
        state = 'warn';
        detail = 'Fell back to a rule-based memo';
      } else if (has('Lead Synthesizer', 'agent_done') || draftSeen || finished) {
        state = 'done';
        detail = 'Both sides argued, draft written';
      } else if (handedTo('Lead Synthesizer')) {
        state = 'active';
        detail = 'Writing the memo';
      }
    } else if (id === 'critic') {
      const critique = of('Risk Critic').find(e => e.type === 'critique');
      if (has('Risk Critic', 'guardrail')) {
        state = 'warn';
        detail = 'Critic output was invalid; skipped';
      } else if (critique) {
        const issues = (critique.data['issues'] as unknown[] | undefined)?.length ?? 0;
        state = 'done';
        detail = critique.data['ok'] ? 'No issues raised' : `${issues} issue${issues === 1 ? '' : 's'} raised, draft revised`;
      } else if (has('Risk Critic', 'agent_start')) {
        state = 'active';
        detail = 'Reviewing the draft';
      } else if (has('Lead Synthesizer', 'agent_error') && (draftSeen || finished)) {
        state = 'done';
        detail = 'Skipped: there was no draft to review';
      } else if (draftSeen || finished) {
        state = 'done';
        detail = 'Skipped to stay inside the token budget';
      }
    } else {
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

  return stoppedEarly ? steps.map(s => (s.state === 'active' ? { ...s, state: 'stopped', detail: 'Stopped' } : s)) : steps;
}
