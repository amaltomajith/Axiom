import type { ReactNode } from 'react';
import { motion } from 'motion/react';
import { useReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/utils';
import { Chip } from './ui';

/** A tile: a picture of the behaviour on top, two lines about it below, blue light pooling in one corner. */
function Tile({ title, body, children, glow, className }: { title: string; body: string; children: ReactNode; glow: 'left' | 'right'; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <motion.article
      aria-label={title}
      initial={reduce ? false : { opacity: 0, y: 32 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ type: 'spring', bounce: 0, duration: 0.8 }}
      className={cn('lp-panel relative isolate flex min-h-[400px] flex-col overflow-hidden rounded-[24px] p-6 sm:p-8', className)}
    >
      <div aria-hidden className={cn('absolute -bottom-48 -z-10 h-[420px] w-[420px] rounded-full bg-primary/25 blur-[110px]', glow === 'left' ? '-left-40' : '-right-36')} />
      <div aria-hidden className="flex flex-1 items-center justify-center py-6">
        {children}
      </div>
      <h3 className="text-[1.5rem] font-medium tracking-[-0.02em]">{title}</h3>
      <p className="mt-2 max-w-[40ch] text-body text-muted-foreground">{body}</p>
    </motion.article>
  );
}

function Note() {
  return (
    <div className="w-full max-w-[360px] rounded-2xl border border-white/10 bg-[hsl(222_28%_8%/0.85)] p-5 shadow-2xl backdrop-blur">
      <div className="flex items-center justify-between">
        <span className="rounded-full bg-primary/15 px-2.5 py-1 text-caption font-medium text-primary">Bought</span>
        <span className="text-caption text-muted-foreground">Today, 9:00</span>
      </div>
      <p className="mt-4 text-small leading-relaxed text-foreground/90">
        Bought a little Ethereum. The trend turned up overnight and nothing else looked better. If it slips back to $2,244, I will step out.
      </p>
      <div className="mt-4 h-px bg-white/[0.07]" />
      <p className="mt-3 text-caption text-muted-foreground">How sure: a bit better than a coin toss</p>
    </div>
  );
}

function Wait() {
  return (
    <div className="relative w-full max-w-[520px]">
      <svg viewBox="0 0 520 170" className="w-full">
        <defs>
          <linearGradient id="wait-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="hsl(199 92% 58%)" stopOpacity="0.25" />
            <stop offset="1" stopColor="hsl(199 92% 58%)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d="M0 96 C40 70 70 120 110 100 S170 60 210 92 270 128 310 98 370 70 410 100 470 118 520 92 L520 170 L0 170Z" fill="url(#wait-fill)" />
        <path d="M0 96 C40 70 70 120 110 100 S170 60 210 92 270 128 310 98 370 70 410 100 470 118 520 92" fill="none" stroke="hsl(199 92% 62%)" strokeWidth="2.5" />
      </svg>
      <div className="absolute left-1/2 top-2 -translate-x-1/2 whitespace-nowrap rounded-full border border-white/10 bg-[hsl(222_28%_8%/0.9)] px-4 py-2 text-small text-foreground/90 shadow-lg backdrop-blur">
        Nothing looks right. Waiting.
      </div>
    </div>
  );
}

function Exit() {
  return (
    <div className="relative w-full max-w-[540px]">
      <svg viewBox="0 0 540 180" className="w-full overflow-visible">
        <line x1="0" y1="150" x2="540" y2="150" stroke="hsl(0 0% 100% / 0.45)" strokeWidth="1.5" strokeDasharray="6 7" />
        <path d="M0 120 C50 110 80 128 120 112 S190 92 230 104 300 70 350 60 430 40 540 22" fill="none" stroke="hsl(199 92% 62%)" strokeWidth="2.5" />
        <circle cx="120" cy="112" r="6" fill="hsl(199 92% 62%)" />
        <circle cx="120" cy="112" r="13" fill="none" stroke="hsl(199 92% 62% / 0.4)" strokeWidth="2" />
      </svg>
      <span className="absolute left-[22%] top-[34%] -translate-x-1/2 whitespace-nowrap text-caption text-foreground">Bought here</span>
      <p className="mt-2 text-right text-caption text-muted-foreground">Safety exit, set before buying</p>
    </div>
  );
}

function Approve() {
  return (
    <div className="w-full max-w-[340px] rounded-2xl border border-white/10 bg-[hsl(222_28%_8%/0.85)] p-5 shadow-2xl backdrop-blur">
      <p className="text-caption text-muted-foreground">New idea</p>
      <p className="mt-1 text-[1.125rem] font-medium">Buy a little Bitcoin?</p>
      <p className="mt-2 text-small text-muted-foreground">Small position, safety exit already set.</p>
      <div className="mt-5 grid grid-cols-2 gap-2">
        <span className="lp-cta flex h-10 items-center justify-center rounded-full text-small font-medium">Approve</span>
        <span className="lp-ghost flex h-10 items-center justify-center rounded-full text-small font-medium">Skip</span>
      </div>
    </div>
  );
}

export function Features() {
  return (
    <section id="how" aria-labelledby="how-title" className="px-4 py-24 sm:px-8 sm:py-32">
      <div className="mx-auto max-w-[1240px]">
        <div className="mx-auto flex max-w-[760px] flex-col items-center text-center">
          <Chip>How it works</Chip>
          <h2 id="how-title" className="lp-silver mt-6 pb-1 text-[clamp(2.2rem,4.4vw,3.5rem)] font-semibold leading-[1.05] tracking-[-0.035em]">
            It does the watching. You do the deciding.
          </h2>
          <p className="mt-5 max-w-[52ch] text-body text-muted-foreground sm:text-[1.0625rem]">
            Markets move around the clock. Axiom keeps an eye on them so you do not have to, and checks in when something is worth your time.
          </p>
        </div>

        <div className="mt-16 grid gap-4 lg:grid-cols-12">
          <Tile className="lg:col-span-5" glow="left" title="It tells you why" body="Every trade comes with a short note: what it saw, why it acted, and where it will step out.">
            <Note />
          </Tile>
          <Tile className="lg:col-span-7" glow="right" title="It knows when to wait" body="If nothing looks right, it does nothing at all. Sitting still is a decision too.">
            <Wait />
          </Tile>
          <Tile className="lg:col-span-7" glow="left" title="It always has a way out" body="Before it buys anything, it decides where it will sell if things go wrong. No exceptions.">
            <Exit />
          </Tile>
          <Tile className="lg:col-span-5" glow="right" title="You stay in charge" body="New ideas wait for your yes. Skip anything you do not like, or stop it all with one press.">
            <Approve />
          </Tile>
        </div>
      </div>
    </section>
  );
}
