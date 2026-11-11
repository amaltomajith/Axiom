import { motion } from 'motion/react';
import { spring, useReducedMotion } from '@/lib/motion';
import { Globe } from './Globe';
import { Chip, GhostLink, StartLink } from './ui';

/**
 * Centred, because the promise is the design here: a chip, one headline, one sentence, two actions.
 * Below it the globe rises behind the real cockpit, framed with a lit top edge.
 */
export function Hero() {
  const reduce = useReducedMotion();
  const item = (delay: number) =>
    reduce
      ? { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { duration: 0.2, delay } }
      : { initial: { opacity: 0, y: 18 }, animate: { opacity: 1, y: 0 }, transition: { ...spring.default, delay } };

  return (
    <section id="top" className="relative isolate overflow-hidden pt-32 sm:pt-40">
      <div aria-hidden className="absolute inset-x-0 top-0 -z-10 h-[720px] bg-[radial-gradient(60%_55%_at_50%_0%,hsl(var(--primary)/0.22),transparent_70%)]" />

      <div className="mx-auto flex max-w-[880px] flex-col items-center px-4 text-center">
        <motion.div {...item(0)}>
          <Chip>Practice money only</Chip>
        </motion.div>
        <motion.h1 {...item(0.06)} className="lp-silver mt-6 pb-2 text-[clamp(2.6rem,7vw,5rem)] font-semibold leading-[1.02] tracking-[-0.04em]">
          A trading partner that thinks first.
        </motion.h1>
        <motion.p {...item(0.12)} className="mt-5 max-w-[34rem] text-[1.0625rem] leading-relaxed text-muted-foreground sm:text-lg">
          Axiom watches the markets for you, explains every move in plain words, and never risks more than you allow.
        </motion.p>
        <motion.div {...item(0.18)} className="mt-9 flex flex-wrap items-center justify-center gap-3">
          <StartLink />
          <GhostLink href="#how">See how it works</GhostLink>
        </motion.div>
      </div>

      <div className="relative mt-16 sm:mt-20">
        <div aria-hidden className="absolute left-1/2 top-0 aspect-square w-[min(1040px,140vw)] -translate-x-1/2">
          <Globe />
        </div>
        <motion.div
          initial={reduce ? { opacity: 0 } : { opacity: 0, y: 60 }}
          animate={{ opacity: 1, y: 0 }}
          transition={reduce ? { duration: 0.3 } : { type: 'spring', bounce: 0, duration: 1.1, delay: 0.3 }}
          className="relative mx-auto max-w-[1200px] px-3 pt-[min(330px,46vw)] sm:px-8"
        >
          <div className="lp-lit overflow-hidden rounded-[22px] bg-[hsl(222_30%_4%)] p-1.5 sm:rounded-[28px] sm:p-2.5">
            <img
              src="/landing/cockpit.jpg"
              width={1600}
              height={900}
              alt="The Axiom cockpit: practice balance, a big red stop button, how much freedom it has, today's limits, and its results against simply holding"
              className="block h-auto w-full rounded-[16px] sm:rounded-[20px]"
            />
          </div>
          <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-background to-transparent" />
        </motion.div>
      </div>
    </section>
  );
}
