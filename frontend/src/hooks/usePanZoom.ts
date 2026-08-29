import { useCallback, useEffect, useRef, useState, type PointerEvent } from "react";

const MIN_ZOOM = 0.28;
const MAX_ZOOM = 2.4;
const FIT_FLOOR = 0.55;
const DRAG_THRESHOLD = 4;

export function usePanZoom(width: number, height: number, resetKey: string) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; viewX: number; viewY: number; moved: boolean } | null>(null);
  const interacted = useRef(false);
  const suppressClick = useRef(false);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const [panning, setPanning] = useState(false);

  const fit = useCallback(() => {
    const el = viewportRef.current;
    if (!el || width <= 0 || height <= 0) {
      return;
    }
    interacted.current = false;
    const pad = 28;
    const k = Math.min(1, Math.max(FIT_FLOOR, (el.clientWidth - pad * 2) / width));
    setView({
      x: (el.clientWidth - width * k) / 2,
      y: pad,
      k,
    });
  }, [width, height]);

  useEffect(() => {
    fit();
  }, [fit, resetKey]);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) {
      return;
    }
    const observer = new ResizeObserver(() => {
      if (!interacted.current) {
        fit();
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [fit]);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) {
      return;
    }
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = el.getBoundingClientRect();
      const mx = event.clientX - rect.left;
      const my = event.clientY - rect.top;
      interacted.current = true;
      setView((current) => {
        const next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, current.k * (event.deltaY > 0 ? 0.9 : 1.1)));
        return {
          k: next,
          x: mx - ((mx - current.x) * next) / current.k,
          y: my - ((my - current.y) * next) / current.k,
        };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  return {
    viewportRef,
    view,
    panning,
    fit,
    consumeClick() {
      if (!suppressClick.current) {
        return false;
      }
      suppressClick.current = false;
      return true;
    },
    onPointerDown(event: PointerEvent<HTMLDivElement>) {
      if (event.button !== 0) {
        return;
      }
      drag.current = { x: event.clientX, y: event.clientY, viewX: view.x, viewY: view.y, moved: false };
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    onPointerMove(event: PointerEvent<HTMLDivElement>) {
      if (!drag.current) {
        return;
      }
      const dx = event.clientX - drag.current.x;
      const dy = event.clientY - drag.current.y;
      if (Math.hypot(dx, dy) > DRAG_THRESHOLD) {
        drag.current.moved = true;
        interacted.current = true;
        setPanning(true);
      }
      if (drag.current.moved) {
        setView((current) => ({
          ...current,
          x: drag.current!.viewX + dx,
          y: drag.current!.viewY + dy,
        }));
      }
    },
    onPointerUp(event: PointerEvent<HTMLDivElement>) {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      suppressClick.current = Boolean(drag.current?.moved);
      drag.current = null;
      setPanning(false);
    },
  };
}
