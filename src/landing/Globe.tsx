import { useEffect, useRef } from 'react';
import { useReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/utils';

type P = { x: number; y: number; z: number; land: boolean };

/** Small seeded generator, so the globe looks the same on every visit. */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

/**
 * Points spread evenly over a sphere, nudged a little so no lattice shows. A sum of waves in random
 * directions marks the brightest third as "land", which reads as continents without drawing a map.
 */
function makePoints(n: number, seed = 7): { surface: P[]; air: P[] } {
  const rand = rng(seed);
  const waves = Array.from({ length: 7 }, (_, i) => {
    const u = rand() * 2 - 1;
    const t = rand() * Math.PI * 2;
    const r = Math.sqrt(1 - u * u);
    return { d: [r * Math.cos(t), u, r * Math.sin(t)], k: 1.6 + i * 0.9, ph: rand() * Math.PI * 2, w: 1 / Math.pow(i + 1, 0.7) };
  });
  const golden = Math.PI * (3 - Math.sqrt(5));
  const raw: { x: number; y: number; z: number; f: number }[] = [];
  for (let i = 0; i < n; i++) {
    let y = 1 - ((i + 0.5) / n) * 2 + (rand() - 0.5) * (1.6 / n) * 40;
    y = Math.max(-1, Math.min(1, y));
    const r = Math.sqrt(1 - y * y);
    const t = golden * i + (rand() - 0.5) * 0.35;
    const x = Math.cos(t) * r;
    const z = Math.sin(t) * r;
    let f = 0;
    for (const w of waves) f += w.w * Math.sin(w.k * (w.d[0] * x + w.d[1] * y + w.d[2] * z) + w.ph);
    raw.push({ x, y, z, f });
  }
  const cut = [...raw].sort((a, b) => a.f - b.f)[Math.floor(raw.length * 0.64)].f;
  const surface = raw.map(p => ({ x: p.x, y: p.y, z: p.z, land: p.f >= cut }));
  const air = Array.from({ length: Math.round(n / 10) }, () => {
    const u = rand() * 2 - 1;
    const t = rand() * Math.PI * 2;
    const r = Math.sqrt(1 - u * u);
    const h = 1.03 + rand() * rand() * 0.16;
    return { x: r * Math.cos(t) * h, y: u * h, z: r * Math.sin(t) * h, land: false };
  });
  return { surface, air };
}

/**
 * A slowly turning globe of blue points, drawn on a canvas. It pauses when off screen and stays still
 * for people who prefer reduced motion.
 */
export function Globe({ className, count = 11000, tilt = 0.32, speed = 0.05 }: { className?: string; count?: number; tilt?: number; speed?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext?.('2d');
    if (!canvas || !ctx) return;
    // Fewer points on small screens: the same look for a fraction of the work.
    const { surface, air } = makePoints(window.innerWidth < 640 ? Math.round(count * 0.45) : count);
    const ct = Math.cos(tilt);
    const st = Math.sin(tilt);
    let angle = 0.9;
    let raf = 0;
    let visible = true;
    let last = 0;

    const size = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(canvas.clientWidth * dpr));
      canvas.height = Math.max(1, Math.round(canvas.clientHeight * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const draw = () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      const half = Math.min(w, h) / 2;
      const R = half * 0.8;
      const cx = w / 2;
      const cy = h / 2;
      ctx.clearRect(0, 0, w, h);
      ctx.globalAlpha = 1;
      // Atmosphere: fades to nothing before the canvas edge, so no box ever shows.
      const halo = ctx.createRadialGradient(cx, cy, R * 0.92, cx, cy, half);
      halo.addColorStop(0, 'hsla(199, 92%, 58%, 0.22)');
      halo.addColorStop(1, 'hsla(199, 92%, 58%, 0)');
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(cx, cy, half, 0, Math.PI * 2);
      ctx.fill();
      const body = ctx.createRadialGradient(cx - R * 0.25, cy - R * 0.35, R * 0.1, cx, cy, R);
      body.addColorStop(0, 'hsla(205, 80%, 22%, 0.55)');
      body.addColorStop(1, 'hsla(215, 70%, 8%, 0.2)');
      ctx.fillStyle = body;
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.fill();

      const ca = Math.cos(angle);
      const sa = Math.sin(angle);
      const plot = (p: P, isAir: boolean) => {
        const x1 = p.x * ca + p.z * sa;
        const z1 = -p.x * sa + p.z * ca;
        const y2 = p.y * ct - z1 * st;
        const z2 = p.y * st + z1 * ct;
        if (!isAir && z2 < -0.05) return;
        const depth = Math.max(0, (z2 + 1) / 2);
        let a: number;
        let s: number;
        if (isAir) {
          a = 0.12 + 0.4 * depth;
          s = 1.1;
          ctx.fillStyle = 'hsl(199, 90%, 70%)';
        } else if (p.land) {
          a = 0.35 + 0.65 * depth;
          s = 0.9 + 1.25 * depth;
          ctx.fillStyle = 'hsl(198, 95%, 66%)';
        } else {
          a = 0.04 + 0.12 * depth;
          s = 0.9 + 0.6 * depth;
          ctx.fillStyle = 'hsl(205, 90%, 58%)';
        }
        ctx.globalAlpha = a;
        ctx.fillRect(cx + x1 * R - s / 2, cy - y2 * R - s / 2, s, s);
      };
      for (const p of surface) plot(p, false);
      for (const p of air) plot(p, true);
      ctx.globalAlpha = 1;
    };

    const tick = (t: number) => {
      const dt = last ? Math.min(0.05, (t - last) / 1000) : 0;
      last = t;
      angle += dt * speed * Math.PI;
      draw();
      if (visible) raf = requestAnimationFrame(tick);
    };

    size();
    draw();
    const ro = new ResizeObserver(() => {
      size();
      draw();
    });
    ro.observe(canvas);

    let io: IntersectionObserver | undefined;
    if (!reduce) {
      io = new IntersectionObserver(([e]) => {
        visible = e.isIntersecting;
        cancelAnimationFrame(raf);
        last = 0;
        if (visible) raf = requestAnimationFrame(tick);
      });
      io.observe(canvas);
    }
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io?.disconnect();
    };
  }, [count, tilt, speed, reduce]);

  return <canvas ref={ref} aria-hidden className={cn('block h-full w-full', className)} />;
}
