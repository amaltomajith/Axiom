import { useEffect, useRef } from 'react';
import { useReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/utils';
import { LAND_BITS, LAND_H, LAND_W } from './landmask';

/** Seeded generator, so the globe is identical on every visit. */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

let landCache: Uint8Array | null = null;
function isLand(lat: number, lon: number) {
  if (!landCache) landCache = Uint8Array.from(atob(LAND_BITS), c => c.charCodeAt(0));
  const x = Math.min(LAND_W - 1, Math.max(0, Math.floor(((lon + 180) / 360) * LAND_W)));
  const y = Math.min(LAND_H - 1, Math.max(0, Math.floor(((90 - lat) / 180) * LAND_H)));
  const i = y * LAND_W + x;
  return (landCache[i >> 3] & (1 << (i & 7))) !== 0;
}

// Point kinds: 0 sea, 1 land, 2 atmosphere, 3 drifting cloud (the dissolving sphere).
function makePoints(variant: 'earth' | 'cloud', n: number) {
  const rand = rng(variant === 'earth' ? 11 : 29);
  const pos: number[] = [];
  const info: number[] = [];
  const push = (x: number, y: number, z: number, kind: number) => {
    pos.push(x, y, z);
    info.push(kind, rand());
  };
  if (variant === 'earth') {
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < n; i++) {
      const y = 1 - ((i + 0.5) / n) * 2;
      const r = Math.sqrt(1 - y * y);
      const t = golden * i;
      const x = Math.sin(t) * r;
      const z = Math.cos(t) * r;
      const lat = (Math.asin(y) * 180) / Math.PI;
      const lon = (Math.atan2(x, z) * 180) / Math.PI;
      if (isLand(lat, lon)) push(x, y, z, 1);
      else if (rand() < 0.12) push(x, y, z, 0);
    }
    // A loose, uneven shell of particles hanging around the planet.
    for (let i = 0; i < n * 0.06; i++) {
      const u = rand() * 2 - 1;
      const t = rand() * Math.PI * 2;
      const r = Math.sqrt(1 - u * u);
      const h = 1.04 + 0.05 * (Math.sin(3 * t + 2 * u) * 0.5 + 0.5) + rand() * rand() * rand() * 0.3;
      push(Math.sin(t) * r * h, u * h, Math.cos(t) * r * h, 2);
    }
  } else {
    for (let i = 0; i < n; i++) {
      const u = rand() * 2 - 1;
      const t = rand() * Math.PI * 2;
      const r = Math.sqrt(1 - u * u);
      const h = 1 + (rand() + rand() + rand() - 1.5) * 0.06;
      push(Math.sin(t) * r * h, u * h, Math.cos(t) * r * h, 3);
    }
  }
  return { pos: new Float32Array(pos), info: new Float32Array(info), count: info.length / 2 };
}

const VERT = `
attribute vec3 a_pos;
attribute vec2 a_info;
uniform mat3 u_rot;
uniform vec2 u_scale;
uniform float u_px;
uniform float u_time;
varying float v_alpha;
varying vec3 v_color;
void main() {
  float kind = a_info.x;
  float seed = a_info.y;
  vec3 p = a_pos;
  if (kind > 2.5) {
    float wave = sin(u_time * 0.5 + seed * 6.2831) * 0.5 + 0.5;
    float lift = pow(max(0.0, sin(u_time * 0.35 + p.y * 2.4 + seed * 3.0)), 6.0);
    p *= 1.0 + wave * 0.03 + lift * (0.25 + seed * 0.5);
  }
  vec3 q = u_rot * p;
  float depth = q.z * 0.5 + 0.5;
  float lit = max(dot(normalize(q), normalize(vec3(-0.55, 0.6, 0.58))), 0.0);
  float rim = 1.0 - abs(normalize(q).z);
  float a;
  float s;
  vec3 c;
  if (kind < 0.5) {
    a = q.z < 0.0 ? 0.0 : 0.07 + 0.22 * lit + 0.25 * rim * rim * lit;
    s = 0.9;
    c = vec3(0.2, 0.5, 0.95);
  } else if (kind < 1.5) {
    a = q.z < -0.03 ? 0.0 : (0.3 + 1.25 * pow(lit, 0.6)) * (0.5 + 0.5 * depth) + 0.9 * rim * rim * lit;
    s = 1.1 + 0.8 * depth;
    c = mix(vec3(0.16, 0.55, 1.0), vec3(0.7, 0.92, 1.0), lit * lit);
  } else if (kind < 2.5) {
    a = (q.z < 0.0 ? 0.04 : 0.1 + 0.45 * lit) * (0.6 + 0.7 * rim);
    s = 0.9;
    c = vec3(0.45, 0.8, 1.0);
  } else {
    a = (0.3 + 0.9 * rim * rim + 0.6 * lit) * (0.5 + 0.5 * depth);
    s = 1.1 + 0.8 * depth;
    c = mix(vec3(0.2, 0.6, 1.0), vec3(0.75, 0.93, 1.0), lit);
  }
  a *= 0.8 + 0.2 * sin(u_time * 1.6 + seed * 40.0);
  gl_Position = vec4(q.x * u_scale.x, q.y * u_scale.y, 0.0, 1.0);
  gl_PointSize = s * u_px;
  v_alpha = clamp(a, 0.0, 1.0);
  v_color = c;
}`;

const FRAG = `
precision mediump float;
varying float v_alpha;
varying vec3 v_color;
void main() {
  float r = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.1, r) * v_alpha;
  if (a < 0.004) discard;
  gl_FragColor = vec4(v_color * a, a);
}`;

type Props = {
  className?: string;
  /** "earth" draws the continents; "cloud" is a sphere of loose particles that keeps lifting away. */
  variant?: 'earth' | 'cloud';
  /** Points spread over the sphere before land and sea are sorted; fewer on small screens. */
  points?: number;
  /** Globe radius as a share of the canvas's shorter side. Place it in a square box. */
  radius?: number;
  /** Longitude facing the viewer at the start, in degrees. */
  facing?: number;
  tilt?: number;
  speed?: number;
  interactive?: boolean;
};

/**
 * A planet of glowing blue points drawn with WebGL: real coastlines, lit from the upper left, slowly
 * turning. Drag it to spin it (sideways only on touch, so the page still scrolls); it coasts to a stop
 * and carries on by itself. It pauses off screen, and with reduced motion it only moves when you move it.
 */
export function Globe({ className, variant = 'earth', points = 110000, radius = 0.4, facing = 15, tilt = 0.35, speed = 0.06, interactive = true }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    const canvas = ref.current;
    const gl = canvas?.getContext?.('webgl', { premultipliedAlpha: true, alpha: true, antialias: false }) as WebGLRenderingContext | null;
    if (!canvas || !gl) return;

    const { pos, info, count } = makePoints(variant, Math.round(points * (window.innerWidth < 768 ? 0.45 : 1)));
    const prog = gl.createProgram();
    const shaders = [
      [gl.VERTEX_SHADER, VERT],
      [gl.FRAGMENT_SHADER, FRAG],
    ].map(([type, src]) => {
      const s = gl.createShader(type as number)!;
      gl.shaderSource(s, src as string);
      gl.compileShader(s);
      gl.attachShader(prog!, s);
      return s;
    });
    gl.linkProgram(prog!);
    if (!prog || !gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
    gl.useProgram(prog);
    const buffers = (
      [
        [pos, 'a_pos', 3],
        [info, 'a_info', 2],
      ] as const
    ).map(([data, name, size]) => {
      const buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(prog, name);
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 0, 0);
      return buf;
    });
    const uRot = gl.getUniformLocation(prog, 'u_rot');
    const uScale = gl.getUniformLocation(prog, 'u_scale');
    const uPx = gl.getUniformLocation(prog, 'u_px');
    const uTime = gl.getUniformLocation(prog, 'u_time');
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.clearColor(0, 0, 0, 0);

    const size = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.75);
      canvas.width = Math.max(1, Math.round(canvas.clientWidth * dpr));
      canvas.height = Math.max(1, Math.round(canvas.clientHeight * dpr));
      gl.viewport(0, 0, canvas.width, canvas.height);
    };

    let yaw = (-facing * Math.PI) / 180;
    let pitch = tilt;
    let vYaw = 0;
    let hoverX = 0;
    let hoverY = 0;
    let curX = 0;
    let curY = 0;
    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    let time = 0;
    let last = 0;
    let raf = 0;
    let visible = true;

    const draw = () => {
      const w = canvas.width;
      const h = canvas.height;
      const R = Math.min(w, h) * radius;
      const ya = yaw + curX * 0.22;
      const pa = pitch + curY * 0.12;
      const cy = Math.cos(ya);
      const sy = Math.sin(ya);
      const cp = Math.cos(pa);
      const sp = Math.sin(pa);
      // Rx(pitch) * Ry(yaw), column-major as WebGL expects.
      gl.uniformMatrix3fv(uRot, false, [cy, sp * sy, -cp * sy, 0, cp, sp, sy, -sp * cy, cp * cy]);
      gl.uniform2f(uScale, (2 * R) / w, (2 * R) / h);
      gl.uniform1f(uPx, Math.max(1.3, (R / 360) * 1.9));
      gl.uniform1f(uTime, time);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.POINTS, 0, count);
    };

    const settled = () => Math.abs(vYaw) < 0.0002 && Math.abs(hoverX - curX) < 0.002 && Math.abs(hoverY - curY) < 0.002;
    const tick = (t: number) => {
      const dt = last ? Math.min(0.05, (t - last) / 1000) : 0;
      last = t;
      if (!reduce) time += dt;
      if (!dragging) {
        yaw += (reduce ? 0 : speed * dt) + vYaw;
        vYaw *= 0.95;
        pitch += (tilt - pitch) * 0.025;
      }
      curX += (hoverX - curX) * 0.06;
      curY += (hoverY - curY) * 0.06;
      draw();
      raf = visible && (!reduce || dragging || !settled()) ? requestAnimationFrame(tick) : 0;
    };
    const wake = () => {
      if (!raf && visible) {
        last = 0;
        raf = requestAnimationFrame(tick);
      }
    };

    const down = (e: PointerEvent) => {
      dragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
      vYaw = 0;
      canvas.setPointerCapture(e.pointerId);
      canvas.style.cursor = 'grabbing';
      wake();
    };
    const move = (e: PointerEvent) => {
      if (dragging) {
        const dx = e.clientX - lastX;
        const dy = e.clientY - lastY;
        lastX = e.clientX;
        lastY = e.clientY;
        vYaw = dx * 0.005;
        yaw += vYaw;
        if (e.pointerType === 'mouse') pitch = Math.max(-0.9, Math.min(1.1, pitch + dy * 0.004));
      } else if (e.pointerType === 'mouse' && !reduce) {
        const b = canvas.getBoundingClientRect();
        hoverX = ((e.clientX - b.left) / b.width - 0.5) * 2;
        hoverY = ((e.clientY - b.top) / b.height - 0.5) * 2;
        wake();
      }
    };
    const up = () => {
      dragging = false;
      canvas.style.cursor = '';
      wake();
    };
    const leave = () => {
      hoverX = 0;
      hoverY = 0;
      wake();
    };
    if (interactive) {
      canvas.addEventListener('pointerdown', down);
      canvas.addEventListener('pointermove', move);
      canvas.addEventListener('pointerup', up);
      canvas.addEventListener('pointercancel', up);
      canvas.addEventListener('pointerleave', leave);
    }

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
      canvas.removeEventListener('pointerdown', down);
      canvas.removeEventListener('pointermove', move);
      canvas.removeEventListener('pointerup', up);
      canvas.removeEventListener('pointercancel', up);
      canvas.removeEventListener('pointerleave', leave);
      buffers.forEach(b => gl.deleteBuffer(b));
      shaders.forEach(s => gl.deleteShader(s));
      gl.deleteProgram(prog);
    };
  }, [variant, points, radius, facing, tilt, speed, interactive, reduce]);

  const disc = `${radius * 200}%`;
  return (
    <div className={cn('relative h-full w-full', className)}>
      {variant === 'earth' && (
        <>
          {/* The night side and the soft blue air around it, under the points. */}
          <div
            aria-hidden
            className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{
              width: disc,
              height: disc,
              background: 'radial-gradient(circle at 34% 28%, hsl(205 85% 30% / 0.55), hsl(214 70% 12% / 0.55) 45%, hsl(222 50% 5% / 0.7) 75%)',
              boxShadow:
                '0 0 90px 10px hsl(199 92% 58% / 0.22), 0 0 220px 40px hsl(205 92% 50% / 0.12), inset 14px 16px 50px -18px hsl(199 95% 72% / 0.55), inset -30px -30px 80px -30px hsl(222 60% 2% / 0.9)',
            }}
          />
        </>
      )}
      <canvas ref={ref} aria-hidden className={cn('relative block h-full w-full touch-pan-y', interactive && 'cursor-grab')} />
    </div>
  );
}
