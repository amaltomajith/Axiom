import { ArrowUpRight } from 'lucide-react';
import { Cell, List, ListRow } from '@/components/kit/List';
import { frac, ratingLabel } from '@/lib/format';
import { cn } from '@/lib/utils';
import { EVAL_REPORT, snapshot } from './data';

const WHAT: Record<string, string> = {
  random_walk: 'Pure noise: there is no edge to find',
  conflict: 'Analysts disagree about direction',
  thin_data: 'Far too little data to judge',
  earned_edge: 'A genuine edge (the positive control)',
  'inj_direct+bypass': 'A planted instruction, filter bypassed',
};

const ratio = (s: string) => {
  const [a, b] = s.split('/').map(Number);
  return b ? a / b : null;
};

function Figure({ value, label }: { value: string; label: string }) {
  return (
    <div className="px-6 py-5">
      <p className="tnum text-h1">{value.replace('/', ' of ')}</p>
      <p className="mt-1 text-small text-muted-foreground">{label}</p>
    </div>
  );
}

export function Evals() {
  const e = snapshot.evals;
  return (
    <section className="mx-auto max-w-[1200px] px-4 pb-24 sm:px-6 sm:pb-32">
      <div className="max-w-[60ch]">
        <h2 className="text-h1">Measured, not promised</h2>
        <p className="mt-3 text-body text-muted-foreground">The suite replays recorded model output, so re-running it costs nothing and gives the same answer every time.</p>
      </div>

      <div className="surface mt-12 overflow-hidden">
        <div className="grid grid-cols-2 divide-border md:grid-cols-4 md:divide-x">
          <Figure value={e.passed} label="scenarios passed" />
          <Figure value={e.injection} label="injection runs ended normally" />
          <Figure value={e.judge} label="memo claims supported, by an LLM judge" />
          <Figure value={e.control_obeyed} label="obeyed an attack with no defences" />
        </div>
        <List cols="grid-cols-[1fr_5.5rem] md:grid-cols-[13rem_1fr_6rem]" headers={[{ label: 'Scenario' }, { label: 'What it checks', hideBelow: 'md' }, { label: 'Final call', align: 'right' }]} className="border-t border-border">
          {e.cases.map(c => (
            <ListRow key={c.name}>
              <Cell className="font-mono text-caption">{c.name}</Cell>
              <Cell hideBelow="md" className="text-muted-foreground">
                {WHAT[c.name] ?? ''}
              </Cell>
              <Cell align="right" className={cn('font-medium', c.name === 'earned_edge' && 'text-success')}>
                {ratingLabel(c.rating.split(' to ').pop() ?? '')}
              </Cell>
            </ListRow>
          ))}
        </List>
        <p className="border-t border-border px-6 py-4 text-caption text-muted-foreground">
          The judge is the same family of small free models as the agents, so treat it as a noisy signal.{' '}
          {ratio(e.judge) != null && `Supported claims: ${frac(ratio(e.judge), 0)}. `}
          <a href={EVAL_REPORT} className="inline-flex items-center gap-0.5 font-medium text-primary hover:underline" target="_blank" rel="noreferrer">
            Read the full report <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
        </p>
      </div>
    </section>
  );
}
