import { useEffect, useRef } from "react";

import { MARK } from "./mark";

const THINK_COLS = 48;
const THINK_ROWS = 14;

function thinkStop(row: number) {
  const t = row / Math.max(1, THINK_ROWS - 1);
  return {
    fuse: dimRgb(mixFuse(t), 0.52 - t * 0.28),
    peak: (0.3 - t * 0.16).toFixed(3),
  };
}

function mixFuse(t: number): string {
  const stops = MARK.fuse.length - 1;
  const x = Math.min(1, Math.max(0, t)) * stops;
  const index = Math.min(stops - 1, Math.floor(x));
  const frac = x - index;
  const from = hexRgb(MARK.fuse[index]);
  const to = hexRgb(MARK.fuse[index + 1]);
  return `rgb(${from.map((value, channel) => Math.round(value + (to[channel] - value) * frac)).join(",")})`;
}

function dimRgb(rgb: string, amount: number): string {
  const values = rgb.match(/\d+/g)?.map(Number) ?? [128, 128, 128];
  return `rgb(${values.map((value) => Math.round(value * amount + 28 * (1 - amount))).join(",")})`;
}

function hexRgb(hex: string): [number, number, number] {
  return [1, 3, 5].map((start) => Number.parseInt(hex.slice(start, start + 2), 16)) as [number, number, number];
}

export function ThinkField({ thinking = false }: { thinking?: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const thinkingRef = useRef(thinking);
  thinkingRef.current = thinking;

  useEffect(() => {
    const node = canvasRef.current;
    if (!node) {
      return;
    }
    const surface = node.getContext("2d");
    if (!surface) {
      return;
    }
    const canvas = node;
    const ctx = surface;

    const particles = makeThinkParticles();
    let morph = thinkingRef.current ? 1 : 0;
    let frame = 0;
    let running = true;
    let lastDraw = 0;
    const started = performance.now();

    function resize(): void {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const box = canvas.getBoundingClientRect();
      canvas.width = Math.floor(box.width * dpr);
      canvas.height = Math.floor(box.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function tick(now: number): void {
      if (!running) {
        return;
      }
      morph += ((thinkingRef.current ? 1 : 0) - morph) * 0.12;
      if (!document.hidden && now - lastDraw > 16) {
        drawThinkField(ctx, canvas, particles, morph, (now - started) / 1000);
        lastDraw = now;
      }
      frame = requestAnimationFrame(tick);
    }

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    frame = requestAnimationFrame(tick);
    return () => {
      running = false;
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

  return (
    <div className={`think-field${thinking ? " is-thinking" : ""}`} aria-hidden>
      <canvas ref={canvasRef} className="think-canvas" />
    </div>
  );
}

interface ThinkParticle {
  col: number;
  row: number;
  fuse: [number, number, number];
  peak: number;
  sx: number;
  sy: number;
  sz: number;
}

function makeThinkParticles(): ThinkParticle[] {
  const count = THINK_COLS * THINK_ROWS;
  const golden = Math.PI * (3 - Math.sqrt(5));
  return Array.from({ length: count }, (_, index) => {
    const col = index % THINK_COLS;
    const row = Math.floor(index / THINK_COLS);
    const y = 1 - (index / Math.max(1, count - 1)) * 2;
    const radius = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = golden * index;
    return {
      col,
      row,
      fuse: rgbTuple(thinkStop(row).fuse),
      peak: Number(thinkStop(row).peak),
      sx: Math.cos(theta) * radius,
      sy: y,
      sz: Math.sin(theta) * radius,
    };
  });
}

function drawThinkField(
  ctx: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  particles: ThinkParticle[],
  morph: number,
  elapsed: number,
): void {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  ctx.clearRect(0, 0, width, height);
  const ease = morph * morph * (3 - 2 * morph);
  const padX = width * 0.05;
  const padTop = height * 0.16;
  const gridW = width - padX * 2;
  const gridH = height * 0.7;
  const cx = width * 0.5;
  const cy = height * 0.46;
  const spinY = elapsed * 0.7;
  const spinX = 0.32 + Math.sin(elapsed * 0.45) * 0.1;
  const breathe = 1 + Math.sin(elapsed * 2.3) * 0.045 * ease;
  const radius = Math.min(width, height) * 0.168 * breathe;
  if (ease < 0.04) {
    for (const particle of particles) {
      const wave = 0.5 + 0.5 * Math.sin(elapsed * 1.05 - particle.row * 0.42 - particle.col * 0.018);
      ctx.beginPath();
      ctx.fillStyle = `rgba(${particle.fuse[0]},${particle.fuse[1]},${particle.fuse[2]},${0.07 + wave * particle.peak})`;
      ctx.arc(
        padX + ((particle.col + 0.5) / THINK_COLS) * gridW,
        padTop + ((particle.row + 0.5) / THINK_ROWS) * gridH,
        0.72 + wave * 0.22,
        0,
        Math.PI * 2,
      );
      ctx.fill();
    }
    return;
  }

  const drawn = particles.map((particle) => {
    const gx = padX + ((particle.col + 0.5) / THINK_COLS) * gridW;
    const gy = padTop + ((particle.row + 0.5) / THINK_ROWS) * gridH;
    const rotated = rotatePoint(particle.sx, particle.sy, particle.sz, spinX, spinY);
    const px = cx + rotated[0] * radius;
    const py = cy + rotated[1] * radius * 0.94;
    const depth = (rotated[2] + 1) / 2;
    const wave = 0.5 + 0.5 * Math.sin(elapsed * 1.05 - particle.row * 0.42 - particle.col * 0.018);
    const color = mixTuple(particle.fuse, [208, 208, 208], ease);
    return {
      x: gx + (px - gx) * ease,
      y: gy + (py - gy) * ease,
      z: depth,
      size: 1.2 + (1.2 + depth * 2.1) * ease + wave * 0.35 * (1 - ease),
      alpha: (0.05 + wave * particle.peak) * (1 - ease) + (0.12 + depth * 0.72) * ease,
      color,
    };
  });
  drawn.sort((left, right) => left.z - right.z);
  for (const dot of drawn) {
    ctx.beginPath();
    ctx.fillStyle = `rgba(${dot.color[0]},${dot.color[1]},${dot.color[2]},${dot.alpha})`;
    ctx.arc(dot.x, dot.y, dot.size / 2, 0, Math.PI * 2);
    ctx.fill();
  }
}

function rotatePoint(x: number, y: number, z: number, ax: number, ay: number): [number, number, number] {
  const cosY = Math.cos(ay);
  const sinY = Math.sin(ay);
  const x1 = x * cosY + z * sinY;
  const z1 = -x * sinY + z * cosY;
  const cosX = Math.cos(ax);
  const sinX = Math.sin(ax);
  return [x1, y * cosX - z1 * sinX, y * sinX + z1 * cosX];
}

function rgbTuple(rgb: string): [number, number, number] {
  const values = rgb.match(/\d+/g)?.map(Number) ?? [160, 160, 160];
  return [values[0] ?? 160, values[1] ?? 160, values[2] ?? 160];
}

function mixTuple(from: [number, number, number], to: [number, number, number], t: number): [number, number, number] {
  return [
    Math.round(from[0] + (to[0] - from[0]) * t),
    Math.round(from[1] + (to[1] - from[1]) * t),
    Math.round(from[2] + (to[2] - from[2]) * t),
  ];
}
