import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';

/**
 * Axiom's house rules, enforced mechanically (ported from the React app's copy.test.ts and tokens.test.ts):
 *  - no em-dash or en-dash anywhere in shipped source, visible strings included
 *  - no text under 12px
 *  - every text/background token pair meets WCAG AA (4.5:1) in both themes
 */
const src = resolve(process.cwd(), 'src');

function files(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) files(p, out);
    else if (/\.(ts|html|scss|css|json)$/.test(name) && !name.endsWith('.spec.ts') && !p.includes('testing')) out.push(p);
  }
  return out;
}

describe('copy and type rules', () => {
  const sources = files(src);

  it('finds the sources it is supposed to scan', () => {
    expect(sources.length).toBeGreaterThan(25);
  });

  it('contains no em-dash or en-dash characters', () => {
    const hits: string[] = [];
    for (const f of sources) {
      readFileSync(f, 'utf-8')
        .split('\n')
        .forEach((line, i) => {
          if (/[–—]/.test(line)) hits.push(`${f.replace(src, 'src')}:${i + 1}`);
        });
    }
    expect(hits).toEqual([]);
  });

  it('never sets a font size under 12px (0.75rem)', () => {
    const hits: string[] = [];
    for (const f of sources.filter(p => /\.(s?css|ts)$/.test(p))) {
      for (const m of readFileSync(f, 'utf-8').matchAll(/font-size:\s*([\d.]+)(px|rem|em)/g)) {
        const px = m[2] === 'px' ? Number(m[1]) : Number(m[1]) * 16;
        if (px < 12) hits.push(`${f.replace(src, 'src')}: ${m[0]}`);
      }
      for (const m of readFileSync(f, 'utf-8').matchAll(/--text-[a-z0-9]+:\s*([\d.]+)rem/g)) {
        if (Number(m[1]) * 16 < 12) hits.push(`${f.replace(src, 'src')}: ${m[0]}`);
      }
    }
    expect(hits).toEqual([]);
  });

  it('loads no remote fonts (fonts are self-hosted)', () => {
    const css = sources.filter(p => /\.(s?css|html)$/.test(p)).map(p => readFileSync(p, 'utf-8')).join('\n');
    expect(css).not.toMatch(/fonts\.googleapis|fonts\.gstatic/);
  });
});

type Hsl = [number, number, number];
const tokensCss = readFileSync(join(src, 'styles', 'tokens.css'), 'utf-8');

function tokens(block: string): Record<string, Hsl> {
  const out: Record<string, Hsl> = {};
  for (const m of block.matchAll(/--([a-z-]+):\s*(-?[\d.]+)\s+([\d.]+)%\s+([\d.]+)%;/g)) out[m[1]] = [Number(m[2]), Number(m[3]), Number(m[4])];
  return out;
}

const light = tokens(tokensCss.slice(0, tokensCss.indexOf('@media (prefers-color-scheme: dark)')));
const darkStart = tokensCss.indexOf('@media (prefers-color-scheme: dark)');
const dark = tokens(tokensCss.slice(darkStart, tokensCss.indexOf('@media (prefers-contrast', darkStart)));

function toRgb([h, s, l]: Hsl): number[] {
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
/** a colour at `alpha` over a backdrop: how `hsl(var(--success) / 0.1)` pills really render */
const over = (tint: Hsl, alpha: number, backdrop: Hsl) => {
  const t = toRgb(tint);
  const b = toRgb(backdrop);
  return t.map((v, i) => v * alpha + b[i] * (1 - alpha));
};

describe.each([
  ['light', light],
  ['dark', dark],
] as const)('%s theme tokens meet WCAG AA', (_name, t) => {
  it('parsed the theme', () => {
    expect(Object.keys(t).length).toBeGreaterThan(20);
  });

  it.each([
    ['foreground', 'background'],
    ['foreground', 'card'],
    ['muted-foreground', 'background'],
    ['muted-foreground', 'card'],
    ['muted-foreground', 'muted'],
    ['primary-foreground', 'primary'],
    ['primary', 'background'],
    ['destructive', 'card'],
    ['success', 'card'],
    ['warning', 'card'],
    ['popover-foreground', 'popover'],
  ])('%s on %s', (fg, bg) => {
    expect(ratio(toRgb(t[fg]), toRgb(t[bg]))).toBeGreaterThanOrEqual(4.5);
  });

  it.each(['success', 'warning', 'destructive'])('%s text on its 10% tint (rating pills, notices)', name => {
    expect(ratio(toRgb(t[name]), over(t[name], 0.1, t['card']))).toBeGreaterThanOrEqual(4.5);
  });
});
