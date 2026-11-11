import { GITHUB_API } from './parts';

export type Tone = 'up' | 'down' | 'warn' | 'unknown' | 'local';

export interface Signal {
  tone: Tone;
  label: string;
  /** Optional detail line under the pill, and a link to the evidence. */
  detail?: string;
  href?: string;
}

export interface WorkflowRun {
  status: string;
  conclusion: string | null;
  created_at: string;
  html_url: string;
  head_branch: string;
}

/**
 * Latest run of a GitHub Actions workflow. The repo is public, so this needs no token; unauthenticated
 * calls are limited to 60 an hour per IP, which a page view or two never reaches (react-query caches it).
 */
export async function latestRun(workflow: string, branch?: string, fetchImpl: typeof fetch = fetch): Promise<WorkflowRun | null> {
  const q = new URLSearchParams({ per_page: '1', ...(branch ? { branch } : {}) });
  const res = await fetchImpl(`${GITHUB_API}/actions/workflows/${workflow}/runs?${q}`, {
    headers: { Accept: 'application/vnd.github+json' },
  });
  if (!res.ok) throw new Error(`GitHub answered ${res.status}`);
  const body = (await res.json()) as { workflow_runs?: WorkflowRun[] };
  return body.workflow_runs?.[0] ?? null;
}

export function runSignal(run: WorkflowRun | null | undefined, failed: boolean, fallbackHref: string): Signal {
  if (failed) return { tone: 'unknown', label: 'Status unavailable', detail: 'GitHub did not answer', href: fallbackHref };
  if (run === undefined) return { tone: 'unknown', label: 'Checking' };
  if (run === null) return { tone: 'unknown', label: 'No runs yet', href: fallbackHref };
  const when = `${ago(Date.parse(run.created_at))} on ${run.head_branch}`;
  if (run.status !== 'completed') return { tone: 'warn', label: 'Running now', detail: when, href: run.html_url };
  if (run.conclusion === 'success') return { tone: 'up', label: 'Last run passed', detail: when, href: run.html_url };
  return { tone: 'down', label: `Last run ${run.conclusion ?? 'ended'}`, detail: when, href: run.html_url };
}

/**
 * A cross-origin page cannot read another site's response without CORS, but a no-cors fetch still
 * rejects when the host is unreachable. That is all a "is it up" pill needs.
 */
export async function reachable(url: string, fetchImpl: typeof fetch = fetch): Promise<boolean> {
  try {
    await fetchImpl(url, { mode: 'no-cors', cache: 'no-store' });
    return true;
  } catch {
    return false;
  }
}

/** "3 min ago", "5 h ago", "2 days ago". Coarse on purpose: the hub is a glance, not a log. */
export function ago(ms: number, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 90) return 'just now';
  const m = Math.round(s / 60);
  if (m < 90) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 36) return `${h} h ago`;
  const d = Math.round(h / 24);
  return `${d} day${d === 1 ? '' : 's'} ago`;
}
