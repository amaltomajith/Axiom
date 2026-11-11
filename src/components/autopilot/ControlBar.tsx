import { OctagonX, Play, ShieldAlert, Square, Undo2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ConfirmButton } from '@/components/kit/ConfirmButton';
import { trader } from '@/lib/api';
import { frac, money } from '@/lib/format';
import type { Autonomy, LadderProgress, RedteamResult, TraderStatus } from '@/lib/types';
import { cn } from '@/lib/utils';
import { useTraderAction } from './useTrader';

const LEVELS: { id: Autonomy; label: string; hint: string }[] = [
  {
    id: 'SHADOW',
    label: 'Shadow',
    hint: 'Decides and keeps score. Trades nothing.',
  },
  {
    id: 'SUPERVISED',
    label: 'Supervised',
    hint: 'Proposes each entry. A human approves it.',
  },
  {
    id: 'AUTONOMOUS',
    label: 'Autonomous',
    hint: 'Trades on its own, still inside every kernel rule.',
  },
];

/** The earned autonomy ladder: where the agent stands and what it still has to prove. */
export function Ladder({ level, progress, onSet, busy }: { level: Autonomy; progress?: LadderProgress | null; onSet: (l: Autonomy) => void; busy: boolean }) {
  const at = LEVELS.findIndex(l => l.id === level);
  return (
    <div>
      <ol className="grid grid-cols-3 gap-2" aria-label="Autonomy ladder">
        {LEVELS.map((l, i) => (
          <li key={l.id}>
            <button
              type="button"
              disabled={busy || l.id === level}
              onClick={() => onSet(l.id)}
              title={`${l.hint} Click to set this level by hand.`}
              aria-current={l.id === level ? 'step' : undefined}
              className={cn(
                'w-full rounded-md border px-3 py-2 text-left transition-colors',
                l.id === level
                  ? 'border-primary bg-primary/10 text-foreground'
                  : i < at
                    ? 'border-border bg-muted/60 text-muted-foreground'
                    : 'border-dashed border-border text-muted-foreground hover:bg-accent',
              )}
            >
              <span className="block text-small font-medium">{l.label}</span>
              <span className="block text-caption">{l.hint}</span>
            </button>
          </li>
        ))}
      </ol>
      {progress && (
        <p className="tnum mt-2 text-caption text-muted-foreground">
          {progress.next == null
            ? 'Top of the ladder. A daily loss halt, a losing streak or poor calibration demotes it.'
            : progress.locked
              ? `Promotion to ${progress.next.toLowerCase()} is locked: a human set this level as the ceiling.`
              : `Next: ${progress.next.toLowerCase()} after ${progress.need} graded ${level === 'SHADOW' ? 'shadow' : 'real'} contracts with Brier at most ${progress.max_brier?.toFixed(2)} and a positive net return. So far ${progress.have} of ${progress.need}${progress.brier != null ? `, Brier ${progress.brier.toFixed(2)}` : ''}, net ${progress.net_return_pct.toFixed(2)}%.`}
        </p>
      )}
    </div>
  );
}

function Meter({ label, used, text, warnAt = 0.7 }: { label: string; used: number; text: string; warnAt?: number }) {
  const v = Math.max(0, Math.min(1, used));
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-caption">
        <span className="text-muted-foreground">{label}</span>
        <span className="tnum font-medium">{text}</span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-muted" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v * 100)}>
        <div className={cn('h-full rounded-full transition-[width]', v >= 1 ? 'bg-destructive' : v >= warnAt ? 'bg-warning' : 'bg-primary')} style={{ width: `${v * 100}%` }} />
      </div>
    </div>
  );
}

/** Daily loss used, exposure, trades and positions against the kernel's hard limits. */
export function RiskBudget({ status }: { status: TraderStatus }) {
  const b = status.budget;
  if (!b) return null;
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Meter label="Daily loss budget used" used={b.daily_loss_used} text={`${frac(b.daily_pl_pct, 2, true)} of -${frac(b.daily_loss_limit_pct, 0)}`} />
      <Meter label="Gross exposure" used={b.exposure_pct / (b.max_gross_pct || 1)} text={`${frac(b.exposure_pct, 0)} of ${frac(b.max_gross_pct, 0)}`} warnAt={0.9} />
      <Meter label="Trades today" used={b.trades_today / (b.max_trades_per_day || 1)} text={`${b.trades_today} of ${b.max_trades_per_day}`} warnAt={0.8} />
      <Meter label="Open positions" used={b.open_positions / (b.max_open_positions || 1)} text={`${b.open_positions} of ${b.max_open_positions}`} warnAt={1.01} />
    </div>
  );
}

export function ControlBar({ status, onRedteam }: { status: TraderStatus; onRedteam: (r: RedteamResult) => void }) {
  const kill = useTraderAction(
    () => trader.kill('a human pressed the kill switch'),
    r => `Kill switch engaged: ${r.closed} position(s) closed`,
  );
  const resume = useTraderAction(
    () => trader.resume(),
    () => 'Kill switch released',
  );
  const start = useTraderAction(
    () => trader.start(),
    () => 'Autopilot started',
  );
  const stop = useTraderAction(
    () => trader.stop(),
    () => 'Autopilot loop stopped. Broker stops stay in place.',
  );
  const level = useTraderAction(
    (l: Autonomy) => trader.setAutonomy(l),
    r => `Autonomy set to ${r.autonomy.toLowerCase()}`,
  );
  const red = useTraderAction(
    () => trader.redteam(),
    r => {
      onRedteam(r);
      return null;
    },
  );

  const hb = status.heartbeat_age_seconds;
  const alive = status.running && hb != null && hb < 3 * 60 + (status.timeframe === '1Day' ? 86_400 : 0);
  return (
    <section className="surface overflow-hidden" aria-label="Autopilot controls">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 sm:px-6">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="success" className="font-mono">
            PAPER
          </Badge>
          <Badge variant={status.killed ? 'destructive' : status.halted ? 'warning' : alive ? 'success' : 'neutral'}>
            {status.killed ? 'Killed' : status.halted ? 'Halted' : alive ? 'Running' : status.running ? 'Starting' : 'Stopped'}
          </Badge>
          <span className="text-caption text-muted-foreground">
            {status.broker} broker, {status.brain} brain, {status.timeframe} bars{hb != null ? `, heartbeat ${Math.round(hb)}s ago` : ''}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {status.running ? (
            <Button size="sm" variant="secondary" disabled={stop.isPending} onClick={() => stop.mutate(undefined)}>
              <Square /> Stop loop
            </Button>
          ) : (
            <Button size="sm" variant="secondary" disabled={start.isPending} onClick={() => start.mutate(undefined)}>
              <Play /> Start
            </Button>
          )}
          <Button size="sm" variant="outline" disabled={red.isPending} onClick={() => red.mutate(undefined)} title="Send an absurd order and a poisoned headline at the agent">
            <ShieldAlert /> Red team
          </Button>
          {status.killed ? (
            <Button size="sm" disabled={resume.isPending} onClick={() => resume.mutate(undefined)}>
              <Undo2 /> Release kill switch
            </Button>
          ) : (
            <ConfirmButton
              title="Engage the kill switch?"
              description="Every open order is cancelled and every position is closed at market on the paper account. No new trades happen until a human releases the switch."
              confirmLabel="Kill and flatten"
              onConfirm={() => kill.mutate(undefined)}
            >
              <Button size="sm" variant="destructive" disabled={kill.isPending}>
                <OctagonX /> Kill switch
              </Button>
            </ConfirmButton>
          )}
        </div>
      </div>
      {(status.halted || status.last_error) && (
        <p role="status" className="border-t border-border bg-warning/10 px-5 py-2.5 text-small text-warning sm:px-6">
          {status.halted ? `Halted: ${status.halted}.` : `Last tick failed: ${status.last_error}`}
        </p>
      )}
      <div className="grid gap-6 border-t border-border px-5 py-4 sm:px-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-caption text-muted-foreground">Paper equity</p>
            <p className="tnum mt-1 text-h2">{money(status.account?.equity)}</p>
          </div>
          <div>
            <p className="text-caption text-muted-foreground">Buy-and-hold basket</p>
            <p className="tnum mt-1 text-h2 text-muted-foreground">{money(status.benchmark_value ?? null)}</p>
          </div>
        </div>
        {status.autonomy && <Ladder level={status.autonomy} progress={status.ladder} onSet={l => level.mutate(l)} busy={level.isPending} />}
      </div>
      <div className="border-t border-border px-5 py-4 sm:px-6">
        <RiskBudget status={status} />
      </div>
    </section>
  );
}
