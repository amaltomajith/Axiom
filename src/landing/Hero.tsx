import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { ArrowRight } from 'lucide-react';
import { ClaimList } from '@/components/MemoPanel';
import { PriceChart } from '@/components/PriceChart';
import { Button } from '@/components/ui/button';
import { frac, ratingLabel, ratingTone, shortDate, TONE_TEXT } from '@/lib/format';
import { spring, useReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/utils';
import { snapshot } from './data';

/** The preview is the real chart component and the real memo, fed by a recorded run. Chips open real evidence. */
function Preview() {
  const { memo, evidence } = snapshot.result;
  const reduce = useReducedMotion();
  const tone = ratingTone(memo.rating);
  return (
    <div className="surface overflow-hidden shadow-md">
      <div className="flex items-end justify-between gap-4 px-5 pb-1 pt-5 sm:px-6">
        <div>
          <p className="font-mono text-small text-muted-foreground">{snapshot.ticker}</p>
          <p className="tnum text-h2">${snapshot.bars[snapshot.bars.length - 1].close.toFixed(2)}</p>
        </div>
        <p className="text-caption text-muted-foreground">14-day range, zero drift</p>
      </div>
      <div className="px-2 sm:px-3">
        <PriceChart bars={snapshot.bars} cone={snapshot.cone} height={230} animate={!reduce} />
      </div>
      <div className="border-t border-border px-5 py-4 sm:px-6">
        <div className="flex items-baseline justify-between gap-4">
          <p className={cn('text-h3', TONE_TEXT[tone])}>{ratingLabel(memo.rating)}</p>
          <p className="tnum text-caption text-muted-foreground">{frac(memo.conviction, 0)} conviction</p>
        </div>
        <div className="mt-3">
          <ClaimList claims={[memo.bull_case[0], memo.bear_case[0]].filter(Boolean)} result={{ evidence }} />
        </div>
      </div>
    </div>
  );
}

/** Hero: headline, one sentence, two actions, one real preview. Nothing else competes with them. */
export function Hero() {
  const reduce = useReducedMotion();
  const item = (delay: number) =>
    reduce
      ? { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { duration: 0.2, delay } }
      : { initial: { opacity: 0, y: 16 }, animate: { opacity: 1, y: 0 }, transition: { ...spring.default, delay } };

  return (
    <section className="mx-auto grid min-h-[min(calc(100dvh-4rem),44rem)] max-w-[1200px] items-center gap-12 px-4 pb-16 pt-12 sm:px-6 lg:grid-cols-12 lg:gap-10">
      <div className="lg:col-span-5">
        <motion.h1 {...item(0)} className="text-display">
          Research that shows its work.
        </motion.h1>
        <motion.p {...item(0.08)} className="mt-5 max-w-[34ch] text-h3 font-normal leading-snug text-muted-foreground">
          Agents research a stock with open tools, argue both sides, and cite every number. Then the call gets scored.
        </motion.p>
        <motion.div {...item(0.16)} className="mt-8 flex flex-wrap items-center gap-3">
          <Button asChild size="lg">
            <Link to="/app">
              Open terminal <ArrowRight />
            </Link>
          </Button>
          <Button asChild size="lg" variant="secondary">
            <a href="#how">See how it works</a>
          </Button>
        </motion.div>
      </div>
      <motion.div {...item(0.2)} className="lg:col-span-7">
        <Preview />
        <p className="mt-3 px-1 text-caption text-muted-foreground">
          A real run on {snapshot.ticker}, recorded {shortDate(snapshot.captured_at)}. Hover a source tag to see the tool result behind it.
        </p>
      </motion.div>
    </section>
  );
}
