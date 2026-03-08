import { useState, useCallback, useEffect } from 'react';
import axiomLogo from '@/assets/axiom-logo.png';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { TickerSelector } from '@/components/TickerSelector';
import { PriceChart } from '@/components/PriceChart';
import { SignalsPanel } from '@/components/SignalsPanel';
import { NewsPanel } from '@/components/NewsPanel';
import { BacktestTab } from '@/components/BacktestTab';
import { WatchlistTab } from '@/components/WatchlistTab';
import { PaperTradingTab } from '@/components/PaperTradingTab';
import { PredictionHistory } from '@/components/PredictionHistory';
import { OHLCVData } from '@/lib/stockData';
import { runPredictions, PredictionResult, getConfidenceGrade } from '@/lib/models';
import { generateSignal, SignalResult } from '@/lib/indicators';
import { NewsItem } from '@/lib/news';
import { addPredictionLog } from '@/lib/storage';
import { runBacktestFromData } from '@/lib/backtesting';
import { fetchStockData, fetchStockNews, convertToNewsItems, clearCache } from '@/lib/api';
import { Activity, BarChart3, Eye, LineChart, History, Briefcase, Trophy, Loader2, RefreshCw, Zap } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { motion, AnimatePresence } from 'framer-motion';

const Index = () => {
  const [ticker, setTicker] = useState('AAPL');
  const [data, setData] = useState<OHLCVData[]>([]);
  const [predictions, setPredictions] = useState<PredictionResult[] | null>(null);
  const [signal, setSignal] = useState<SignalResult | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [bestModel, setBestModel] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('predict');
  const { toast } = useToast();

  const loadData = useCallback(async (t: string) => {
    setIsLoading(true);
    setPredictions(null);
    setSignal(null);
    setBestModel(null);

    try {
      const [stockData, newsData] = await Promise.all([
        fetchStockData(t, 60),
        fetchStockNews(t),
      ]);
      setData(stockData);
      setNews(convertToNewsItems(newsData.news));
    } catch (err: any) {
      toast({ title: 'Data fetch error', description: err.message || 'Failed to load data', variant: 'destructive' });
      setData([]);
      setNews([]);
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  useEffect(() => { loadData(ticker); }, []);

  const handleTickerChange = useCallback((t: string) => {
    setTicker(t);
    loadData(t);
  }, [loadData]);

  const handleRefresh = useCallback(() => {
    clearCache(ticker);
    loadData(ticker);
  }, [ticker, loadData]);

  const handleRunPrediction = useCallback(() => {
    if (data.length < 20) {
      toast({ title: 'Not enough data', description: 'Need at least 20 data points', variant: 'destructive' });
      return;
    }
    setIsRunning(true);
    setTimeout(() => {
      const preds = runPredictions(data, 14);
      setPredictions(preds);
      const sig = generateSignal(data, {
        lstm: preds[0].predictions,
        prophet: preds[1].predictions,
        xgboost: preds[2].predictions,
      });
      setSignal(sig);
      const backtestResults = runBacktestFromData(data);
      if (backtestResults.length > 0) {
        const best = backtestResults.reduce((b, r) => r.rmse < b.rmse ? r : b, backtestResults[0]);
        setBestModel(best.model);
      }
      addPredictionLog({
        ticker,
        date: new Date().toISOString().split('T')[0],
        targetDate: preds[0].dates[preds[0].dates.length - 1],
        predictions: preds.map(p => ({ model: p.model, price: p.predictions[p.predictions.length - 1] })),
      });
      setIsRunning(false);
    }, 800);
  }, [data, ticker, toast]);

  const lastPrice = data[data.length - 1]?.close || 0;
  const prevPrice = data[data.length - 2]?.close || lastPrice;
  const dayChange = lastPrice - prevPrice;
  const dayChangePct = prevPrice ? (dayChange / prevPrice) * 100 : 0;

  return (
    <div className="min-h-screen bg-background terminal-grid">
      {/* Header */}
      <header className="sticky top-0 z-50 glass border-b border-border/50">
        <div className="max-w-[1400px] mx-auto flex items-center justify-between px-6 py-3">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2.5">
              <div className="relative">
                <img src={axiomLogo} alt="Axiom Logo" className="h-8 w-8" />
              </div>
              <h1 className="text-xl font-bold font-display tracking-tight gradient-text">AXIOM</h1>
            </div>
            <div className="hidden sm:flex items-center gap-2">
              <div className="w-px h-5 bg-border" />
              <span className="text-[11px] text-muted-foreground font-mono uppercase tracking-widest">Predictive Analytics</span>
            </div>
            <Badge className="font-mono text-[10px] bg-success/10 text-success border-success/20 hover:bg-success/10">
              <span className="w-1.5 h-1.5 bg-success rounded-full mr-1.5 pulse-dot inline-block" />
              LIVE
            </Badge>
          </div>

          <div className="flex items-center gap-4">
            <Button variant="ghost" size="icon" onClick={handleRefresh} className="h-8 w-8 text-muted-foreground hover:text-foreground">
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
            {isLoading ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="font-mono text-xs">Loading...</span>
              </div>
            ) : (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-right">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-sm font-semibold text-muted-foreground">{ticker}</span>
                  <span className="font-mono text-xl font-bold">${lastPrice.toFixed(2)}</span>
                </div>
                <div className={`font-mono text-xs font-medium ${dayChange >= 0 ? 'text-success' : 'text-destructive'}`}>
                  {dayChange >= 0 ? '↑' : '↓'} {dayChange >= 0 ? '+' : ''}{dayChange.toFixed(2)} ({dayChangePct.toFixed(2)}%)
                </div>
              </motion.div>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-6 py-5">
        {/* Ticker Selector */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-5">
          <TickerSelector selected={ticker} onSelect={handleTickerChange} />
        </motion.div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="font-mono mb-5 bg-muted/50 glass p-1 h-auto gap-1 rounded-xl border border-border/50">
            {[
              { value: 'predict', icon: LineChart, label: 'PREDICT' },
              { value: 'backtest', icon: BarChart3, label: 'BACKTEST' },
              { value: 'watchlist', icon: Eye, label: 'WATCHLIST' },
              { value: 'trading', icon: Briefcase, label: 'PAPER TRADE' },
              { value: 'history', icon: History, label: 'HISTORY' },
            ].map(tab => (
              <TabsTrigger
                key={tab.value}
                value={tab.value}
                className="font-mono text-[11px] gap-1.5 rounded-lg px-4 py-2 data-[state=active]:bg-primary/10 data-[state=active]:text-primary data-[state=active]:shadow-none transition-all duration-200"
              >
                <tab.icon className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">{tab.label}</span>
              </TabsTrigger>
            ))}
          </TabsList>

          <AnimatePresence mode="wait">
            <TabsContent value="predict" key="predict">
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className={`grid grid-cols-1 gap-5 transition-all duration-700 ease-in-out ${predictions ? 'lg:grid-cols-3' : 'lg:grid-cols-1'}`}
              >
                <motion.div layout transition={{ duration: 0.6, ease: [0.4, 0, 0.2, 1] }} className={`space-y-5 ${predictions ? 'lg:col-span-2' : 'lg:col-span-1'}`}>
                  {/* Chart Card */}
                  <motion.div layout transition={{ duration: 0.6, ease: [0.4, 0, 0.2, 1] }} className="glass-card rounded-xl overflow-hidden">
                    <div className="flex items-center justify-between px-5 py-4 border-b border-border/50">
                      <div>
                        <h2 className="text-sm font-semibold font-display">
                          {ticker} <span className="text-muted-foreground font-normal">—</span>{' '}
                          <span className="text-muted-foreground font-normal text-xs">
                            {isLoading ? 'Loading...' : `${data.length} Day History`}
                            {predictions ? ' + 14 Day Forecast' : ''}
                          </span>
                        </h2>
                      </div>
                      <Button
                        onClick={handleRunPrediction}
                        disabled={isRunning || isLoading || data.length === 0}
                        size="sm"
                        className="font-mono text-xs gap-1.5 bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 hover:text-primary shadow-none"
                      >
                        {isRunning ? (
                          <><Loader2 className="h-3 w-3 animate-spin" /> ANALYZING...</>
                        ) : (
                          <><Zap className="h-3 w-3" /> RUN PREDICTION</>
                        )}
                      </Button>
                    </div>
                    <div className="p-4">
                      {isLoading ? (
                        <div className="flex flex-col items-center justify-center h-[400px] gap-3">
                          <Loader2 className="h-8 w-8 animate-spin text-primary/50" />
                          <span className="text-xs text-muted-foreground font-mono">Fetching market data...</span>
                        </div>
                      ) : data.length > 0 ? (
                        <PriceChart data={data} predictions={predictions || undefined} newsItems={news} />
                      ) : (
                        <div className="flex items-center justify-center h-[400px] text-muted-foreground font-mono text-sm">
                          No data available for {ticker}
                        </div>
                      )}
                    </div>
                  </motion.div>

                  {/* Model Cards */}
                  <AnimatePresence>
                    {predictions && (
                      <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4, delay: 0.2 }}
                        className="grid grid-cols-3 gap-3"
                      >
                        {predictions.map((p, idx) => {
                          const finalPrice = p.predictions[p.predictions.length - 1];
                          const change = ((finalPrice - lastPrice) / lastPrice) * 100;
                          const isBest = p.model === bestModel;
                          return (
                            <motion.div
                              key={p.model}
                              initial={{ opacity: 0, y: 12 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{ delay: 0.25 + idx * 0.1, duration: 0.35 }}
                              className={`stat-card ${isBest ? 'glow-primary gradient-border' : ''}`}
                            >
                              <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
                                  <span className="font-mono text-[11px] font-semibold text-muted-foreground uppercase">{p.model}</span>
                                </div>
                                {isBest && <Trophy className="h-3.5 w-3.5 text-primary" />}
                              </div>
                              <div className="font-mono text-xl font-bold tracking-tight">${finalPrice.toFixed(2)}</div>
                              <div className={`font-mono text-xs font-medium mt-1 ${change >= 0 ? 'text-success' : 'text-destructive'}`}>
                                {change >= 0 ? '↑' : '↓'} {change >= 0 ? '+' : ''}{change.toFixed(2)}%
                              </div>
                              {isBest && (
                                <Badge className="mt-2.5 font-mono text-[10px] bg-primary/10 text-primary border-primary/20 hover:bg-primary/10">
                                  BEST MODEL
                                </Badge>
                              )}
                            </motion.div>
                          );
                        })}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>

                {/* Right sidebar - slides in when predictions are ready */}
                <AnimatePresence>
                  {predictions ? (
                    <motion.div
                      initial={{ opacity: 0, y: 16 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 16 }}
                      transition={{ duration: 0.4, delay: 0.1 }}
                      className="space-y-5"
                    >
                      <SignalsPanel signal={signal} />
                      <motion.div
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ duration: 0.4, delay: 0.4 }}
                        className="glass-card rounded-xl p-5"
                      >
                        <div className="text-[11px] text-muted-foreground font-mono uppercase tracking-wider mb-2">Model Confidence</div>
                        <div className="font-mono text-4xl font-bold gradient-text">
                          {getConfidenceGrade(predictions)}
                        </div>
                        <div className="text-xs text-muted-foreground mt-2">Agreement grade across all models</div>
                      </motion.div>
                      <NewsPanel news={news} />
                    </motion.div>
                  ) : (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="lg:col-span-1"
                    >
                      <NewsPanel news={news} />
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            </TabsContent>
          </AnimatePresence>

          <TabsContent value="backtest">
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
              <BacktestTab ticker={ticker} />
            </motion.div>
          </TabsContent>

          <TabsContent value="watchlist">
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
              <WatchlistTab onSelectTicker={(t) => { handleTickerChange(t); setActiveTab('predict'); }} />
            </motion.div>
          </TabsContent>

          <TabsContent value="trading">
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
              <PaperTradingTab ticker={ticker} />
            </motion.div>
          </TabsContent>

          <TabsContent value="history">
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
              <PredictionHistory />
            </motion.div>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
};

export default Index;
