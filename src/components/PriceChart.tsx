import { useMemo } from 'react';
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useChartTheme } from '@/hooks/useChartTheme';
import { buildChartRows, yDomain } from '@/lib/cone';
import { money } from '@/lib/format';
import type { Bar, ConeStep } from '@/lib/types';

interface PriceChartProps {
  bars: Bar[];
  cone?: ConeStep[];
  height?: number;
  /** draw the price line in once (landing page only; the app never animates data it just loaded) */
  animate?: boolean;
}

/** Price with an optional zero-drift uncertainty cone. All colours come from the active theme's tokens. */
export function PriceChart({ bars, cone, height = 340, animate = false }: PriceChartProps) {
  const t = useChartTheme();
  const rows = useMemo(() => buildChartRows(bars, cone), [bars, cone]);
  const domain = useMemo(() => yDomain(rows), [rows]);
  const lastDate = bars[bars.length - 1]?.date;
  const tick = { fill: t.axis, fontSize: 12, fontFamily: t.mono };

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={t.grid} vertical={false} />
        <XAxis dataKey="date" tick={tick} tickFormatter={(v: string) => v.slice(5)} tickLine={false} axisLine={false} minTickGap={36} tickMargin={8} />
        <YAxis domain={domain} tick={tick} tickFormatter={(v: number) => `$${v.toFixed(0)}`} tickLine={false} axisLine={false} width={52} orientation="right" />
        <Tooltip
          cursor={{ stroke: t.axis, strokeDasharray: '3 3' }}
          contentStyle={{ background: t.surface, border: `1px solid ${t.border}`, borderRadius: 10, fontSize: 12, fontFamily: t.mono, color: t.text, boxShadow: 'var(--shadow-md)' }}
          labelStyle={{ color: t.axis, marginBottom: 4 }}
          formatter={(value: unknown, name: string) => (Array.isArray(value) ? [`${money(value[0] as number)} to ${money(value[1] as number)}`, name] : [money(value as number), name])}
        />
        {cone && lastDate && <ReferenceLine x={lastDate} stroke={t.axis} strokeDasharray="3 4" strokeOpacity={0.6} />}
        {cone && <Area dataKey="band80" name="80% range" stroke="none" fill={t.accent} fillOpacity={0.12} isAnimationActive={false} />}
        {cone && <Area dataKey="band50" name="50% range" stroke="none" fill={t.accent} fillOpacity={0.2} isAnimationActive={false} />}
        {cone && <Line dataKey="median" name="Median, zero drift" stroke={t.accent} strokeDasharray="4 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />}
        <Line dataKey="price" name="Close" stroke={t.line} strokeWidth={2} dot={false} activeDot={{ r: 4, fill: t.line, stroke: t.surface, strokeWidth: 2 }} connectNulls={false} isAnimationActive={animate} animationDuration={1400} animationEasing="ease-out" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
