import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { MCP_TOOLS, snapshot } from '@/landing/data';
import { Evals } from '@/landing/Evals';
import { Footer } from '@/landing/Footer';
import { LogoWall } from '@/landing/LogoWall';
import { McpSection } from '@/landing/McpSection';
import { Nav } from '@/landing/Nav';
import { StackSection } from '@/landing/StackSection';
import { Walkthrough } from '@/landing/Walkthrough';

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe('landing data is real, not typed in', () => {
  it('has a complete recorded run with prices, cone, trace and cited evidence', () => {
    expect(snapshot.bars.length).toBeGreaterThanOrEqual(60);
    expect(snapshot.cone.length).toBe(14);
    expect(snapshot.events.length).toBeGreaterThan(20);
    const ids = Object.keys(snapshot.result.evidence);
    const claims = [...snapshot.result.memo.bull_case, ...snapshot.result.memo.bear_case];
    for (const c of claims) for (const id of c.evidence) expect(ids).toContain(id); // every chip resolves
    expect(snapshot.backtest.verdict).toMatch(/^(no_edge|unproven|edge_detected|insufficient_data)$/);
  });

  it('carries a real, unsent approval payload and honest eval numbers', () => {
    expect(snapshot.approval.plan?.steps.map(s => s.kind)).toContain('sheet_row');
    expect(snapshot.approval.plan?.executor).toBe('dry_run');
    expect(snapshot.evals.passed).toMatch(/^\d+\/\d+$/);
    expect(snapshot.evals.control_obeyed).toMatch(/^\d+\/\d+$/);
    expect(snapshot.scorecard.sample_note).toMatch(/need/i);
  });

  it('lists exactly the MCP tools the backend server registers', () => {
    const server = readFileSync(resolve(__dirname, '../../backend/axiom/mcp_server/server.py'), 'utf-8');
    const registered = [...server.matchAll(/@mcp\.tool\(\)\s+async def (\w+)\(/g)].map(m => m[1]).sort();
    expect([...MCP_TOOLS].sort()).toEqual(registered);
    expect(registered).toHaveLength(11);
  });
});

describe('landing sections', () => {
  it('nav has one primary call to action and labelled landmarks', () => {
    wrap(<Nav />);
    expect(screen.getByRole('link', { name: 'Open terminal' })).toHaveAttribute('href', '/app');
    expect(screen.getByRole('navigation', { name: 'Page' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /switch to (dark|light) mode/i })).toBeInTheDocument();
  });

  it('logo wall shows logos only, each named for screen readers, with no category labels', () => {
    wrap(<LogoWall />);
    const list = screen.getByRole('list');
    const items = within(list).getAllByRole('listitem');
    expect(items.length).toBeGreaterThanOrEqual(6);
    for (const li of items) expect(li.querySelector('svg')).not.toBeNull();
    expect(list.textContent?.replace(/\s/g, '').length).toBeLessThan(200); // only svg <title>s, no printed labels
    expect(screen.queryByRole('img', { name: /slack|groq/i })).toBeNull(); // not in simple-icons: omitted, not faked
  });

  it('walkthrough renders all five steps with real visuals when motion is allowed to stack', () => {
    wrap(<Walkthrough />);
    for (const step of ['Gather', 'Debate', 'Guard', 'Approve', 'Score']) expect(screen.getAllByText(step).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Recorded run/).length).toBeGreaterThan(0);
  });

  it('evals section shows the real figures and the judge caveat', () => {
    wrap(<Evals />);
    expect(screen.getByText(/scenarios passed/)).toBeInTheDocument();
    expect(screen.getByText(/noisy signal/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Read the full report/ })).toHaveAttribute('href', expect.stringContaining('eval-report.md'));
    expect(screen.getByText('earned_edge')).toBeInTheDocument();
  });

  it('mcp section lists every tool and gives copyable setup for both clients', () => {
    wrap(<McpSection />);
    for (const t of MCP_TOOLS) expect(screen.getByText(t)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy Claude Code command' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy Claude Desktop configuration' })).toBeInTheDocument();
  });

  it('stack section states its limits plainly', () => {
    wrap(<StackSection />);
    expect(screen.getByRole('list', { name: 'Model fallback order' })).toBeInTheDocument();
    expect(screen.getByText(/not been run against a live account/)).toBeInTheDocument();
  });

  it('footer carries the disclaimer and no version strings', () => {
    wrap(<Footer />);
    expect(screen.getByText(/not financial advice/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\bv\d+\.\d+/);
  });
});

describe('landing copy rules', () => {
  const sources = ['Hero', 'Nav', 'LogoWall', 'Walkthrough', 'Honest', 'Evals', 'McpSection', 'StackSection', 'Footer'].map(n => readFileSync(resolve(__dirname, `../landing/${n}.tsx`), 'utf-8'));

  it('the hero follows the stack rules: a short headline and a sub-20-word sentence', () => {
    const hero = readFileSync(resolve(__dirname, '../landing/Hero.tsx'), 'utf-8');
    const h1 = hero.match(/<motion\.h1[^>]*>\s*([^<]+?)\s*<\/motion\.h1>/)?.[1] ?? '';
    const sub = hero.match(/<motion\.p[^>]*>\s*([^<]+?)\s*<\/motion\.p>/)?.[1] ?? '';
    expect(h1.split(/\s+/).length).toBeLessThanOrEqual(6);
    expect(sub.split(/\s+/).length).toBeLessThanOrEqual(20);
  });

  it('uses one label for the primary intent everywhere', () => {
    const all = sources.join('\n') + readFileSync(resolve(__dirname, '../pages/Landing.tsx'), 'utf-8');
    expect((all.match(/Open terminal/g) ?? []).length).toBeGreaterThanOrEqual(3);
    for (const dup of ['Get started', 'Start now', 'Try it free', 'Launch app', 'Sign up']) expect(all).not.toContain(dup);
  });

  it('has no scroll cues, fake version labels, banned filler verbs or section numbering', () => {
    const all = sources.join('\n');
    expect(all).not.toMatch(/scroll to|Scroll down|↓ scroll/i);
    expect(all).not.toMatch(/\bBETA\b|\bv0\.\d|invite-only|early access/i);
    expect(all).not.toMatch(/\b(elevate|seamless|unleash|next-gen|revolutionize|supercharge)\b/i);
    expect(all).not.toMatch(/\b0\d\s*\/\s*0?\d|\bStep \d|\bStage \d|\bPhase \d/);
  });

  it('never uses a fixed 100vh hero or scroll listeners', () => {
    const all = sources.join('\n');
    expect(all).not.toMatch(/h-screen|100vh/);
    expect(all).not.toMatch(/addEventListener\(\s*['"]scroll/);
  });
});
