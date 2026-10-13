import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Design tokens are checked, not trusted: every text/background pair that the UI actually uses must meet
 * WCAG AA in BOTH themes (4.5:1 for text). Values are read straight from src/index.css.
 */
const css = readFileSync(resolve(__dirname, '../index.css'), 'utf-8');

function block(selector: string): Record<string, [number, number, number]> {
  const m = css.match(new RegExp(`${selector.replace('.', '\\.')}\\s*\\{([\\s\\S]*?)\\n  \\}`));
  if (!m) throw new Error(`no ${selector} block`);
  const out: Record<string, [number, number, number]> = {};
  for (const line of m[1].split('\n')) {
    const t = line.match(/--([a-z-]+):\s*(-?[\d.]+)\s+([\d.]+)%\s+([\d.]+)%;/);
    if (t) out[t[1]] = [Number(t[2]), Number(t[3]), Number(t[4])];
  }
  return out;
}

type Hsl = [number, number, number];
function toRgb([h, s, l]: Hsl): [number, number, number] {
  const S = s / 100;
  const L = l / 100;
  const k = (n: number) => (n + h / 30) % 12;
  const a = S * Math.min(L, 1 - L);
  const f = (n: number) => L - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [f(0) * 255, f(8) * 255, f(4) * 255];
}
const lum = (rgb: number[]) => {
  const [r, g, b] = rgb.map(v => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a: number[], b: number[]) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
/** foreground colour at `alpha` over a backdrop (how `bg-success/10` really renders) */
const over = (tint: Hsl, alpha: number, backdrop: Hsl) => {
  const t = toRgb(tint);
  const b = toRgb(backdrop);
  return t.map((v, i) => v * alpha + b[i] * (1 - alpha));
};

describe.each([
  ['light', block(':root')],
  ['dark', block('.dark')],
] as const)('%s theme tokens meet WCAG AA', (_name, t) => {
  const pairs: [string, string, string][] = [
    ['foreground', 'background', 'body text'],
    ['foreground', 'card', 'text on surface'],
    ['muted-foreground', 'background', 'secondary text on page'],
    ['muted-foreground', 'card', 'secondary text on surface'],
    ['muted-foreground', 'muted', 'secondary text on muted'],
    ['primary-foreground', 'primary', 'primary button label'],
    ['primary', 'background', 'accent link/text on page'],
    ['primary', 'card', 'accent text on surface'],
    ['destructive-foreground', 'destructive', 'destructive button label'],
    ['destructive', 'card', 'loss text on surface'],
    ['success', 'card', 'gain text on surface'],
    ['warning', 'card', 'warning text on surface'],
    ['popover-foreground', 'popover', 'popover text'],
  ];
  it.each(pairs)('%s on %s (%s)', (fg, bg) => {
    expect(ratio(toRgb(t[fg]), toRgb(t[bg]))).toBeGreaterThanOrEqual(4.5);
  });

  it.each(['primary', 'success', 'warning', 'destructive'])('%s pill (tinted background) is readable', name => {
    const bg = over(t[name], 0.1, t.card);
    expect(ratio(toRgb(t[name]), bg)).toBeGreaterThanOrEqual(4.5);
  });

  it('neutral pill is readable on its own tint', () => {
    expect(ratio(toRgb(t['muted-foreground']), toRgb(t.muted))).toBeGreaterThanOrEqual(4.5);
  });

  it('uses no pure black or pure white as a page background', () => {
    expect(t.background[2]).toBeGreaterThan(0);
    expect(t.background[2]).toBeLessThan(100);
  });
});
