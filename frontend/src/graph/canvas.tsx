import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent } from "react";

import { usePlaceGraph } from "../api/query";
import { type WorkspaceGraph, type WorkspaceNode } from "./build";
import { computePlaceDagLayout } from "./layout";

const MIN_ZOOM = 0.12;
const MAX_ZOOM = 2.4;
const DRAG_THRESHOLD = 4;

function usePanZoom(width: number, height: number, resetKey: string) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; viewX: number; viewY: number; moved: boolean } | null>(null);
  const interacted = useRef(false);
  const suppressClick = useRef(false);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const [panning, setPanning] = useState(false);

  const fit = useCallback(() => {
    const el = viewportRef.current;
    if (!el || width <= 0 || height <= 0 || el.clientWidth < 40 || el.clientHeight < 40) {
      return;
    }
    interacted.current = false;
    const padX = 36;
    const padY = 28;
    const scale = Math.min((el.clientWidth - padX * 2) / width, (el.clientHeight - padY * 2) / height);
    const k = Math.min(1, Math.max(0.68, scale));
    setView({
      x: (el.clientWidth - width * k) / 2,
      y: Math.max(padY, (el.clientHeight - height * k) / 2),
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

interface PlaceGraphProps {
  address: string;
  onOpenOverview: () => void;
}

export function PlaceGraph({ address, onOpenOverview }: PlaceGraphProps) {
  const graphQuery = usePlaceGraph(address);
  const graph = graphQuery.data;
  if (!graph) {
    return null;
  }
  return <GraphCanvas graph={graph} onOpenOverview={onOpenOverview} />;
}

function GraphCanvas({ graph, onOpenOverview }: { graph: WorkspaceGraph; onOpenOverview: () => void }) {
  const [selected, setSelected] = useState<string | null>(null);
  const sizes = useMemo(
    () => Object.fromEntries(graph.nodes.map((node) => [node.id, sizeFor(node)])),
    [graph.nodes],
  );
  const layout = useMemo(
    () =>
      computePlaceDagLayout(
        graph.nodes[0]?.id ?? "place",
        graph.nodes.map((node) => node.id),
        graph.links,
        { sizes },
      ),
    [graph, sizes],
  );
  const nodeById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);
  const pan = usePanZoom(layout.width, layout.height, graph.nodes[0]?.id ?? "");

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelected(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div
      ref={pan.viewportRef}
      className={`g-field workspace-in${pan.panning ? " is-panning" : ""}${selected ? " is-focused" : ""}`}
      aria-label="Place graph"
      onPointerDown={pan.onPointerDown}
      onPointerMove={pan.onPointerMove}
      onPointerUp={pan.onPointerUp}
      onPointerCancel={pan.onPointerUp}
      onDoubleClick={pan.fit}
      onClick={(event) => {
        if (pan.consumeClick()) {
          return;
        }
        if ((event.target as HTMLElement).closest("[data-node]")) {
          return;
        }
        setSelected(null);
      }}
    >
      <div
        className="g-map"
        style={
          {
            width: layout.width,
            height: layout.height,
            "--g-x": `${pan.view.x}px`,
            "--g-y": `${pan.view.y}px`,
            "--g-k": pan.view.k,
          } as CSSProperties
        }
      >
        <svg height={layout.height} width={layout.width}>
          {layout.edges.map((edge) => {
            const on = selected != null && (edge.from === selected || edge.to === selected);
            const thought = nodeById.get(edge.to)?.role === "thought" || nodeById.get(edge.from)?.role === "thought";
            return (
              <path
                key={`${edge.from}-${edge.to}`}
                className={`g-edge${edge.kind === "cross" ? " is-cross" : ""}${thought ? " is-thought" : ""}${
                  on ? " is-on" : ""
                }`}
                d={edge.d}
              />
            );
          })}
        </svg>
        {layout.nodes.map((box) => {
          const node = nodeById.get(box.id);
          if (!node) {
            return null;
          }
          const on = selected === node.id;
          return (
            <article
              key={node.id}
              aria-current={on ? "true" : undefined}
              aria-label={node.role === "more" ? `${node.title}, open overview` : node.title}
              className={`g-node g-node-${skin(node)}${on ? " is-on" : ""}`}
              data-node={node.id}
              role="button"
              tabIndex={0}
              onClick={() => {
                if (pan.consumeClick()) {
                  return;
                }
                if (node.role === "more") {
                  onOpenOverview();
                  return;
                }
                setSelected(on ? null : node.id);
              }}
              onKeyDown={(event) => {
                if (event.key !== "Enter" && event.key !== " ") {
                  return;
                }
                event.preventDefault();
                if (node.role === "more") {
                  onOpenOverview();
                  return;
                }
                setSelected(on ? null : node.id);
              }}
              style={{ left: box.x, top: box.y, width: box.width, minHeight: box.height }}
            >
              <p className="g-kicker">
                <span>{node.tag}</span>
                {node.confidence != null ? <span className="g-pct">{Math.round(node.confidence * 100)}%</span> : null}
              </p>
              <h3 className="g-title">{node.title}</h3>
              {node.body ? <p className="g-body">{node.body}</p> : null}
            </article>
          );
        })}
      </div>
      <button className="g-fit" onClick={pan.fit} type="button">
        Recenter
      </button>
    </div>
  );
}

function skin(node: WorkspaceNode): string {
  if (node.role === "place") {
    return "place";
  }
  if (node.role === "thought") {
    return node.tone === "watch" ? "watch" : "think";
  }
  if (node.role === "more" || node.tone === "gap") {
    return "gap";
  }
  return "trail";
}

function sizeFor(node: WorkspaceNode): { width: number; height: number } {
  const width = widthFor(node);
  return { width, height: measureHeight(node, width) };
}

function widthFor(node: WorkspaceNode): number {
  if (node.role === "place") {
    return 380;
  }
  if (node.role === "thought") {
    return 320;
  }
  if (node.role === "more") {
    return 210;
  }
  if (node.role === "facet") {
    return 260;
  }
  return 300;
}

let measureHost: HTMLElement | null = null;

function measureHeight(node: WorkspaceNode, width: number): number {
  if (typeof document === "undefined") {
    return 140;
  }
  const host = measureHost?.isConnected ? measureHost : document.createElement("article");
  if (!host.isConnected) {
    host.setAttribute("aria-hidden", "true");
    host.style.cssText = "position:absolute;left:-9999px;top:0;visibility:hidden;pointer-events:none;";
    document.body.appendChild(host);
    measureHost = host;
  }
  host.className = `g-node g-node-${skin(node)}`;
  host.style.width = `${width}px`;
  host.style.height = "auto";
  host.innerHTML = `<p class="g-kicker"><span>${escapeHtml(node.tag)}</span></p><h3 class="g-title">${escapeHtml(node.title)}</h3>${
    node.body ? `<p class="g-body">${escapeHtml(node.body)}</p>` : ""
  }`;
  return Math.max(96, Math.ceil(host.offsetHeight) + 8);
}

function escapeHtml(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

