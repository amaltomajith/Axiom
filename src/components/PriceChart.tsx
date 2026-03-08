import { useState, useEffect, useRef } from 'react';
import { OHLCVData } from '@/lib/stockData';
import { PredictionResult } from '@/lib/models';
import { NewsItem } from '@/lib/news';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceDot,
  Legend,
  Customized,
} from 'recharts';

interface PriceChartProps {
  data: OHLCVData[];
  predictions?: PredictionResult[];
  newsItems?: NewsItem[];
  height?: number;
}

export function PriceChart({ data, predictions, newsItems, height = 400 }: PriceChartProps) {
  const [animKey, setAnimKey] = useState(0);
  const prevPredRef = useRef<PredictionResult[] | undefined>(undefined);

  // Trigger re-animation when predictions change
  useEffect(() => {
    if (predictions && predictions !== prevPredRef.current) {
      setAnimKey(k => k + 1);
    }
    prevPredRef.current = predictions;
  }, [predictions]);
  const chartData = data.map(d => ({
    date: d.date,
    price: d.close,
  }));

  if (predictions?.length) {
    predictions.forEach(pred => {
      pred.dates.forEach((date, i) => {
        let existing = chartData.find(c => c.date === date);
        if (!existing) {
          existing = { date } as any;
          chartData.push(existing);
        }
        (existing as any)[pred.model] = pred.predictions[i];
      });
    });
  }

  chartData.sort((a, b) => a.date.localeCompare(b.date));

  const sentimentMarkers = newsItems?.map(n => {
    const point = chartData.find(c => c.date === n.date);
    if (!point) return null;
    return { date: n.date, price: (point as any).price, sentiment: n.sentiment };
  }).filter(Boolean) || [];

  const allValues = chartData.flatMap(d => {
    const vals = [(d as any).price].filter(Boolean);
    predictions?.forEach(p => {
      const v = (d as any)[p.model];
      if (v) vals.push(v);
    });
    return vals;
  });
  const minVal = Math.min(...allValues) * 0.98;
  const maxVal = Math.max(...allValues) * 1.02;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
        <defs>
          <linearGradient id="priceGradient" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="hsl(168, 80%, 48%)" />
            <stop offset="100%" stopColor="hsl(200, 80%, 50%)" />
          </linearGradient>
          <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(168, 80%, 48%)" stopOpacity={0.15} />
            <stop offset="100%" stopColor="hsl(168, 80%, 48%)" stopOpacity={0} />
          </linearGradient>
          {predictions && (
            <clipPath id={`forecast-reveal-${animKey}`}>
              <rect x="0" y="0" width="0" height="100%">
                <animate
                  attributeName="width"
                  from="0%"
                  to="100%"
                  dur="1.8s"
                  begin="0.2s"
                  fill="freeze"
                  calcMode="spline"
                  keySplines="0.25 0.1 0.25 1"
                  keyTimes="0;1"
                />
              </rect>
            </clipPath>
          )}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(225, 15%, 10%)" />
        <XAxis
          dataKey="date"
          tick={{ fill: 'hsl(220, 12%, 40%)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          tickFormatter={v => v.slice(5)}
          stroke="hsl(225, 15%, 10%)"
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          domain={[minVal, maxVal]}
          tick={{ fill: 'hsl(220, 12%, 40%)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          stroke="hsl(225, 15%, 10%)"
          tickFormatter={v => `$${v.toFixed(0)}`}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'hsl(225, 20%, 6%)',
            border: '1px solid hsl(225, 15%, 14%)',
            borderRadius: '10px',
            fontSize: 11,
            fontFamily: 'JetBrains Mono',
            boxShadow: '0 8px 32px -8px hsl(225, 25%, 0%, 0.8)',
          }}
          labelStyle={{ color: 'hsl(210, 20%, 70%)' }}
          cursor={{ stroke: 'hsl(168, 80%, 48%)', strokeWidth: 1, strokeDasharray: '4 4' }}
        />
        <Legend
          wrapperStyle={{ fontSize: 10, fontFamily: 'JetBrains Mono', paddingTop: '12px' }}
          iconType="circle"
          iconSize={6}
        />
        <Line
          type="monotone"
          dataKey="price"
          stroke="url(#priceGradient)"
          strokeWidth={2.5}
          dot={false}
          name="Historical"
          activeDot={{ r: 4, fill: 'hsl(168, 80%, 48%)', stroke: 'hsl(225, 20%, 6%)', strokeWidth: 2 }}
          isAnimationActive={true}
          animationDuration={1200}
          animationEasing="ease-in-out"
        />
        {predictions?.map((pred, idx) => (
          <Line
            key={`${pred.model}-${animKey}`}
            type="monotone"
            dataKey={pred.model}
            stroke={pred.color}
            strokeWidth={2}
            strokeDasharray="6 3"
            dot={false}
            name={`${pred.model} Forecast`}
            connectNulls={false}
            isAnimationActive={false}
            clipPath={`url(#forecast-reveal-${animKey})`}
          />
        ))}
        {sentimentMarkers.map((m: any, i) => (
          <ReferenceDot
            key={i}
            x={m.date}
            y={m.price}
            r={4}
            fill={m.sentiment === 'Positive' ? 'hsl(152, 70%, 48%)' : m.sentiment === 'Negative' ? 'hsl(0, 75%, 55%)' : 'hsl(42, 95%, 55%)'}
            stroke="hsl(225, 20%, 6%)"
            strokeWidth={2}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
