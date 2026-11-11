import { useEffect, useRef } from 'react';
import { useReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/utils';

// The Axiom mark (same paths as components/Logo.tsx), in its 32 by 32 box.
const STEM = 'M5.5 26 15 6.5 24.5 26';
const ARROW = ['M15.5 20.5 27 9', 'M20.5 8.5H27.5V15.5'];

type Dot = { hx: number; hy: number; x: number; y: number; vx: number; vy: number; blue: boolean; r: number; tw: number };

/** Rasterise the mark off screen, then keep one dot at a random spot in each lit cell (no grid lines show). */
function sample(size: number, gap: number): Dot[] {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const g = c.getContext('2d');
  if (!g) return [];
  const k = size / 32;
  g.scale(k, k);
  g.lineCap = 'round';
  g.lineJoin = 'round';
  g.lineWidth = 3.2;
  g.strokeStyle = '#f00';
  g.stroke(new Path2D(STEM));
  g.strokeStyle = '#00f';
  for (const p of ARROW) g.stroke(new Path2D(p));
  const px = g.getImageData(0, 0, size, size).data;
  let seed = 7;
  const rand = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296;
  const dots: Dot[] = [];
  for (let gy = 0; gy < size; gy += gap)
    for (let gx = 0; gx < size; gx += gap) {
      const x = Math.min(size - 1, Math.floor(gx + rand() * gap));
      const y = Math.min(size - 1, Math.floor(gy + rand() * gap));
      const i = (y * size + x) * 4;
      if (px[i + 3] < 140) continue;
      const nx = x / size - 0.5;
      const ny = y / size - 0.5;
      dots.push({ hx: nx, hy: ny, x: nx, y: ny, vx: 0, vy: 0, blue: px[i + 2] > px[i], r: 0.5 + rand() * 0.8, tw: rand() * 6.283 });
    }
  // A little loose dust around the mark.
  for (let i = 0; i < 160; i++) {
    const a = rand() * 6.283;
    const d = 0.3 + rand() * 0.25;
    const nx = Math.cos(a) * d;
    const ny = Math.sin(a) * d * 0.8;
    dots.push({ hx: nx, hy: ny, x: nx, y: ny, vx: 0, vy: 0, blue: true, r: 0.3 + rand() * 0.5, tw: rand() * 6.283 });
  }
  return dots;
}

/**
 * The Axiom mark made of glowing particles, floating over a soft pool of light. Move the pointer through it
 * and the particles scatter, then drift home on a spring. Static for reduced motion; pauses off screen.
 */
export function MarkField({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext?.('2d');
    if (!canvas || !ctx) return;
    const dots = sample(320, window.innerWidth < 768 ? 4 : 3);
    const pointer = { x: -9, y: -9, active: false };
    let W = 0;
    let H = 0;
    let dpr = 1;
    let raf = 0;
    let visible = true;
    let t = 0;

    const size = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = canvas.clientWidth;
      H = canvas.clientHeight;
      canvas.width = Math.max(1, Math.round(W * dpr));
      canvas.height = Math.max(1, Math.round(H * dpr));
    };

    const draw = () => {
      const S = Math.min(W, H) * 0.78;
      const cx = W / 2;
      const cy = H * 0.47;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = 'lighter';
      const float = reduce ? 0 : Math.sin(t * 0.8) * 0.012;
      const floor = cy + 0.33 * S;
      for (const d of dots) {
        const dx = reduce ? 0 : Math.sin(t * 0.9 + d.tw) * 0.0025;
        const dy = reduce ? 0 : Math.cos(t * 0.7 + d.tw * 1.3) * 0.0025;
        const x = cx + (d.x + dx) * S;
        const y = cy + (d.y + dy + float) * S;
        const tw = reduce ? 1 : 0.7 + 0.3 * Math.sin(t * 2 + d.tw);
        const away = Math.min(1, Math.hypot(d.x - d.hx, d.y - d.hy) * 12);
        ctx.fillStyle = d.blue ? `hsla(199, 95%, ${64 + away * 14}%, ${0.85 * tw})` : `hsla(205, 55%, ${88 - away * 18}%, ${0.7 * tw})`;
        const r = d.r * (S / 330) * (1 + away * 0.6);
        ctx.fillRect(x - r, y - r, r * 2, r * 2);
        // Its reflection on the floor: flipped, squashed and fading with depth.
        const below = 0.33 - d.hy;
        if (below > 0) {
          ctx.globalAlpha = Math.max(0, 0.22 - below * 0.5) * tw;
          ctx.fillRect(x - r, floor + below * S * 0.55 - r, r * 2, r * 2);
          ctx.globalAlpha = 1;
        }
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = 'source-over';
    };

    const step = () => {
      const S = Math.min(W, H) * 0.78;
      let moving = false;
      for (const d of dots) {
        if (pointer.active) {
          const dx = d.x - pointer.x;
          const dy = d.y - pointer.y;
          const dist = Math.hypot(dx, dy);
          const reach = 0.16;
          if (dist < reach && dist > 0.0001) {
            const f = ((reach - dist) / reach) ** 2 * 0.012;
            d.vx += (dx / dist) * f;
            d.vy += (dy / dist) * f;
          }
        }
        d.vx += (d.hx - d.x) * 0.045;
        d.vy += (d.hy - d.y) * 0.045;
        d.vx *= 0.84;
        d.vy *= 0.84;
        d.x += d.vx;
        d.y += d.vy;
        if (Math.abs(d.vx) + Math.abs(d.vy) > 0.00005) moving = true;
      }
      return moving || S === 0;
    };

    let last = 0;
    const tick = (now: number) => {
      const dt = last ? Math.min(0.05, (now - last) / 1000) : 0;
      last = now;
      if (!reduce) t += dt;
      const moving = step();
      draw();
      raf = visible && (!reduce || moving || pointer.active) ? requestAnimationFrame(tick) : 0;
    };
    const wake = () => {
      if (!raf && visible) {
        last = 0;
        raf = requestAnimationFrame(tick);
      }
    };

    const host = canvas.parentElement ?? canvas;
    const move = (e: PointerEvent) => {
      const b = canvas.getBoundingClientRect();
      const S = Math.min(b.width, b.height) * 0.78;
      pointer.x = (e.clientX - b.left - b.width / 2) / S;
      pointer.y = (e.clientY - b.top - b.height * 0.47) / S;
      pointer.active = true;
      wake();
    };
    const leave = () => {
      pointer.active = false;
      wake();
    };
    host.addEventListener('pointermove', move);
    host.addEventListener('pointerleave', leave);

    size();
    draw();
    const ro = new ResizeObserver(() => {
      size();
      draw();
    });
    ro.observe(canvas);
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      cancelAnimationFrame(raf);
      raf = 0;
      if (visible && !reduce) wake();
    });
    io.observe(canvas);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
      host.removeEventListener('pointermove', move);
      host.removeEventListener('pointerleave', leave);
    };
  }, [reduce]);

  return <canvas ref={ref} aria-hidden className={cn('block h-full w-full', className)} />;
}
