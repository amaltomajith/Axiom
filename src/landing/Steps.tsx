import { motion, useScroll, useTransform } from 'motion/react';
import { useRef } from 'react';
import { useReducedMotion } from '@/lib/motion';
import { Chip, GhostLink, StartLink } from './ui';

const STEPS = [
  { title: 'Connect a practice account', body: 'Link a free paper account. It works just like the real thing, with pretend money.' },
  { title: 'Choose how much say it gets', body: 'Let it only watch, ask you before every trade, or act on its own once it has earned that.' },
  { title: 'Read along', body: 'Follow each decision in the journal, written so anyone can understand it.' },
];

/** Three steps on a line that fills with light as you read down it (scroll-linked, no listeners). */
export function Steps() {
  const ref = useRef<HTMLOListElement>(null);
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start 75%', 'end 45%'] });
  const fill = useTransform(scrollYProgress, [0, 1], ['0%', '100%']);

  return (
    <section id="steps" aria-labelledby="steps-title" className="relative isolate px-4 py-24 sm:px-8 sm:py-32">
      <div aria-hidden className="absolute left-1/2 top-1/2 -z-10 h-[520px] w-[820px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/10 blur-[140px]" />
      <div className="mx-auto grid max-w-[1180px] items-center gap-14 lg:grid-cols-2">
        <div>
          <Chip>Getting started</Chip>
          <h2 id="steps-title" className="lp-silver mt-6 max-w-[14ch] pb-1 text-[clamp(2.2rem,4.4vw,3.5rem)] font-semibold leading-[1.04] tracking-[-0.035em]">
            Ready in three easy steps.
          </h2>
          <p className="mt-5 max-w-[40ch] text-body text-muted-foreground sm:text-[1.0625rem]">Nothing to deposit and nothing to install. A free practice account and a few minutes is all it takes.</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <StartLink />
            <GhostLink href="#faq">Questions</GhostLink>
          </div>
        </div>

        <ol ref={ref} className="relative space-y-12 pl-14">
          <span aria-hidden className="absolute bottom-3 left-[15px] top-3 w-[3px] rounded-full bg-white/[0.07]" />
          <motion.span
            aria-hidden
            style={{ height: reduce ? '100%' : fill }}
            className="absolute left-[15px] top-3 w-[3px] rounded-full bg-gradient-to-b from-primary/30 to-primary shadow-[0_0_14px_hsl(var(--primary)/0.7)]"
          />
          {STEPS.map((s, i) => (
            <li key={s.title} className="relative">
              <span
                aria-hidden
                className="absolute -left-14 top-0 flex h-8 w-8 items-center justify-center rounded-full bg-foreground text-small font-semibold text-background shadow-[0_0_0_5px_hsl(var(--background))]"
              >
                {i + 1}
              </span>
              <h3 className="text-[1.5rem] font-medium tracking-[-0.02em]">{s.title}</h3>
              <p className="mt-2 max-w-[42ch] text-body text-muted-foreground">{s.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
