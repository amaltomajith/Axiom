import { motion } from 'motion/react';
import { useReducedMotion } from '@/lib/motion';
import { BACKTEST_DOC } from './data';
import { Chip } from './ui';

/** A softly breathing orb over the one part of the story most products leave out: how it actually did. */
export function Honest() {
  const reduce = useReducedMotion();
  return (
    <section id="honest" aria-labelledby="honest-title" className="relative isolate overflow-hidden px-4 pb-24 pt-32 sm:px-8 sm:pb-32 sm:pt-40">
      <div aria-hidden className="absolute left-1/2 top-24 -z-10 h-[620px] w-[620px] -translate-x-1/2 rounded-full bg-primary/20 blur-[150px]" />
      <div className="mx-auto flex max-w-[760px] flex-col items-center text-center">
        <motion.div
          aria-hidden
          animate={reduce ? undefined : { scale: [1, 1.04, 1] }}
          transition={{ duration: 7, repeat: Infinity, ease: 'easeInOut' }}
          className="relative h-44 w-44 rounded-full border border-white/20 bg-[radial-gradient(circle_at_50%_62%,hsl(199_92%_62%/0.55),hsl(205_90%_42%/0.35)_48%,hsl(212_85%_30%/0.25)_72%,hsl(199_92%_70%/0.35)_100%)] shadow-[0_0_90px_hsl(var(--primary)/0.5),inset_0_0_36px_hsl(199_95%_75%/0.45)] sm:h-52 sm:w-52"
        >
          <span className="absolute left-[16%] top-[22%] h-[30%] w-[66%] -rotate-12 rounded-[50%] bg-gradient-to-b from-white/90 via-sky-100/40 to-transparent blur-[5px]" />
          <span className="absolute inset-x-[22%] bottom-[10%] h-[22%] rounded-full bg-primary/60 blur-xl" />
        </motion.div>
        <Chip className="mt-12">Honest by design</Chip>
        <h2 id="honest-title" className="lp-silver mt-6 pb-1 text-[clamp(2.2rem,4.4vw,3.5rem)] font-semibold leading-[1.05] tracking-[-0.035em]">
          It keeps itself honest.
        </h2>
        <p className="mt-5 max-w-[52ch] text-body text-muted-foreground sm:text-[1.0625rem]">
          Before each trade, Axiom says how confident it is. Afterwards, it checks whether it was right. When it has been too sure of itself, it stays on a shorter leash.
        </p>
        <div className="lp-panel mt-12 w-full rounded-[24px] p-6 text-left sm:p-8">
          <p className="text-[1.25rem] font-medium leading-snug tracking-[-0.015em] text-foreground">
            In years of practice runs, it lost far less than simply holding when markets fell. It also made far less when they rose.
          </p>
          <p className="mt-3 text-body text-muted-foreground">We would rather show you that than promise you anything. It is careful by nature, which is exactly why it starts with paper money.</p>
          <a href={BACKTEST_DOC} target="_blank" rel="noreferrer" className="mt-5 inline-flex text-small font-medium text-primary underline-offset-4 hover:underline">
            Read the full practice report
          </a>
        </div>
      </div>
    </section>
  );
}
