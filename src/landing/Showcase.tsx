import { motion } from 'motion/react';
import { useReducedMotion } from '@/lib/motion';

const POINTS = [
  { title: 'A diary of every decision', body: 'Including the trades it chose not to take, and the reason why.' },
  { title: 'A report card for every trade', body: 'It says how sure it is up front, then gets graded on what happened.' },
  { title: 'One big red button', body: 'Stop everything and close every position, instantly.' },
];

/** The real journal and report cards, beside three plain lines about what you are looking at. */
export function Showcase() {
  const reduce = useReducedMotion();
  return (
    <section id="screen" aria-labelledby="screen-title" className="px-4 py-24 sm:px-8 sm:py-32">
      <div className="mx-auto grid max-w-[1320px] items-center gap-14 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <motion.div
          initial={reduce ? false : { opacity: 0, x: -40 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{ type: 'spring', bounce: 0, duration: 1 }}
          className="lp-lit overflow-hidden rounded-[24px] bg-[hsl(222_30%_4%)] p-1.5 sm:p-2"
        >
          <img
            src="/landing/journal.jpg"
            width={1248}
            height={780}
            loading="lazy"
            decoding="async"
            alt="The journal, with a note for every decision, beside the report cards that grade each trade"
            className="block h-auto w-full rounded-[18px]"
          />
        </motion.div>

        <div>
          <h2 id="screen-title" className="lp-silver max-w-[13ch] pb-1 text-[clamp(2.2rem,4.4vw,3.5rem)] font-semibold leading-[1.04] tracking-[-0.035em]">
            Everything on one calm screen.
          </h2>
          <p className="mt-5 max-w-[40ch] text-body text-muted-foreground sm:text-[1.0625rem]">See what it holds, what it is thinking, and how its past calls turned out.</p>
          <ul className="mt-10 space-y-8">
            {POINTS.map(p => (
              <li key={p.title} className="relative pl-6">
                <span aria-hidden className="absolute left-0 top-1.5 h-6 w-[3px] rounded-full bg-primary shadow-[0_0_10px_hsl(var(--primary))]" />
                <h3 className="text-[1.375rem] font-medium tracking-[-0.02em]">{p.title}</h3>
                <p className="mt-1.5 max-w-[40ch] text-body text-muted-foreground">{p.body}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
