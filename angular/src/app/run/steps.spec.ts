import { trace } from '../../testing/fakes';
import { deriveSteps, StepState } from './steps';

const states = (s: ReturnType<typeof deriveSteps>): Record<string, StepState> => Object.fromEntries(s.map(x => [x.id, x.state]));

describe('deriveSteps', () => {
  it('shows only the router as active while connecting', () => {
    expect(states(deriveSteps([], 'connecting'))).toEqual({
      router: 'active',
      technical: 'pending',
      fundamental: 'pending',
      risk: 'pending',
      synthesis: 'pending',
      critic: 'pending',
      policy: 'pending',
    });
  });

  it('follows the pipeline from the trace alone', () => {
    const events = [
      trace('run_start', 'system', { ticker: 'AAPL' }),
      trace('agent_start', 'Technical Analyst'),
      trace('tool_call', 'Technical Analyst', { tool: 'get_indicators' }),
      trace('agent_start', 'Fundamental Auditor'),
      trace('finding', 'Technical Analyst', { stance: 'bullish', confidence: 0.7 }),
    ];
    const steps = deriveSteps(events, 'running');
    expect(states(steps)).toMatchObject({ router: 'done', technical: 'done', fundamental: 'active', risk: 'pending' });
    expect(steps.find(s => s.id === 'router')?.detail).toBe('Routed to AAPL');
    expect(steps.find(s => s.id === 'technical')?.detail).toBe('bullish at 70% confidence');

    events.push(
      trace('agent_error', 'Fundamental Auditor', { message: 'bad output' }),
      trace('handoff', 'system', { to: 'Risk Guard' }),
      trace('tool_call', 'Risk Guard', { tool: 'get_risk_metrics' }),
    );
    expect(states(deriveSteps(events, 'running'))).toMatchObject({ fundamental: 'warn', risk: 'active' });

    events.push(
      trace('handoff', 'system', { to: 'Lead Synthesizer' }),
      trace('agent_done', 'Lead Synthesizer'),
      trace('agent_start', 'Risk Critic'),
    );
    expect(states(deriveSteps(events, 'running'))).toMatchObject({ risk: 'done', synthesis: 'done', critic: 'active', policy: 'pending' });

    events.push(trace('critique', 'Risk Critic', { ok: false, issues: ['a', 'b'] }), trace('memo_draft', 'Lead Synthesizer'));
    const late = deriveSteps(events, 'running');
    expect(states(late)).toMatchObject({ critic: 'done', policy: 'active' });
    expect(late.find(s => s.id === 'critic')?.detail).toBe('2 issues raised, draft revised');

    events.push(trace('guardrail', 'Policy', { name: 'policy_cap' }), trace('final', 'Lead Synthesizer'));
    const done = deriveSteps(events, 'done');
    expect(Object.values(states(done)).filter(s => s === 'done').length).toBe(6);
    expect(done.find(s => s.id === 'policy')?.detail).toBe('1 adjustment applied');
  });

  it('marks a skipped critic, and stops active steps when the run fails', () => {
    const events = [trace('run_start', 'system', { ticker: 'X' }), trace('memo_draft', 'Lead Synthesizer')];
    expect(deriveSteps(events, 'running').find(s => s.id === 'critic')?.detail).toBe('Skipped to stay inside the token budget');
    const fallback = [trace('run_start', 'system', { ticker: 'X' }), trace('agent_error', 'Lead Synthesizer', { message: 'no model' })];
    expect(deriveSteps(fallback, 'done').find(s => s.id === 'critic')?.detail).toBe('Skipped: there was no draft to review');
    const failed = deriveSteps([trace('run_start', 'system', { ticker: 'X' }), trace('agent_start', 'Technical Analyst')], 'error');
    expect(states(failed)).toMatchObject({ router: 'done', technical: 'stopped' });
  });
});
