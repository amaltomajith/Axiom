import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DOCS, LIVE, PARTS } from '@/hub/parts';
import { ago, latestRun, reachable, runSignal, type WorkflowRun } from '@/hub/status';
import Hub from '@/pages/Hub';

const repo = resolve(__dirname, '../..');
const read = (p: string) => readFileSync(resolve(repo, p), 'utf-8');

describe('the hub manifest matches the repo', () => {
  it('points every part and doc at a file that exists', () => {
    for (const p of PARTS) {
      expect(existsSync(resolve(repo, p.folder)), p.folder).toBe(true);
      expect(existsSync(resolve(repo, p.docs)), p.docs).toBe(true);
    }
    for (const d of DOCS) expect(existsSync(resolve(repo, d.path)), d.path).toBe(true);
  });

  it('lists every doc in docs/README.md, and every live URL in the README', () => {
    const index = read('docs/README.md');
    for (const d of DOCS.filter(d => d.path !== 'docs/README.md')) {
      const rel = d.path.startsWith('docs/') ? d.path.slice('docs/'.length) : `../${d.path}`;
      expect(index, d.path).toContain(encodeURI(rel));
    }
    const readme = read('README.md');
    for (const url of Object.values(LIVE)) expect(readme).toContain(url);
  });

  it('names the launcher script that exists', () => {
    const pkg = JSON.parse(read('package.json')) as { scripts: Record<string, string> };
    expect(pkg.scripts['dev:all']).toMatch(/scripts\/dev\.mjs/);
    expect(existsSync(resolve(repo, 'scripts/dev.mjs'))).toBe(true);
  });
});

describe('status helpers', () => {
  const run = (over: Partial<WorkflowRun>): WorkflowRun => ({
    status: 'completed', conclusion: 'success', created_at: new Date().toISOString(),
    html_url: 'https://github.com/x/y/actions/runs/1', head_branch: 'main', ...over,
  });

  it('turns a workflow run into a pill', () => {
    expect(runSignal(run({}), false, '#').tone).toBe('up');
    expect(runSignal(run({ conclusion: 'failure' }), false, '#')).toMatchObject({ tone: 'down', label: 'Last run failure' });
    expect(runSignal(run({ status: 'in_progress', conclusion: null }), false, '#').tone).toBe('warn');
    expect(runSignal(undefined, true, '#')).toMatchObject({ tone: 'unknown', href: '#' });
    expect(runSignal(null, false, '#').label).toBe('No runs yet');
  });

  it('reads the latest run and reports GitHub errors', async () => {
    const ok = vi.fn().mockResolvedValue(new Response(JSON.stringify({ workflow_runs: [run({})] })));
    expect((await latestRun('ci.yml', 'main', ok))?.conclusion).toBe('success');
    expect(String(ok.mock.calls[0][0])).toContain('/actions/workflows/ci.yml/runs?per_page=1&branch=main');
    const limited = vi.fn().mockResolvedValue(new Response('{}', { status: 403 }));
    await expect(latestRun('ci.yml', undefined, limited)).rejects.toThrow('403');
  });

  it('treats a rejected no-cors fetch as unreachable', async () => {
    expect(await reachable('https://x', vi.fn().mockResolvedValue(new Response(null)))).toBe(true);
    expect(await reachable('https://x', vi.fn().mockRejectedValue(new TypeError('offline')))).toBe(false);
  });

  it('says how long ago in coarse steps', () => {
    const now = 1_000_000_000_000;
    expect(ago(now - 30_000, now)).toBe('just now');
    expect(ago(now - 20 * 60_000, now)).toBe('20 min ago');
    expect(ago(now - 5 * 3_600_000, now)).toBe('5 h ago');
    expect(ago(now - 3 * 86_400_000, now)).toBe('3 days ago');
  });
});

describe('hub page', () => {
  afterEach(() => vi.unstubAllGlobals());

  const renderHub = () =>
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <Hub />
        </MemoryRouter>
      </QueryClientProvider>,
    );

  it('renders every part even when nothing answers', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    renderHub();
    for (const p of PARTS) expect(screen.getByRole('heading', { name: p.name })).toBeInTheDocument();
    const api = screen.getByRole('heading', { name: 'Axiom API' }).closest('div.surface') as HTMLElement;
    // The page retries the API once before calling it unreachable, so allow for the retry delay.
    await waitFor(() => expect(within(api).getByRole('status')).toHaveTextContent('Unreachable'), { timeout: 5000 });
    expect(screen.getAllByRole('link', { name: /docs/i }).length).toBeGreaterThanOrEqual(PARTS.length);
  });

  it('shows live API counts when the API answers', async () => {
    const status = {
      ok: true, llm_chain: ['groq'], llm_models: {}, market_data: 'yfinance', news: 'google_news_rss',
      actions_executor: 'dry_run', auth_required: false, scheduler: false, storage: 'sqlite', daily_cap: null,
      counts: { runs: 7, last_run_at: Date.now() / 1000, theses: { open: 3, scored: 2 }, actions: { proposed: 1 }, watchlist: 2, trades: 0 },
      analyses_today: { used: null, cap: null },
    };
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        String(url).includes('/api/status') ? Promise.resolve(new Response(JSON.stringify(status))) : Promise.reject(new TypeError('offline')),
      ),
    );
    renderHub();
    const api = screen.getByRole('heading', { name: 'Axiom API' }).closest('div.surface') as HTMLElement;
    await waitFor(() => expect(within(api).getByRole('status')).toHaveTextContent('Online'));
    expect(within(api).getByText('3 open, 2 scored')).toBeInTheDocument();
    expect(within(api).getByText('7')).toBeInTheDocument();
  });
});
