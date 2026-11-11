import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { FAQ, MCP_TOOLS, REPO, snapshot } from '@/landing/data';
import { Features } from '@/landing/Features';
import { FinalCta, Footer } from '@/landing/Footer';
import { Gateway } from '@/landing/Gateway';
import { Hero } from '@/landing/Hero';
import { Honest } from '@/landing/Honest';
import { Modes } from '@/landing/Modes';
import { Nav } from '@/landing/Nav';
import Landing from '@/pages/Landing';

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);
const dir = resolve(__dirname, '../landing');
const sources = readdirSync(dir)
  .filter(f => f.endsWith('.tsx'))
  .map(f => readFileSync(resolve(dir, f), 'utf-8'));
const joined = sources.join(String.fromCharCode(10));
const page = readFileSync(resolve(__dirname, '../pages/Landing.tsx'), 'utf-8');

describe('landing data is real, not typed in', () => {
  it('has a complete recorded research run with cited evidence', () => {
    expect(snapshot.bars.length).toBeGreaterThanOrEqual(60);
    const ids = Object.keys(snapshot.result.evidence);
    const claims = [...snapshot.result.memo.bull_case, ...snapshot.result.memo.bear_case];
    for (const c of claims) for (const id of c.evidence) expect(ids).toContain(id); // every chip resolves
  });

  it('lists exactly the MCP tools the backend server registers', () => {
    const server = readFileSync(resolve(__dirname, '../../backend/axiom/mcp_server/server.py'), 'utf-8');
    const registered = [...server.matchAll(/@mcp\.tool\(\)\s+async def (\w+)\(/g)].map(m => m[1]).sort();
    expect([...MCP_TOOLS].sort()).toEqual(registered);
    expect(registered).toHaveLength(11);
  });

  it('uses real product screenshots that exist', () => {
    for (const img of ['cockpit.jpg', 'journal.jpg']) expect(() => readFileSync(resolve(__dirname, `../../public/landing/${img}`))).not.toThrow();
  });
});

describe('landing sections', () => {
  it('hero has one headline and the primary action', () => {
    wrap(<Hero />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('A trading partner that thinks first.');
    expect(screen.getByRole('link', { name: /Start on paper/ })).toHaveAttribute('href', '/app');
    expect(screen.getByRole('img', { name: /cockpit/ })).toHaveAttribute('src', '/landing/cockpit.jpg');
  });

  it('nav menus open, close on Escape, and link only to sections that exist or to the project', () => {
    wrap(<Nav />);
    const nav = screen.getByRole('navigation', { name: 'Page' });
    for (const label of ['Product', 'Learn']) fireEvent.click(within(nav).getByRole('button', { name: label }));
    const hrefs = within(nav)
      .getAllByRole('link')
      .map(a => a.getAttribute('href') ?? '');
    expect(hrefs.filter(h => h.startsWith('#')).length).toBeGreaterThanOrEqual(5);
    for (const h of hrefs) {
      if (h.startsWith('#')) expect(joined).toContain(`id="${h.slice(1)}"`);
      else expect(h.startsWith(REPO)).toBe(true);
    }
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(within(nav).getByRole('button', { name: 'Learn' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('gateway cards lead somewhere on the page or to the project, never into the app', () => {
    wrap(<Gateway />);
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(6);
    for (const a of links) {
      const h = a.getAttribute('href') ?? '';
      if (h.startsWith('#')) expect(joined).toContain(`id="${h.slice(1)}"`);
      else expect(h.startsWith(REPO)).toBe(true);
    }
  });

  it('every link into the app uses the same words', () => {
    wrap(<Landing />);
    const intoApp = screen.getAllByRole('link').filter(a => a.getAttribute('href') === '/app');
    expect(intoApp.length).toBeGreaterThanOrEqual(3);
    for (const a of intoApp) expect(a).toHaveTextContent('Start on paper');
  });

  it('feature tiles each show a picture of the behaviour', () => {
    wrap(<Features />);
    for (const t of ['It tells you why', 'It knows when to wait', 'It always has a way out', 'You stay in charge']) expect(screen.getByRole('article', { name: t })).toBeInTheDocument();
  });

  it('modes match the three autonomy levels, with the supervised one marked as the start', () => {
    wrap(<Modes />);
    for (const m of ['Watch only', 'Ask me first', 'On its own']) expect(screen.getByRole('heading', { name: m })).toBeInTheDocument();
    const autonomy = readFileSync(resolve(__dirname, '../../backend/axiom/trading/autonomy.py'), 'utf-8');
    for (const level of ['SHADOW', 'SUPERVISED', 'AUTONOMOUS']) expect(autonomy).toContain(level);
    expect(screen.getByText('Recommended start')).toBeInTheDocument();
  });

  it('is honest that it trailed simply holding, and links the report', () => {
    wrap(<Honest />);
    expect(screen.getByText(/made far less when they rose/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /practice report/ })).toHaveAttribute('href', expect.stringContaining('backtest-report.md'));
  });

  it('answers the real-money question first', () => {
    expect(FAQ[0].q).toMatch(/real money/);
    expect(FAQ[0].a).toMatch(/^No\./);
  });

  it('closing section and footer carry the action and the disclaimer, no version strings', () => {
    wrap(
      <>
        <FinalCta />
        <Footer />
      </>,
    );
    for (const a of screen.getAllByRole('link', { name: /Start on paper/ })) expect(a).toHaveAttribute('href', '/app');
    expect(screen.getByText(/not financial advice/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\bv\d+\.\d+/);
  });
});

describe('landing copy rules', () => {
  const all = sources.join('\n') + page;

  it('the hero follows the stack rules: a short headline and sub-20-word sentences', () => {
    const hero = readFileSync(resolve(dir, 'Hero.tsx'), 'utf-8');
    const h1 = hero.match(/<motion\.h1[^>]*>\s*([^<]+?)\s*<\/motion\.h1>/)?.[1] ?? '';
    const subs = [...hero.matchAll(/<motion\.p[^>]*>\s*([^<]+?)\s*<\/motion\.p>/g)].map(m => m[1]);
    expect(h1.split(/\s+/).length).toBeLessThanOrEqual(6);
    expect(subs.length).toBeGreaterThan(0);
    for (const sub of subs) expect(sub.split(/\s+/).length).toBeLessThanOrEqual(20);
  });

  it('speaks plainly: no trading jargon or internal names in visible copy', () => {
    const visible = [...all.matchAll(/>([^<>{}]+)</g)].map(m => m[1]).join(' ');
    expect(visible).not.toMatch(/\b(kernel|Brier|Sharpe|walk-forward|tournament|LLM|drawdown|calibration|R\d{1,2})\b/i);
  });

  it('never uses banned call-to-action labels, filler verbs, scroll cues or fake versions', () => {
    for (const dup of ['Get started', 'Start now', 'Try it free', 'Launch app', 'Sign up']) expect(all).not.toContain(dup);
    expect(all).not.toMatch(/\b(elevate|seamless|unleash|next-gen|revolutionize|supercharge)\b/i);
    expect(all).not.toMatch(/scroll to|Scroll down/i);
    expect(all).not.toMatch(/\bBETA\b|\bv0\.\d|invite-only|early access/i);
  });

  it('never uses a fixed 100vh hero or scroll listeners', () => {
    expect(all).not.toMatch(/h-screen|100vh/);
    expect(all).not.toMatch(/addEventListener\(\s*['"]scroll/);
  });
});
