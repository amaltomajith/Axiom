import { Plus } from 'lucide-react';
import { FAQ } from './data';
import { Chip } from './ui';

/** Plain questions with plain answers. Native disclosure elements, so it works with a keyboard and without script. */
export function Faq() {
  return (
    <section id="faq" aria-labelledby="faq-title" className="px-4 py-24 sm:px-8 sm:py-32">
      <div className="mx-auto grid max-w-[1180px] gap-12 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <div>
          <Chip>Questions</Chip>
          <h2 id="faq-title" className="lp-silver mt-6 max-w-[12ch] pb-1 text-[clamp(2.2rem,4.4vw,3.5rem)] font-semibold leading-[1.04] tracking-[-0.035em]">
            Good questions, straight answers.
          </h2>
        </div>
        <div className="divide-y divide-white/[0.08] border-y border-white/[0.08]">
          {FAQ.map(({ q, a }) => (
            <details key={q} className="group">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-6 text-[1.1875rem] font-medium tracking-[-0.015em] outline-none focus-visible:text-primary [&::-webkit-details-marker]:hidden">
                {q}
                <span className="lp-ghost flex h-9 w-9 shrink-0 items-center justify-center rounded-full">
                  <Plus aria-hidden className="h-4 w-4 transition-transform duration-300 group-open:rotate-45" />
                </span>
              </summary>
              <p className="max-w-[60ch] pb-6 text-body text-muted-foreground">{a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
