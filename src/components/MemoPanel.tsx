import { Fragment, useState } from 'react';
import { Check, ChevronDown, Copy, ScrollText, TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { DefList } from '@/components/kit/DefList';
import { useToast } from '@/hooks/use-toast';
import { frac, money, ratingLabel, ratingTone, TONE_BG, TONE_TEXT } from '@/lib/format';
import type { AnalysisResult, Claim, Finding } from '@/lib/types';
import { cn } from '@/lib/utils';

const STANCE_VARIANT = { bullish: 'success', bearish: 'destructive', neutral: 'neutral', insufficient_data: 'warning' } as const;

/** A citation: a small, quiet reference that opens the tool result the number came from. */
export function CitationChip({ id, result }: { id: string; result: Pick<AnalysisResult, 'evidence'> }) {
  const ev = result.evidence[id];
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="mx-0.5 inline-flex h-[1.125rem] items-center rounded-sm border border-border bg-muted px-1.5 align-baseline font-mono text-caption text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary"
          aria-label={`Evidence ${id}${ev ? `: ${ev.tool}` : ''}`}
        >
          {id}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[22rem] space-y-2.5 text-small" align="start">
        {ev ? (
          <>
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-mono font-medium text-primary">{ev.tool}</span>
              <span className="text-caption text-muted-foreground">{[ev.as_of, ev.provider].filter(Boolean).join(', ')}</span>
            </div>
            <p className="font-mono text-caption text-muted-foreground">{JSON.stringify(ev.args)}</p>
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-sm bg-muted p-2.5 font-mono text-caption leading-relaxed">{ev.excerpt}</pre>
          </>
        ) : (
          <span className="text-destructive">Unknown evidence id {id}</span>
        )}
      </PopoverContent>
    </Popover>
  );
}

export function ClaimList({ claims, result }: { claims: Claim[]; result: Pick<AnalysisResult, 'evidence'> }) {
  return (
    <ul className="space-y-2">
      {claims.map((c, i) => (
        <li key={i} className="relative pl-4 text-small leading-relaxed before:absolute before:left-0 before:top-[0.6em] before:h-1 before:w-1 before:rounded-full before:bg-muted-foreground/50">
          {c.text}
          {c.evidence.map(id => (
            <CitationChip key={id} id={id} result={result} />
          ))}
        </li>
      ))}
    </ul>
  );
}

const Block = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="border-t border-border px-5 py-4 sm:px-6">
    <h3 className="mb-2.5 text-small font-semibold">{title}</h3>
    {children}
  </div>
);

function Analyst({ f }: { f: Finding }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5">
      <div className="min-w-0">
        <p className="text-small font-medium">{f.agent}</p>
        <p className="mt-0.5 text-caption leading-relaxed text-muted-foreground">{f.summary}</p>
      </div>
      <div className="shrink-0 text-right">
        <Badge variant={STANCE_VARIANT[f.stance]}>{f.stance.replace('_', ' ')}</Badge>
        <p className="tnum mt-1 text-caption text-muted-foreground">{frac(f.confidence, 0)}</p>
      </div>
    </div>
  );
}

interface Props {
  result: AnalysisResult;
  onOpenTrace?: () => void;
}

export function MemoPanel({ result, onOpenTrace }: Props) {
  const { memo, position, findings } = result;
  const tone = ratingTone(memo.rating);
  const { toast } = useToast();
  const [copied, setCopied] = useState(false);
  const evidenceIds = Object.keys(result.evidence);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(result.markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      toast({ title: 'Could not copy', description: 'Clipboard access was blocked by the browser.', variant: 'destructive' });
    }
  };

  const plan =
    position.action === 'open_long'
      ? [
          { label: 'Action', value: 'Open a long position (paper)' },
          { label: 'Shares', value: position.shares.toLocaleString() },
          { label: 'Entry reference', value: money(position.entry_reference) },
          { label: 'Stop', value: money(position.stop_price) },
          { label: 'Capital at risk', value: money(position.risk_amount) },
          { label: 'Share of equity', value: frac(position.position_pct, 1) },
        ]
      : [{ label: 'Action', value: position.action === 'avoid' ? 'Avoid or exit' : 'No position proposed' }];

  return (
    <article className="surface overflow-hidden" aria-label={`${memo.ticker} memo`}>
      <div className="px-5 pb-5 pt-5 sm:px-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-caption text-muted-foreground">{memo.ticker} rating</p>
            <p className={cn('mt-0.5 text-h1', TONE_TEXT[tone])}>{ratingLabel(memo.rating)}</p>
          </div>
          <div className="flex items-center gap-1">
            {onOpenTrace && (
              <Button variant="ghost" size="icon-sm" onClick={onOpenTrace} aria-label="Open the agent trace">
                <ScrollText />
              </Button>
            )}
            <Button variant="ghost" size="icon-sm" onClick={copy} aria-label="Copy memo as Markdown">
              {copied ? <Check className="text-success" /> : <Copy />}
            </Button>
          </div>
        </div>

        <div className="mt-4" role="meter" aria-label="Conviction" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(memo.conviction * 100)}>
          <div className="h-1 overflow-hidden rounded-full bg-muted">
            <div className={cn('h-full rounded-full', TONE_BG[tone])} style={{ width: `${Math.max(2, memo.conviction * 100)}%` }} />
          </div>
          <p className="tnum mt-2 text-caption text-muted-foreground">
            {frac(memo.conviction, 0)} conviction over {memo.horizon_days} days. {result.usage.tokens?.toLocaleString() ?? 'n/a'} tokens across {result.usage.calls ?? 'n/a'} model calls.
          </p>
        </div>

        {result.degraded.length > 0 && (
          <div className="mt-4 flex gap-2 rounded-md bg-warning/10 p-3 text-caption text-warning" role="status">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{result.degraded.join(' ')}</span>
          </div>
        )}

        <p className="mt-5 max-w-[65ch] text-body leading-relaxed">{memo.thesis}</p>
      </div>

      <Block title="Bull case">
        <ClaimList claims={memo.bull_case} result={result} />
      </Block>
      <Block title="Bear case">
        <ClaimList claims={memo.bear_case} result={result} />
      </Block>
      <Block title="Key risks">
        <ul className="space-y-1.5 text-small leading-relaxed">
          {memo.key_risks.map(r => (
            <li key={r} className="relative pl-4 before:absolute before:left-0 before:top-[0.6em] before:h-1 before:w-1 before:rounded-full before:bg-muted-foreground/50">
              {r}
            </li>
          ))}
        </ul>
        {memo.what_would_change_my_mind.length > 0 && (
          <Fragment>
            <h3 className="mb-2 mt-5 text-small font-semibold">What would change this view</h3>
            <ul className="space-y-1.5 text-small leading-relaxed text-muted-foreground">
              {memo.what_would_change_my_mind.map(r => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </Fragment>
        )}
      </Block>
      <Block title="Position plan (paper)">
        <DefList items={plan} />
        {[...position.notes, ...position.violations].map(n => (
          <p key={n} className="mt-2 text-caption text-muted-foreground">
            {n}
          </p>
        ))}
      </Block>
      <Block title="Analysts">
        <div className="-my-2.5 divide-y divide-border">
          {findings.map(f => (
            <Analyst key={f.agent} f={f} />
          ))}
        </div>
      </Block>

      <details className="group border-t border-border">
        <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-3.5 text-small font-semibold sm:px-6">
          Evidence, {evidenceIds.length} sources
          <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
        </summary>
        <ul className="divide-y divide-border border-t border-border">
          {evidenceIds.map(id => {
            const e = result.evidence[id];
            return (
              <li key={id} className="grid grid-cols-[3.25rem_1fr_auto] items-center gap-3 px-5 py-2 text-caption sm:px-6">
                <CitationChip id={id} result={result} />
                <span className="truncate font-mono">{e.tool}</span>
                <span className="tnum text-muted-foreground">{[e.as_of, e.provider].filter(Boolean).join(', ')}</span>
              </li>
            );
          })}
        </ul>
      </details>
      {(result.guardrails.length > 0 || memo.prior_theses_addressed) && (
        <details className="group border-t border-border">
          <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-3.5 text-small font-semibold sm:px-6">
            Checks applied, {result.guardrails.length}
            <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
          </summary>
          <ul className="space-y-1.5 border-t border-border px-5 py-3 text-caption text-muted-foreground sm:px-6">
            {result.guardrails.map(g => (
              <li key={g}>{g}</li>
            ))}
            {memo.prior_theses_addressed && <li>{memo.prior_theses_addressed}</li>}
          </ul>
        </details>
      )}
      <p className="border-t border-border px-5 py-3 text-caption text-muted-foreground sm:px-6">
        Research tooling, not financial advice. Daily bars and public filings only. Past results and backtests do not predict future returns.
      </p>
    </article>
  );
}
