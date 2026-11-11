import { motion } from 'motion/react';
import { CircleStop, Hand, MessageSquareText, Moon, Scale } from 'lucide-react';
import { useReducedMotion } from '@/lib/motion';
import { Globe } from './Globe';
import { Chip, StartLink } from './ui';

const TRAITS = [
  { icon: Hand, title: 'Asks first', note: 'before it places a trade' },
  { icon: MessageSquareText, title: 'Explains itself', note: 'in plain, everyday words' },
  { icon: Scale, title: 'Bets small', note: 'never more than you allow' },
  { icon: Moon, title: 'Rests on bad days', note: 'and tries again tomorrow' },
  { icon: CircleStop, title: 'Stops on command', note: 'one press, and it is flat' },
];

/** Five plain promises beside a turning globe: how it behaves, rather than how much it made. */
export function Trust() {
  const reduce = useReducedMotion();
  return (
    <section id="safety" aria-labelledby="trust-title" className="relative overflow-hidden px-4 py-24 sm:px-8 sm:py-32">
      <div className="mx-auto grid max-w-[1320px] items-center gap-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-6">
        <div>
          <Chip>Peace of mind</Chip>
          <h2 id="trust-title" className="lp-silver mt-6 max-w-[11ch] pb-1 text-[clamp(2.2rem,3.6vw,3rem)] font-semibold leading-[1.06] tracking-[-0.035em]">
            Steady when markets are not.
          </h2>
          <p className="mt-5 max-w-[34ch] text-body text-muted-foreground">Most trading bots chase excitement. Axiom is designed to be the steady one in the room.</p>
          <StartLink className="mt-8" />
        </div>

        <div className="relative mx-auto aspect-square w-full max-w-[560px] lg:-mx-[12%] lg:w-[124%] lg:max-w-none">
          <Globe tilt={0.3} speed={0.04} radius={0.44} facing={-20} />
        </div>

        <ul className="relative z-10 divide-y divide-white/[0.07]">
          {TRAITS.map(({ icon: Icon, title, note }, i) => (
            <motion.li
              key={title}
              initial={reduce ? false : { opacity: 0, x: 24 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, amount: 0.6 }}
              transition={{ type: 'spring', bounce: 0, duration: 0.6, delay: i * 0.06 }}
              className="flex items-center gap-4 py-5"
            >
              <Icon aria-hidden className="h-5 w-5 shrink-0 text-foreground/70" strokeWidth={1.75} />
              <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-0.5">
                <span className="text-[1.375rem] font-medium tracking-[-0.02em] text-foreground">{title}</span>
                <span className="text-body text-primary">{note}</span>
              </div>
            </motion.li>
          ))}
        </ul>
      </div>
    </section>
  );
}
