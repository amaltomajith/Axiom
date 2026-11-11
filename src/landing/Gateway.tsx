import { motion } from 'motion/react';
import { ArrowUpRight, BrainCircuit, CircleStop, ClipboardCheck, History, MonitorSmartphone, Wallet } from 'lucide-react';
import { useReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/utils';
import { BACKTEST_DOC } from './data';
import { MarkField } from './MarkField';
import { Chip } from './ui';

const LEFT = [
  { icon: MonitorSmartphone, title: 'A calm cockpit', body: 'Your balance, its plans and the stop button, together on one screen.', href: '#screen', lit: true },
  { icon: Wallet, title: 'A practice account', body: 'It connects to a free paper account, so every trade uses pretend money.', href: '#steps' },
  { icon: History, title: 'A time machine', body: 'Replay years of past markets and see how it would have done.', href: BACKTEST_DOC },
];
const RIGHT = [
  { icon: BrainCircuit, title: 'A free brain', body: 'It thinks with free AI, and falls back to simple rules when none is around.', href: '#faq' },
  { icon: ClipboardCheck, title: 'Report cards', body: 'Every trade gets a grade, and so does every trade it chose to skip.', href: '#honest' },
  { icon: CircleStop, title: 'Your stop button', body: 'One press cancels every order and closes every position.', href: '#faq' },
];

type Card = (typeof LEFT)[number];

function GateCard({ card, side, i }: { card: Card; side: 'left' | 'right'; i: number }) {
  const reduce = useReducedMotion();
  const Icon = card.icon;
  const ext = card.href.startsWith('http');
  return (
    <motion.a
      href={card.href}
      {...(ext ? { target: '_blank', rel: 'noreferrer' } : {})}
      initial={reduce ? { opacity: 0 } : { opacity: 0, x: side === 'left' ? -28 : 28 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true, amount: 0.5 }}
      transition={reduce ? { duration: 0.2 } : { type: 'spring', bounce: 0, duration: 0.7, delay: i * 0.08 }}
      className={cn(
        'group relative flex gap-4 rounded-[20px] p-5 outline-none transition-[transform,box-shadow,border-color] duration-300 focus-visible:ring-2 focus-visible:ring-ring sm:p-6',
        card.lit ? 'lp-card-lit' : 'lp-card',
        side === 'right' && 'lg:flex-row-reverse lg:text-right',
      )}
    >
      <span className="lp-icon flex h-11 w-11 shrink-0 items-center justify-center rounded-xl">
        <Icon aria-hidden className="h-5 w-5 text-primary" strokeWidth={1.75} />
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn('flex items-center gap-1.5 text-[1.125rem] font-medium tracking-[-0.015em] text-foreground', side === 'right' && 'lg:justify-end')}>
          {card.title}
          <ArrowUpRight
            aria-hidden
            className="h-4 w-4 text-foreground/40 transition-[color,transform] duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-primary"
          />
        </span>
        <span className="mt-1.5 block text-body text-muted-foreground">{card.body}</span>
      </span>
    </motion.a>
  );
}

/** Six things that come with it, three either side of the Axiom mark drawn in light. */
export function Gateway() {
  return (
    <section id="gateway" aria-labelledby="gateway-title" className="relative isolate overflow-hidden px-4 py-24 sm:px-8 sm:py-32">
      <div aria-hidden className="absolute left-1/2 top-[58%] -z-10 h-[560px] w-[760px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/[0.13] blur-[140px]" />
      <div className="mx-auto max-w-[1320px]">
        <div className="mx-auto flex max-w-[720px] flex-col items-center text-center">
          <Chip>All in one place</Chip>
          <h2 id="gateway-title" className="lp-silver mt-6 pb-1 text-[clamp(2.2rem,4.6vw,3.75rem)] font-semibold leading-[1.04] tracking-[-0.035em]">
            Everything it needs to look after you.
          </h2>
          <p className="mt-5 max-w-[46ch] text-body text-muted-foreground sm:text-[1.0625rem]">No add-ons and no upgrades. Everything here comes with it from the very first day.</p>
        </div>

        <div className="mt-14 grid items-center gap-4 lg:mt-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-8">
          <div className="space-y-4 lg:order-1">
            {LEFT.map((c, i) => (
              <GateCard key={c.title} card={c} side="left" i={i} />
            ))}
          </div>
          <div className="relative order-first mx-auto aspect-square w-full max-w-[460px] lg:order-2 lg:max-w-none">
            <div aria-hidden className="lp-floor absolute inset-x-[10%] top-[66%] h-[14%]" />
            <MarkField />
          </div>
          <div className="space-y-4 lg:order-3">
            {RIGHT.map((c, i) => (
              <GateCard key={c.title} card={c} side="right" i={i} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
