import { useReducedMotion } from 'motion/react';

/**
 * Motion presets, from Apple's "Designing Fluid Interfaces": think in damping ratio + response,
 * not duration. Start critically damped (no overshoot) and add bounce only when the gesture itself
 * carried momentum (a flick or throw). Springs, not CSS keyframes, for anything the user can touch,
 * because a spring re-targets from the live value and stays interruptible.
 */
export const spring = {
  /** default: graceful, no overshoot */
  default: { type: 'spring', bounce: 0, duration: 0.4 },
  /** quick state changes: tabs, toggles, indicator slides */
  snappy: { type: 'spring', bounce: 0, duration: 0.28 },
  /** after a flick or drag release only */
  momentum: { type: 'spring', bounce: 0.2, duration: 0.4 },
  /** sheets and drawers */
  sheet: { type: 'spring', bounce: 0.18, duration: 0.35 },
} as const;

/** Press feedback fires on pointer-down, instantly (apple-design section 1). */
export const press = {
  whileTap: { scale: 0.97 },
  transition: { duration: 0.1, ease: 'easeOut' },
} as const;

/** Reveal-on-view: hierarchy motion. Collapses to an opacity cross-fade under reduced motion. */
export function reveal(reduce: boolean | null, delay = 0) {
  return reduce
    ? { initial: { opacity: 0 }, whileInView: { opacity: 1 }, viewport: { once: true, amount: 0.25 }, transition: { duration: 0.2, delay } }
    : {
        initial: { opacity: 0, y: 18 },
        whileInView: { opacity: 1, y: 0 },
        viewport: { once: true, amount: 0.25 },
        transition: { ...spring.default, delay },
      };
}

export { useReducedMotion };

/** Release-velocity projection for flick landing points: the exponential-decay form Apple ships. */
export function project(velocityPxPerSec: number, decelerationRate = 0.998): number {
  return ((velocityPxPerSec / 1000) * decelerationRate) / (1 - decelerationRate);
}

/** Soft boundary: progressive resistance past an edge instead of a hard stop. */
export function rubberband(overshoot: number, dimension: number, constant = 0.55): number {
  return (overshoot * dimension * constant) / (dimension + constant * Math.abs(overshoot));
}
