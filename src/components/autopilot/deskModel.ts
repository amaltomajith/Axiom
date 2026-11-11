import { ratingLabel } from '@/lib/format';
import type { DeskEvent, DeskReview, JournalEntry, RuleCheck, TraderStatus } from '@/lib/types';

/** Pure helpers behind the cockpit's Live run card and regime tile: trace and facts in, display rows out. */

export type StepState = 'waiting' | 'working' | 'done' | 'failed';
type Tone = 'default' | 'success' | 'warning' | 'destructive' | 'neutral';
export interface Step {
  name: string;
  job: string;
  state: StepState;
  result?: string;
  badge?: { text: string; tone: Tone };
}

const STANCE: Record<string, { text: string; tone: Tone }> = {
  bullish: { text: 'Bullish', tone: 'success' },
  bearish: { text: 'Bearish', tone: 'destructive' },
  neutral: { text: 'Neutral', tone: 'neutral' },
  insufficient_data: { text: 'No view', tone: 'warning' },
};

const str = (v: unknown): string => (typeof v === 'string' ? v : '');

/** Turn one run's trace into the five steps the desk goes through. */
export function deskSteps(events: DeskEvent[], review: DeskReview | null, running: boolean): Step[] {
  const of = (agent: string, kind: string) => [...events].reverse().find(e => e.agent === agent && e.kind === kind);
  const touched = (agent: string) => events.some(e => e.agent === agent);
  const analyst = (name: string, job: string): Step => {
    const finding = of(name, 'finding');
    const failed = of(name, 'agent_error');
    const tools = events.filter(e => e.agent === name && e.kind === 'tool_call').length;
    if (finding) return { name, job, state: 'done', result: str(finding.data.summary), badge: STANCE[str(finding.data.stance)] ?? STANCE.neutral };
    if (failed) return { name, job, state: 'failed', result: 'Could not finish, so it counts as no view.', badge: STANCE.insufficient_data };
    if (touched(name)) return { name, job, state: running ? 'working' : 'failed', result: tools ? `Called ${tools} tool${tools === 1 ? '' : 's'} so far.` : undefined };
    return { name, job, state: running ? 'waiting' : 'failed' };
  };

  const draft = of('Lead Synthesizer', 'final') ?? of('Lead Synthesizer', 'memo_draft');
  const synth: Step = { name: 'Lead Synthesizer', job: 'Weighs both views and writes the plan', state: running ? 'waiting' : 'failed' };
  if (review?.rating) {
    synth.state = 'done';
    synth.result = review.thesis ?? undefined;
    synth.badge = { text: `${ratingLabel(review.rating)}, conviction ${review.conviction?.toFixed(2) ?? 'n/a'}`, tone: 'default' };
  } else if (draft) {
    synth.state = 'done';
    synth.badge = { text: ratingLabel(str(draft.data.rating)), tone: 'default' };
  } else if (touched('Lead Synthesizer')) synth.state = running ? 'working' : 'failed';

  const critique = of('Risk Critic', 'critique');
  const critic: Step = { name: 'Risk Critic', job: 'Argues against the plan and can ask for less', state: running ? 'waiting' : 'failed' };
  if (critique) {
    const issues = (critique.data.issues as string[] | undefined) ?? [];
    critic.state = 'done';
    critic.result = critique.data.ok ? 'Found nothing to object to.' : issues[0];
    critic.badge = critique.data.ok ? { text: 'No objection', tone: 'success' } : { text: 'Objected', tone: 'warning' };
  } else if (touched('Risk Critic')) critic.state = running ? 'working' : 'failed';
  else if (!running && review?.rating) {
    critic.state = 'done';
    critic.result = 'Did not run on this plan.';
  }

  return [analyst('Technical Analyst', 'Reads the chart, the trend and the backtest'), analyst('Fundamental Auditor', 'Reads the news, filings and peers'), synth, critic];
}

const GROUPS: { label: (limit: string) => string; rules: string[] }[] = [
  { label: () => 'Paper account only', rules: ['R1'] },
  { label: () => 'Stop-loss attached', rules: ['R5'] },
  { label: () => 'Size within caps', rules: ['R6', 'R7', 'R8', 'R9'] },
  { label: limit => `Day loss under ${limit}`, rules: ['R3'] },
  { label: () => 'Kill switch is off', rules: ['R0'] },
];
const ALSO = ['R2', 'R4', 'R10', 'R11', 'R12'];

export interface GateRow {
  label: string;
  ok: boolean | null; // null: this check was not reached
  detail: string;
}

/** The kernel's thirteen rules, shown as the six checks every order has to pass. */
export function gateRows(e: JournalEntry, limit: string): { rows: GateRow[]; also: RuleCheck[] } {
  const checks = (e.facts.checks as RuleCheck[] | undefined) ?? [];
  const pick = (rules: string[]) => checks.filter(c => rules.includes(c.rule));
  const rows: GateRow[] = GROUPS.map(g => {
    const cs = pick(g.rules);
    const bad = cs.find(c => !c.ok);
    return { label: g.label(limit), ok: cs.length ? !bad : null, detail: (bad ?? cs[0])?.detail ?? 'Not reached: an earlier check stopped it.' };
  });
  const rewrite = e.facts.rewrite as string | undefined;
  rows.push({
    label: 'Journal numbers verified',
    ok: true,
    detail:
      rewrite === 'accepted'
        ? 'The plain-language rewrite kept every number, so it was accepted.'
        : rewrite === 'discarded'
          ? 'A rewrite changed a number, so it was thrown away and the template was kept.'
          : 'Written from the recorded facts by a fixed template.',
  });
  return { rows, also: pick(ALSO) };
}

const TREND: Record<string, string> = { uptrend: 'Trending up', downtrend: 'Trending down', sideways: 'Sideways' };

/** The market regime the strategies are being judged in: one word when the symbols agree, a count when not. */
export function regimeSummary(regimes: TraderStatus['regimes']): { headline: string; detail: string } | null {
  const rows = Object.entries(regimes ?? {});
  if (!rows.length) return null;
  const name = (t?: string) => TREND[t ?? ''] ?? 'Unclear';
  const counts = new Map<string, number>();
  for (const [, r] of rows) counts.set(name(r.trend), (counts.get(name(r.trend)) ?? 0) + 1);
  const [top, n] = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
  const detail = rows.map(([sym, r]) => `${sym}: ${name(r.trend).toLowerCase()}, ${r.volatility ?? 'unknown'} volatility`).join('. ');
  return { headline: counts.size === 1 ? top : `${top} (${n} of ${rows.length})`, detail };
}
