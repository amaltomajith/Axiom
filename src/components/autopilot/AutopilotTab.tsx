import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Bot, ShieldCheck, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/kit/EmptyState';
import { SkeletonBlock } from '@/components/kit/Skeleton';
import { trader } from '@/lib/api';
import type { RedteamResult } from '@/lib/types';
import { Approvals, Positions } from './Book';
import { ControlBar } from './ControlBar';
import { JournalFeed } from './JournalFeed';
import { Contracts, EquityChart } from './Performance';
import { ReportView, TimeMachine } from './TimeMachine';
import { TRADER_KEY, useTraderStream } from './useTrader';

function RedteamCard({ r, onClose }: { r: RedteamResult; onClose: () => void }) {
  return (
    <section className="surface overflow-hidden" aria-label="Red team result" role="status">
      <header className="flex items-start justify-between gap-3 px-5 pb-2 pt-4 sm:px-6">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-success" />
          <h2 className="text-h3">{r.approved ? 'The kernel let it through' : 'Both attacks were stopped'}</h2>
        </div>
        <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Dismiss">
          <X />
        </Button>
      </header>
      <ul className="space-y-2 px-5 pb-4 text-small sm:px-6">
        <li>
          <span className="font-medium">An order for 1,000,000 units:</span> blocked by {r.failed_rules.join(', ') || 'no rule'}. {r.verdict.reason}
        </li>
        <li>
          <span className="font-medium">A poisoned headline</span> ("
          {r.headline.text}"): {r.headline.flagged ? 'flagged as a prompt injection. The model would only see:' : 'not flagged.'}{' '}
          {r.headline.model_sees && <span className="font-mono text-caption">{r.headline.model_sees}</span>}
        </li>
      </ul>
    </section>
  );
}

/** The Autopilot cockpit: controls, risk budget, positions, approvals, journal, equity, contracts, Time Machine. */
export function AutopilotTab() {
  const [session, setSession] = useState('live');
  const [redteam, setRedteam] = useState<RedteamResult | null>(null);
  const connected = useTraderStream(session);
  const status = useQuery({
    queryKey: [TRADER_KEY, 'status'],
    queryFn: trader.status,
    refetchInterval: 10_000,
    retry: false,
  });
  const live = session === 'live';

  if (status.isLoading) return <SkeletonBlock className="h-[320px]" />;
  if (status.isError || !status.data) {
    return (
      <div className="surface">
        <EmptyState icon={Bot} title="The Autopilot is not reachable" description={(status.error as Error | null)?.message ?? 'Start the backend on port 8000.'} />
      </div>
    );
  }
  const s = status.data;
  if (!s.ok) {
    return (
      <div className="surface">
        <EmptyState icon={Bot} title="The Autopilot could not start" description={s.error ?? 'Check the trader settings in backend/.env.example.'} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <ControlBar status={s} onRedteam={setRedteam} />
      {redteam && <RedteamCard r={redteam} onClose={() => setRedteam(null)} />}
      <Approvals pending={s.pending ?? []} />
      {!live && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-muted/60 px-4 py-2.5 text-small">
          <Badge variant="warning">Time Machine</Badge>
          <span>Viewing a historical replay ({session}). Nothing here touched a broker.</span>
          <Button size="xs" variant="ghost" className="ml-auto" onClick={() => setSession('live')}>
            Back to live
          </Button>
        </div>
      )}
      <div className="grid items-start gap-6 lg:grid-cols-12">
        <div className="space-y-6 lg:col-span-7">
          <EquityChart session={session} />
          <JournalFeed session={session} />
        </div>
        <div className="space-y-6 lg:col-span-5">
          {live && <Positions />}
          <Contracts session={session} />
          <TimeMachine session={session} onSession={setSession} />
          <ReportView />
          <p className="px-1 text-caption text-muted-foreground">Paper trading only: no setting enables real money. Live updates {connected ? 'are streaming' : 'fall back to polling'}.</p>
        </div>
      </div>
    </div>
  );
}
