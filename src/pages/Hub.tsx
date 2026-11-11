import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { DefList } from '@/components/kit/DefList';
import { Section, Surface } from '@/components/kit/Surface';
import { Button } from '@/components/ui/button';
import { CodeBlock } from '@/landing/CodeBlock';
import { Footer } from '@/landing/Footer';
import { Nav } from '@/landing/Nav';
import { DOCS, LAUNCHER, LIVE, PARTS, blobUrl, type Doc, type Part, type PartId } from '@/hub/parts';
import { ago, latestRun, reachable, runSignal, type Signal, type Tone } from '@/hub/status';
import { API_BASE, api } from '@/lib/api';
import type { ApiStatus } from '@/lib/types';
import { cn } from '@/lib/utils';

const DOT: Record<Tone, string> = {
  up: 'bg-success',
  down: 'bg-destructive',
  warn: 'bg-warning',
  unknown: 'bg-muted-foreground/50',
  local: 'bg-primary',
};

function Pill({ signal }: { signal: Signal }) {
  return (
    <span role="status" data-tone={signal.tone} className="inline-flex items-center gap-2 rounded-full border border-border px-2.5 py-1 text-caption">
      <span aria-hidden className={cn('size-2 rounded-full', DOT[signal.tone])} />
      {signal.label}
    </span>
  );
}

const host = (url: string) => url.replace(/^https?:\/\//, '').replace(/\/$/, '');

function apiSignal(data: ApiStatus | undefined, failed: boolean): Signal {
  if (failed) return { tone: 'down', label: 'Unreachable', detail: `Tried ${host(API_BASE)}` };
  if (!data) return { tone: 'unknown', label: 'Checking' };
  const last = data.counts.last_run_at ? `last run ${ago(data.counts.last_run_at * 1000)}` : 'no runs yet';
  return { tone: 'up', label: 'Online', detail: `${host(API_BASE)}, ${last}` };
}

function apiFacts(s: ApiStatus) {
  const open = s.counts.theses.open ?? 0;
  const scored = s.counts.theses.scored ?? 0;
  const cap = s.analyses_today.cap;
  return [
    { label: 'Runs stored', value: s.counts.runs },
    { label: 'Theses', value: `${open} open, ${scored} scored` },
    { label: 'Awaiting approval', value: s.counts.actions.proposed ?? 0 },
    { label: 'Models', value: s.llm_chain.length ? s.llm_chain.join(', ') : 'none set' },
    { label: 'Storage', value: s.storage ?? 'unknown' },
    ...(cap ? [{ label: 'Analyses today', value: `${s.analyses_today.used ?? 0} of ${cap}` }] : []),
  ];
}

function PartCard({ part, signal, facts }: { part: Part; signal: Signal; facts?: { label: string; value: React.ReactNode }[] }) {
  return (
    <Surface className="flex min-w-0 flex-col p-5 sm:p-6" aria-labelledby={`part-${part.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id={`part-${part.id}`} className="text-h3">
            {part.name}
          </h2>
          <p className="mt-0.5 font-mono text-caption text-muted-foreground">{part.folder}</p>
        </div>
        <Pill signal={signal} />
      </div>
      {signal.detail && (
        <p className="mt-2 text-caption text-muted-foreground">
          {signal.href ? (
            <a className="underline-offset-2 hover:text-foreground hover:underline" href={signal.href} target="_blank" rel="noreferrer">
              {signal.detail}
            </a>
          ) : (
            signal.detail
          )}
        </p>
      )}
      <p className="mt-3 text-body">{part.purpose}</p>

      <DefList
        className="mt-4"
        items={[
          { label: 'Stack', value: part.stack },
          { label: 'Needs', value: part.needs },
          ...(part.port ? [{ label: 'Local port', value: part.port }] : []),
          ...(facts ?? []),
        ]}
      />

      <div className="mt-4">
        <CodeBlock code={part.run} label={`command to run ${part.name}`} />
      </div>

      <div className="mt-auto flex flex-wrap gap-2 pt-5">
        {part.live && (
          <Button asChild size="sm">
            <a href={part.live} target="_blank" rel="noreferrer">
              {part.id === 'data' ? 'See runs' : 'Open'} <ArrowUpRight aria-hidden />
            </a>
          </Button>
        )}
        <Button asChild size="sm" variant="outline">
          <a href={blobUrl(part.docs)} target="_blank" rel="noreferrer">
            Docs
          </a>
        </Button>
      </div>
    </Surface>
  );
}

const STATUS_LABEL: Record<Doc['status'], string> = { current: 'Current', generated: 'Generated', historical: 'Historical' };

export default function Hub() {
  useEffect(() => {
    document.title = 'Axiom hub: every part in one place';
  }, []);

  const status = useQuery({ queryKey: ['hub', 'status'], queryFn: api.status, retry: 1, refetchInterval: 60_000 });
  const watch = useQuery({ queryKey: ['hub', 'watch'], queryFn: () => reachable(`${LIVE.watch}/config.json`), staleTime: 5 * 60_000 });
  const elt = useQuery({ queryKey: ['hub', 'gh', 'data'], queryFn: () => latestRun('data-platform.yml'), retry: false, staleTime: 10 * 60_000 });
  const ci = useQuery({ queryKey: ['hub', 'gh', 'ci'], queryFn: () => latestRun('ci.yml', 'main'), retry: false, staleTime: 10 * 60_000 });

  const signals: Record<PartId, Signal> = {
    terminal: { tone: 'up', label: 'You are here' },
    api: apiSignal(status.data, status.isError),
    watch:
      watch.data === undefined
        ? { tone: 'unknown', label: 'Checking' }
        : watch.data
          ? { tone: 'up', label: 'Reachable' }
          : { tone: 'down', label: 'Unreachable' },
    mcp: { tone: 'local', label: 'Local only' },
    data: runSignal(elt.data, elt.isError, PARTS.find(p => p.id === 'data')!.live!),
  };
  const ciSignal = runSignal(ci.data, ci.isError, 'https://github.com/amaltomajith/Axiom/actions/workflows/ci.yml');

  return (
    <div className="min-h-[100dvh] bg-background">
      <Nav />
      <main className="mx-auto max-w-[1200px] px-4 pb-24 pt-12 sm:px-6 sm:pt-16">
        <header className="max-w-[60ch]">
          <p className="text-small font-medium text-primary">Hub</p>
          <h1 className="mt-2 text-h1">Everything in Axiom, in one place</h1>
          <p className="mt-3 text-body text-muted-foreground">
            Axiom is two apps on one API, an MCP server for AI clients and a data platform that copies the results into
            BigQuery. Each card says what a part is for, whether it is up and how to run it.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <span className="text-small text-muted-foreground">Tests on main</span>
            <Pill signal={ciSignal} />
            {ciSignal.detail && ciSignal.href && (
              <a className="text-caption text-muted-foreground hover:text-foreground" href={ciSignal.href} target="_blank" rel="noreferrer">
                {ciSignal.detail}
              </a>
            )}
          </div>
        </header>

        <div className="mt-10 grid gap-4 md:grid-cols-2" aria-label="Parts">
          {PARTS.map(p => (
            <PartCard key={p.id} part={p} signal={signals[p.id]} facts={p.id === 'api' && status.data ? apiFacts(status.data) : undefined} />
          ))}
        </div>

        <Section
          className="mt-10"
          title="Run it all locally"
          description="One command starts the API, the terminal and Axiom Watch, each with its own prefix in the log. Ctrl+C stops all of them."
        >
          <div className="space-y-3 px-5 pb-5 sm:px-6 sm:pb-6">
            <CodeBlock code={LAUNCHER} label="launcher commands" />
            <p className="text-caption text-muted-foreground">
              It refuses to start when backend/.env points at a production database, and skips Axiom Watch with a fix if
              your Node is too old for Angular. Then open{' '}
              <Link className="underline underline-offset-2 hover:text-foreground" to="/hub">
                localhost:5173/hub
              </Link>
              .
            </p>
          </div>
        </Section>

        <Section className="mt-4" title="Docs map" description="Every doc in the repo, and whether it still describes the code.">
          <ul className="divide-y divide-border border-t border-border">
            {DOCS.map(d => (
              <li key={d.path} className="flex flex-col gap-1 px-5 py-3 sm:flex-row sm:items-baseline sm:gap-4 sm:px-6">
                <a className="shrink-0 text-small font-medium hover:underline sm:w-48" href={blobUrl(d.path)} target="_blank" rel="noreferrer">
                  {d.title}
                </a>
                <span className="min-w-0 flex-1 text-small text-muted-foreground">{d.purpose}</span>
                <span className={cn('shrink-0 text-caption', d.status === 'historical' ? 'text-warning' : 'text-muted-foreground')}>
                  {STATUS_LABEL[d.status]}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      </main>
      <Footer />
    </div>
  );
}
