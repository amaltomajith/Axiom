import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Chip } from './ui';

const MODES = [
  {
    name: 'Watch only',
    body: 'It follows the market and makes its picks on paper, but touches nothing. A good way to get to know it.',
    points: ['Places no trades at all', 'Shares every idea in the journal', 'Builds a record you can read'],
  },
  {
    name: 'Ask me first',
    badge: 'Recommended start',
    body: 'It brings you each idea with a short reason. You approve it or skip it. Nothing happens without you.',
    points: ['You approve every trade', 'A safety exit on every position', 'Takes the day off after a rough patch'],
  },
  {
    name: 'On its own',
    body: 'Once its calls have proven reliable, it can act without asking, still inside every limit you set.',
    points: ['Earned with a good track record', 'Same limits and safety exits', 'Goes back to asking after a bad day'],
  },
];

/** The three levels of freedom as three cards; the middle one is lit because that is where it starts. */
export function Modes() {
  return (
    <section id="modes" aria-labelledby="modes-title" className="px-4 py-24 sm:px-8 sm:py-32">
      <div className="mx-auto max-w-[1180px]">
        <div className="mx-auto flex max-w-[720px] flex-col items-center text-center">
          <Chip>Three modes</Chip>
          <h2 id="modes-title" className="lp-silver mt-6 pb-1 text-[clamp(2.2rem,4.4vw,3.5rem)] font-semibold leading-[1.05] tracking-[-0.035em]">
            Freedom it has to earn.
          </h2>
          <p className="mt-5 max-w-[50ch] text-body text-muted-foreground sm:text-[1.0625rem]">
            Axiom starts out cautious. It only gets more independence after it has shown, trade after trade, that its judgement holds up.
          </p>
        </div>

        <ul className="mt-16 grid gap-4 md:grid-cols-3">
          {MODES.map(m => (
            <li key={m.name} className={cn('lp-panel flex flex-col rounded-[24px] p-7', m.badge && 'lp-lit md:-translate-y-3')}>
              <div className="flex flex-col-reverse items-start gap-3 sm:flex-row sm:justify-between">
                <h3 className="text-[1.75rem] font-medium tracking-[-0.025em]">{m.name}</h3>
                {m.badge && <span className="lp-chip shrink-0 sm:mt-1 rounded-full px-3 py-1 text-caption font-medium">{m.badge}</span>}
              </div>
              <p className="mt-3 text-body text-muted-foreground">{m.body}</p>
              <ul className="mt-7 space-y-3 border-t border-white/[0.07] pt-6">
                {m.points.map(p => (
                  <li key={p} className="flex items-start gap-3 text-small text-foreground/85">
                    <Check aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-primary" strokeWidth={2.25} />
                    {p}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
