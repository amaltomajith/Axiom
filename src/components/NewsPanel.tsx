import { NewsItem, getNetSentiment } from '@/lib/news';
import { Badge } from '@/components/ui/badge';
import { ExternalLink } from 'lucide-react';

interface NewsPanelProps {
  news: NewsItem[];
}

export function NewsPanel({ news }: NewsPanelProps) {
  if (news.length === 0) return null;
  const net = getNetSentiment(news);

  const sentimentConfig = {
    Bullish: 'bg-success/10 text-success border-success/20',
    Bearish: 'bg-destructive/10 text-destructive border-destructive/20',
    Neutral: 'bg-muted text-muted-foreground border-border',
  };

  return (
    <div className="glass-card rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-border/50">
        <h3 className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground font-semibold">News Sentiment</h3>
        <Badge className={`font-mono text-[10px] border ${sentimentConfig[net.label as keyof typeof sentimentConfig]} hover:opacity-100`}>
          {net.label} ({net.score > 0 ? '+' : ''}{net.score})
        </Badge>
      </div>
      <div className="divide-y divide-border/30">
        {news.map(n => (
          <div key={n.id} className="flex items-start gap-3 px-5 py-3 hover:bg-muted/20 transition-colors group">
            <div className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${
              n.sentiment === 'Positive' ? 'bg-success' :
              n.sentiment === 'Negative' ? 'bg-destructive' : 'bg-warning'
            }`} />
            <div className="min-w-0 flex-1">
              <p className="text-xs leading-relaxed group-hover:text-foreground transition-colors">{n.headline}</p>
              <div className="flex items-center gap-2 mt-1.5">
                <span className="text-[10px] text-muted-foreground font-mono">{n.source}</span>
                <span className="text-[10px] text-muted-foreground/50">·</span>
                <span className="text-[10px] text-muted-foreground font-mono">{n.date}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
