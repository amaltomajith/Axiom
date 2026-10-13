import { useMemo } from 'react';
import { useTheme } from 'next-themes';

export interface ChartTheme {
  grid: string;
  axis: string;
  line: string;
  accent: string;
  benchmark: string;
  surface: string;
  border: string;
  text: string;
  mono: string;
}

const read = (name: string): string => {
  if (typeof document === 'undefined') return '0 0% 50%';
  return getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim() || '0 0% 50%';
};

/**
 * Recharts needs concrete colour strings, not CSS variables. Resolve the design tokens for the active theme
 * so the same chart reads correctly in light and dark (no hard-coded colours in components).
 */
export function useChartTheme(): ChartTheme {
  const { resolvedTheme } = useTheme();
  return useMemo(
    () => {
      const hsl = (n: string) => `hsl(${read(n)})`;
      return {
        grid: hsl('chart-grid'),
        axis: hsl('chart-axis'),
        line: hsl('chart-line'),
        accent: hsl('chart-accent'),
        benchmark: hsl('chart-benchmark'),
        surface: hsl('popover'),
        border: hsl('border'),
        text: hsl('foreground'),
        mono: '"Geist Mono Variable", ui-monospace, monospace',
      };
    },
    // resolvedTheme is the real dependency: tokens change when the class on <html> flips
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [resolvedTheme],
  );
}
