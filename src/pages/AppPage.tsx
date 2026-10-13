import { Suspense, lazy, useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BarChart3, Briefcase, Eye, FlaskConical, Loader2, ScrollText, Target } from 'lucide-react';
import { AgentPanel } from '@/components/AgentPanel';
import { AgentTraceDrawer } from '@/components/AgentTraceDrawer';
import { IndicatorPanel } from '@/components/IndicatorPanel';
import { NewsPanel } from '@/components/NewsPanel';
import { PriceChart } from '@/components/PriceChart';
import { Segmented, type SegmentedOption } from '@/components/kit/Segmented';
import { SkeletonBlock } from '@/components/kit/Skeleton';
import { Section } from '@/components/kit/Surface';
import { AppHeader } from '@/components/shell/AppHeader';
import { QuoteStrip } from '@/components/shell/QuoteStrip';
import { Badge } from '@/components/ui/badge';
import { useAgentStream } from '@/hooks/useAgentStream';
import { useToast } from '@/hooks/use-toast';
import { api, ApiError, clearCache } from '@/lib/api';
import { pushRecent } from '@/lib/recent';
import { cn } from '@/lib/utils';

// Tabs other than Analyze load on demand so the first paint stays small.
const named = <K extends string>(load: () => Promise<Record<K, React.ComponentType<never>>>, key: K) =>
  lazy(() => load().then(m => ({ default: m[key] as React.ComponentType<Record<string, unknown>> })));
const BacktestTab = named(() => import('@/components/BacktestTab'), 'BacktestTab');
const WatchlistTab = named(() => import('@/components/WatchlistTab'), 'WatchlistTab');
const PaperTradingTab = named(() => import('@/components/PaperTradingTab'), 'PaperTradingTab');
const ScorecardTab = named(() => import('@/components/ScorecardTab'), 'ScorecardTab');
const ActionsTab = named(() => import('@/components/ActionsTab'), 'ActionsTab');

type TabId = 'analyze' | 'backtest' | 'watchlist' | 'trading' | 'scorecard' | 'actions';
const TAB_IDS: TabId[] = ['analyze', 'backtest', 'watchlist', 'trading', 'scorecard', 'actions'];

const TabFallback = () => (
  <div className="flex justify-center py-20" role="status" aria-label="Loading">
    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
  </div>
);

export default function AppPage() {
  const [params, setParams] = useSearchParams();
  const ticker = (params.get('t') ?? 'AAPL').toUpperCase();
  const tab = (TAB_IDS.includes(params.get('tab') as TabId) ? params.get('tab') : 'analyze') as TabId;
  const [traceOpen, setTraceOpen] = useState(false);
  const qc = useQueryClient();
  const { toast } = useToast();
  const stream = useAgentStream();

  const setTicker = useCallback(
    (t: string) => {
      stream.reset();
      pushRecent(t);
      setParams(p => {
        const n = new URLSearchParams(p);
        n.set('t', t);
        return n;
      });
    },
    [setParams, stream],
  );
  const setTab = (id: TabId) =>
    setParams(p => {
      const n = new URLSearchParams(p);
      if (id === 'analyze') n.delete('tab');
      else n.set('tab', id);
      return n;
    });

  useEffect(() => {
    pushRecent(ticker);
    document.title = `${ticker} | Axiom`;
  }, [ticker]);

  const health = useQuery({ queryKey: ['health'], queryFn: api.health, retry: false, refetchInterval: 60_000 });
  const bars = useQuery({ queryKey: ['bars', ticker], queryFn: () => api.ohlcv(ticker, 90), retry: false });
  const indicators = useQuery({ queryKey: ['indicators', ticker], queryFn: () => api.indicators(ticker), retry: false });
  const regime = useQuery({ queryKey: ['regime', ticker], queryFn: () => api.regime(ticker), retry: false });
  const forecast = useQuery({ queryKey: ['forecast', ticker], queryFn: () => api.forecast(ticker, 14), retry: false });
  const news = useQuery({ queryKey: ['news', ticker], queryFn: () => api.news(ticker), retry: false });
  const watchlist = useQuery({ queryKey: ['watchlist'], queryFn: api.watchlist, retry: false });
  const actions = useQuery({ queryKey: ['actions'], queryFn: api.actions, retry: false, refetchInterval: 20_000 });

  const watched = (watchlist.data ?? []).some(w => w.ticker === ticker);
  const toggleWatch = useMutation({
    mutationFn: () => (watched ? api.watchRemove(ticker) : api.watchAdd(ticker)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
    onError: (e: unknown) =>
      toast({ title: e instanceof ApiError && e.status === 401 ? 'API token required' : 'Could not update watchlist', description: e instanceof Error ? e.message : 'Unknown error', variant: 'destructive' }),
  });

  const result = stream.result && stream.result.ticker === ticker ? stream.result : null;
  const running = stream.status === 'running' || stream.status === 'queued';

  useEffect(() => {
    if (stream.status === 'done') for (const k of ['theses', 'scorecard', 'actions']) qc.invalidateQueries({ queryKey: [k] });
  }, [stream.status, qc]);

  const list = bars.data?.bars ?? [];
  const last = list[list.length - 1]?.close;
  const prev = list[list.length - 2]?.close;
  const change = last != null && prev != null ? last - prev : 0;
  const changePct = prev ? (change / prev) * 100 : 0;
  const offline = health.isError;
  const cone = forecast.data?.cone;
  const pendingActions = (actions.data ?? []).filter(a => a.status === 'proposed').length;

  const refresh = () => {
    clearCache(ticker);
    for (const k of ['bars', 'indicators', 'regime', 'forecast', 'news']) qc.invalidateQueries({ queryKey: [k, ticker] });
  };
  const run = () => {
    setTraceOpen(false);
    stream.start(ticker);
  };

  const tabs: SegmentedOption<TabId>[] = [
    { value: 'analyze', label: 'Analyze', icon: FlaskConical },
    { value: 'backtest', label: 'Backtest', icon: BarChart3 },
    { value: 'watchlist', label: 'Watchlist', icon: Eye },
    { value: 'trading', label: 'Paper trade', icon: Briefcase },
    { value: 'scorecard', label: 'Scorecard', icon: Target },
    { value: 'actions', label: 'Actions', icon: ScrollText, badge: pendingActions || undefined },
  ];

  return (
    <div className="min-h-[100dvh] bg-background">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:shadow-md">
        Skip to content
      </a>
      <AppHeader ticker={ticker} onTicker={setTicker} health={health.data} offline={offline} />

      <main id="main" className="mx-auto max-w-[1280px] px-4 pb-24 sm:px-6">
        {offline && (
          <div role="alert" className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-small text-destructive">
            The backend is not reachable, so there is no market data or analysis. Open the status menu for how to start it.
          </div>
        )}

        <QuoteStrip
          ticker={ticker}
          loading={bars.isLoading}
          last={last}
          change={change}
          changePct={changePct}
          asOf={list[list.length - 1]?.date}
          provider={bars.data?.provider}
          watched={watched}
          onToggleWatch={() => toggleWatch.mutate()}
          onRefresh={refresh}
          running={running}
          canRun={!bars.isLoading && list.length > 0 && !offline}
          onRun={run}
          onCancel={stream.cancel}
        />

        <nav aria-label="Sections" className="-mx-4 mb-6 overflow-x-auto px-4 sm:mx-0 sm:px-0 [scrollbar-width:none]">
          <Segmented options={tabs} value={tab} onChange={setTab} ariaLabel="Sections" scroll />
        </nav>

        {tab === 'analyze' && (
          <div className="grid items-start gap-6 lg:grid-cols-12">
            <div className="space-y-6 lg:col-span-8">
              <Section
                title="Price and 14-day range"
                description={cone ? 'The shaded band is a zero-drift range, not a forecast' : '90 trading days'}
                actions={
                  forecast.data?.calibration?.empirical_coverage != null && (
                    <Badge variant={forecast.data.calibration.well_calibrated ? 'success' : 'warning'}>
                      {`Range held ${Math.round(forecast.data.calibration.empirical_coverage * 100)}% of the time`}
                    </Badge>
                  )
                }
              >
                <div className="border-t border-border px-2 pb-3 pt-4 sm:px-4">
                  {bars.isLoading ? (
                    <SkeletonBlock className="mx-3 h-[340px]" />
                  ) : list.length > 0 ? (
                    <PriceChart bars={list} cone={cone} />
                  ) : (
                    <div className="flex h-[340px] items-center justify-center px-6 text-center text-small text-muted-foreground">
                      {bars.error ? (bars.error as Error).message : `No data available for ${ticker}`}
                    </div>
                  )}
                </div>
                {forecast.data?.calibration && cone && (
                  <p className="border-t border-border px-5 py-3 text-caption text-muted-foreground sm:px-6">
                    Walk-forward check: the {Math.round(forecast.data.calibration.nominal_coverage * 100)}% band contained the realised price{' '}
                    {Math.round((forecast.data.calibration.empirical_coverage ?? 0) * 100)}% of the time across {forecast.data.calibration.n_checks} overlapping tests.
                  </p>
                )}
              </Section>
              <IndicatorPanel indicators={indicators.data ?? null} regime={regime.data ?? null} loading={indicators.isLoading} />
              <NewsPanel news={news.data ?? null} loading={news.isLoading} />
            </div>

            <div className={cn('space-y-4 lg:col-span-4', !result && 'lg:sticky lg:top-20')}>
              <AgentPanel status={stream.status} events={stream.events} result={result} error={stream.error} onOpenTrace={() => setTraceOpen(true)} />
              {result?.action && (
                <div className="surface-quiet px-5 py-4 text-small">
                  <p className="font-medium">Action plan proposed</p>
                  <p className="mt-0.5 text-muted-foreground">Nothing runs until you approve it.</p>
                  <button className="mt-2 text-small font-medium text-primary hover:underline" onClick={() => setTab('actions')}>
                    Review in Actions
                  </button>
                </div>
              )}
              {result && !result.action && result.action_reason && <p className="px-1 text-caption text-muted-foreground">{result.action_reason}</p>}
            </div>
          </div>
        )}

        <Suspense fallback={<TabFallback />}>
          {tab === 'backtest' && <BacktestTab ticker={ticker} />}
          {tab === 'watchlist' && <WatchlistTab onSelectTicker={(t: string) => { setTicker(t); setTab('analyze'); }} />}
          {tab === 'trading' && <PaperTradingTab ticker={ticker} />}
          {tab === 'scorecard' && <ScorecardTab />}
          {tab === 'actions' && <ActionsTab />}
        </Suspense>
      </main>

      <AgentTraceDrawer open={traceOpen} onOpenChange={setTraceOpen} events={stream.events} status={stream.status} error={stream.error} />
    </div>
  );
}
