import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * House copy rules, enforced mechanically:
 *  - no em-dash or en-dash anywhere in shipped source (visible strings included)
 *  - no sub-12px type, no leftover template fonts
 */
const root = resolve(__dirname, '..');

function files(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (name === 'test') continue;
      files(p, out);
    } else if (/\.(tsx?|css|json)$/.test(name)) out.push(p);
  }
  return out;
}

describe('copy and type rules', () => {
  const sources = files(root);

  it('finds the sources it is supposed to scan', () => {
    expect(sources.length).toBeGreaterThan(30);
  });

  it('contains no em-dash or en-dash characters', () => {
    const hits: string[] = [];
    for (const f of sources) {
      readFileSync(f, 'utf-8')
        .split('\n')
        .forEach((line, i) => {
          if (/[—–]/.test(line)) hits.push(`${f.replace(root, 'src')}:${i + 1}  ${line.trim().slice(0, 80)}`);
        });
    }
    expect(hits).toEqual([]);
  });

  it('never uses the banned 10px/11px text sizes', () => {
    const hits = sources.filter(f => f.endsWith('.tsx') && /text-\[1[01]px\]/.test(readFileSync(f, 'utf-8')));
    expect(hits).toEqual([]);
  });

  it('does not link remote fonts or use the retired template styles', () => {
    const css = readFileSync(join(root, 'index.css'), 'utf-8');
    expect(css).not.toMatch(/fonts\.googleapis|JetBrains|Space Grotesk/);
    expect(css).not.toMatch(/glass-card|gradient-border|terminal-grid|glow-/);
  });
});
