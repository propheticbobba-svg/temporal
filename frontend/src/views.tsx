import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent, type ReactNode } from "react";

import { formatCoordinate, formatDate, formatGeneratedAt } from "./format";
import { computePlaceDagLayout, type WorkspaceGraph, type WorkspaceNode, type SourceCard } from "./graph";
import { usePlaceGraph, usePlaceSources } from "./query";
import type { Brief, BriefModule, GraphEntity, Location, Signal } from "./types";
import { REL_LABEL, STATUS_LABEL } from "./types";
import { StreetView } from "./StreetView";

const MIN_ZOOM = 0.12;
const MAX_ZOOM = 2.4;
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
    if (!el || width <= 0 || height <= 0 || el.clientWidth < 40 || el.clientHeight < 40) {
      return;
    }
    interacted.current = false;
    const padX = 32;
    const padY = 28;
    const scale = Math.min((el.clientWidth - padX * 2) / width, (el.clientHeight - padY * 2) / height);
    const k = Math.min(1, Math.max(0.4, scale));
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
  onOpenSources: (focus?: string) => void;
}

export function PlaceGraph({ address, onOpenSources }: PlaceGraphProps) {
  const graphQuery = usePlaceGraph(address);
  const graph = graphQuery.data;
  if (!graph) {
    return null;
  }
  return <GraphCanvas graph={graph} onOpenSources={onOpenSources} />;
}

function GraphCanvas({ graph, onOpenSources }: { graph: WorkspaceGraph; onOpenSources: (focus?: string) => void }) {
  const [open, setOpen] = useState<WorkspaceNode | null>(null);
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
  const linkByPair = useMemo(
    () => new Map(graph.links.map((link) => [`${link.from}->${link.to}`, link])),
    [graph.links],
  );
  const pan = usePanZoom(layout.width, layout.height, graph.nodes[0]?.id ?? "");

  return (
    <div
      ref={pan.viewportRef}
      className={`relative h-full min-h-0 w-full flex-1 touch-none overflow-hidden select-none ${
        pan.panning ? "cursor-grabbing" : "cursor-grab"
      }`}
      aria-label="Place graph"
      onPointerDown={pan.onPointerDown}
      onPointerMove={pan.onPointerMove}
      onPointerUp={pan.onPointerUp}
      onPointerCancel={pan.onPointerUp}
      onDoubleClick={pan.fit}
    >
      <div
        className="absolute top-0 left-0 origin-top-left contain-layout"
        style={{
          width: layout.width,
          height: layout.height,
          transform: `translate(${pan.view.x}px, ${pan.view.y}px) scale(${pan.view.k})`,
        }}
      >
        <svg className="block" width={layout.width} height={layout.height}>
          {layout.edges.map((edge) => {
            const meta = linkByPair.get(`${edge.from}->${edge.to}`);
            return (
              <g key={`${edge.from}-${edge.to}`}>
                <path className="fill-none stroke-graph stroke-[1.2]" d={curve(edge.sourceX, edge.sourceY, edge.targetX, edge.targetY)} />
                {meta?.label ? (
                  <text
                    className="fill-graph text-[10px] font-medium"
                    textAnchor="middle"
                    x={(edge.sourceX + edge.targetX) / 2}
                    y={(edge.sourceY + edge.targetY) / 2 - 4}
                  >
                    {meta.label}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
        {layout.nodes.map((box) => {
          const node = nodeById.get(box.id);
          if (!node) {
            return null;
          }
          return (
            <article
              key={node.id}
              className={`absolute box-border flex cursor-pointer flex-col gap-1.5 overflow-hidden rounded-xl border px-3 py-3 ${roleClass(node.role)}`}
              onClick={() => {
                if (pan.consumeClick()) {
                  return;
                }
                if (node.role === "more") {
                  onOpenSources(node.focus);
                  return;
                }
                setOpen(node);
              }}
              style={{ left: box.x, top: box.y, width: box.width, height: box.height }}
            >
              <h3 className="m-0 line-clamp-2 shrink-0 text-[0.78rem] leading-snug font-medium tracking-tight text-white">
                {node.title}
              </h3>
              <p className="m-0 line-clamp-2 min-h-0 flex-1 text-[0.78rem] leading-snug text-ink">{node.body}</p>
              <footer className="mt-auto flex shrink-0 items-center justify-between gap-2">
                <span className="rounded-full bg-white/6 px-1.5 py-0.5 text-[0.68rem] font-medium text-muted lowercase">
                  {node.tag}
                </span>
                {node.confidence != null ? (
                  <span className="text-[0.68rem] font-medium text-graph">{Math.round(node.confidence * 100)}%</span>
                ) : null}
              </footer>
            </article>
          );
        })}
      </div>
      <button
        className="absolute right-3 bottom-3 rounded-full bg-elev px-2.5 py-1 text-[0.72rem] font-medium text-muted hover:text-ink"
        onClick={pan.fit}
        type="button"
      >
        Recenter
      </button>
      {open ? (
        <NodeModal
          node={open}
          onClose={() => setOpen(null)}
          onSources={() => {
            const focus = open.focus;
            setOpen(null);
            onOpenSources(focus);
          }}
        />
      ) : null}
    </div>
  );
}

function NodeModal({
  node,
  onClose,
  onSources,
}: {
  node: WorkspaceNode;
  onClose: () => void;
  onSources: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="absolute inset-0 z-10 flex items-end justify-center bg-black/55 p-4 sm:items-center"
      onClick={onClose}
      role="presentation"
    >
      <article
        aria-labelledby="graph-node-title"
        aria-modal="true"
        className="max-h-[min(72vh,520px)] w-full max-w-md overflow-auto rounded-2xl border border-line bg-elev p-4"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <h2 className="m-0 text-base leading-snug font-medium text-white" id="graph-node-title">
          {node.title}
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-ink">{node.body}</p>
        <footer className="mt-4 flex items-center justify-between gap-3">
          <p className="m-0 text-xs text-muted">
            {node.tag}
            {node.confidence != null ? ` · ${Math.round(node.confidence * 100)}%` : ""}
          </p>
          <div className="flex gap-2">
            {node.role !== "place" ? (
              <button
                className="rounded-full bg-hover px-3 py-1 text-xs font-medium text-ink"
                onClick={onSources}
                type="button"
              >
                Sources
              </button>
            ) : null}
            <button
              className="rounded-full bg-white px-3 py-1 text-xs font-medium text-bg"
              onClick={onClose}
              type="button"
            >
              Close
            </button>
          </div>
        </footer>
      </article>
    </div>
  );
}

function roleClass(role: WorkspaceNode["role"]): string {
  if (role === "place") {
    return "border-place-line bg-place";
  }
  if (role === "facet") {
    return "border-graph-line bg-[#0f1a12]";
  }
  if (role === "more") {
    return "border-dashed border-graph-line bg-graph-fill";
  }
  return "border-graph-line bg-graph-fill";
}

function sizeFor(node: WorkspaceNode): { width: number; height: number } {
  if (node.role === "place") {
    return { width: 360, height: 148 };
  }
  if (node.role === "facet") {
    return { width: 236, height: 120 };
  }
  if (node.role === "more") {
    return { width: 236, height: 136 };
  }
  return { width: 248, height: 136 };
}

function curve(x1: number, y1: number, x2: number, y2: number): string {
  const mid = (y1 + y2) / 2;
  return `M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`;
}

interface SourceGridProps {
  address: string;
  focus?: string | null;
}

export function SourceGrid({ address, focus }: SourceGridProps) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(focus ?? null);
  const sources = usePlaceSources(address, { query, category });
  const cards = sources.data?.cards ?? [];
  const categories = sources.data?.categories ?? [];
  const total = sources.data?.total ?? 0;
  const sections = useMemo(() => groupCards(cards), [cards]);

  useEffect(() => {
    setCategory(focus ?? null);
  }, [focus]);

  return (
    <section className="mx-auto w-full max-w-[1100px]" aria-label="Sources">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h2 className="m-0 text-xl font-medium tracking-tight text-white">
          Sources <span className="font-normal text-dim">{total}</span>
          {categories.length > 0 ? (
            <span className="ml-2 text-[0.85rem] font-normal text-dim">{categories.length} types</span>
          ) : null}
        </h2>
        <input
          className="w-full max-w-70 rounded-full bg-elev px-3 py-2 text-ink placeholder:text-dim"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search sources…"
          type="search"
          value={query}
        />
      </div>
      {categories.length > 1 ? (
        <div className="mb-5.5 flex flex-wrap gap-1.5" role="tablist" aria-label="Source types">
          <Chip selected={category == null} onClick={() => setCategory(null)}>
            All <em className="not-italic text-dim">{total}</em>
          </Chip>
          {categories.map((item) => (
            <Chip key={item.title} selected={category === item.title} onClick={() => setCategory(item.title)}>
              {item.title} <em className="not-italic text-dim">{item.count}</em>
            </Chip>
          ))}
        </div>
      ) : null}
      {cards.length === 0 ? (
        <p className="text-[0.88rem] text-dim">No covering sources produced a record for this place yet.</p>
      ) : (
        sections.map((section) => (
          <section className="mb-7" key={`${section.family}:${section.title}`}>
            <header>
              <p className="mb-0.5 text-[0.68rem] font-medium tracking-[0.08em] text-dim uppercase">{section.family}</p>
              <h3 className="mb-3 text-base font-medium text-white">
                {section.title} <span className="font-normal text-dim">{section.cards.length}</span>
              </h3>
            </header>
            <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-2.5 p-0">
              {section.cards.map((card) => (
                <li key={card.id}>
                  <article className="min-h-37 rounded-2xl bg-elev p-3.5">
                    <p className="m-0 text-[0.92rem] font-medium text-ink">{card.source}</p>
                    <p className="mt-1 text-[0.8rem] text-muted">{card.path}</p>
                    <p className="mt-2.5 line-clamp-3 text-xs leading-normal text-dim">{card.summary}</p>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {card.tags.map((tag) => (
                        <span key={tag} className="rounded-full bg-hover px-2 py-0.5 text-[0.68rem] text-muted">
                          {tag}
                        </span>
                      ))}
                      <time className="rounded-full bg-hover px-2 py-0.5 text-[0.68rem] text-muted" dateTime={card.observedAt}>
                        {formatDate(card.observedAt)}
                      </time>
                    </div>
                  </article>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </section>
  );
}

function Chip({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      aria-selected={selected}
      className={`rounded-full px-2.5 py-1 text-xs font-medium ${
        selected ? "bg-[#1a2a1d] text-ink" : "bg-elev text-muted"
      }`}
      onClick={onClick}
      role="tab"
      type="button"
    >
      {children}
    </button>
  );
}

function groupCards(cards: SourceCard[]): { family: string; title: string; cards: SourceCard[] }[] {
  const groups = new Map<string, { family: string; title: string; cards: SourceCard[] }>();
  for (const card of cards) {
    const key = `${card.family}:${card.category}`;
    const existing = groups.get(key);
    if (existing) {
      existing.cards.push(card);
      continue;
    }
    groups.set(key, { family: card.family, title: card.category, cards: [card] });
  }
  return [...groups.values()].sort(
    (left, right) => right.cards.length - left.cards.length || left.title.localeCompare(right.title),
  );
}

interface EdgeTableProps {
  brief: Brief;
}

export function EdgeTable({ brief }: EdgeTableProps) {
  const labels = new Map<string, string>([[brief.graph.place_id, brief.address]]);
  for (const entity of brief.graph.entities) {
    labels.set(entity.id, entity.label);
  }

  return (
    <section className="mx-auto w-full max-w-[1100px]" aria-label="Tabular relations">
      <h2 className="mb-4 text-xl font-medium tracking-tight text-white">Table</h2>
      {brief.graph.edges.length === 0 ? (
        <p className="text-[0.88rem] text-dim">No related records to list yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[0.8rem] text-muted">
            <thead>
              <tr>
                {["From", "Relation", "To", "Source", "Capability", "Date"].map((heading) => (
                  <th
                    key={heading}
                    className="pr-3.5 pb-2 text-left text-[0.68rem] font-medium tracking-wide text-dim uppercase"
                  >
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {brief.graph.edges.map((edge) => (
                <tr key={edge.id} className="border-t border-line first:border-0">
                  <td className="py-2.5 pr-3.5 align-top">
                    {labels.get(edge.from_id || brief.graph.place_id) ?? edge.from_id}
                  </td>
                  <td className="py-2.5 pr-3.5 align-top">{REL_LABEL[edge.rel]}</td>
                  <td className="py-2.5 pr-3.5 align-top">{labels.get(edge.entity_id) ?? edge.entity_id}</td>
                  <td className="py-2.5 pr-3.5 align-top">{edge.origin || edge.source}</td>
                  <td className="py-2.5 pr-3.5 align-top">{edge.capability.replaceAll("_", " ")}</td>
                  <td className="py-2.5 pr-3.5 align-top">
                    <time className="font-mono text-[0.72rem] text-dim" dateTime={edge.observed_at}>
                      {formatDate(edge.observed_at)}
                    </time>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

interface AnomalyCalloutProps {
  flags: string[];
}

function AnomalyCallout({ flags }: AnomalyCalloutProps) {
  if (flags.length === 0) {
    return null;
  }

  return (
    <aside className="mt-5 rounded-[20px] bg-[#1a0b0b] px-4 py-3.5" aria-label="Anomaly flags">
      <p className="mb-2 text-[0.78rem] text-danger">Anomalies</p>
      <ul className="m-0 list-disc pl-4.5">
        {flags.map((flag) => (
          <li key={flag} className="text-[0.88rem] leading-normal text-ink">
            {flag}
          </li>
        ))}
      </ul>
    </aside>
  );
}

interface ModulePanelProps {
  module: BriefModule;
  entities: GraphEntity[];
}

function ModulePanel({ module, entities }: ModulePanelProps) {
  return (
    <article className="rounded-[20px] bg-elev px-4.5 py-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="m-0 text-[0.95rem] font-medium tracking-tight text-white">{module.title}</h2>
          <p className="mt-1 text-[0.78rem] leading-normal text-muted">{module.trail}</p>
        </div>
        <span
          className={`shrink-0 text-[0.68rem] font-medium tracking-wide uppercase ${
            module.status === "answered" ? "text-ink" : "text-dim"
          }`}
        >
          {STATUS_LABEL[module.status]}
        </span>
      </div>

      <p className="mt-3.5 text-[0.88rem] leading-normal text-ink">{module.summary}</p>

      {entities.length > 0 ? (
        <ul className="mt-3 flex flex-wrap gap-1.5 p-0">
          {entities.map((entity) => (
            <li key={entity.id} className="rounded-full bg-hover px-2.5 py-1 text-xs text-muted">
              {entity.label}
            </li>
          ))}
        </ul>
      ) : null}

      {module.signals.length > 0 ? (
        <ol className="mt-3.5 list-none p-0">
          {module.signals.slice(0, 3).map((signal, index) => (
            <li
              key={`${signal.source}-${signal.observed_at}-${index}`}
              className="grid gap-1 border-t border-line pt-2.5 text-[0.8rem] leading-normal text-muted first:border-0 first:pt-0"
            >
              <time className="font-mono text-[0.72rem] text-dim" dateTime={signal.observed_at}>
                {formatDate(signal.observed_at)}
              </time>
              <span>{signal.summary}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </article>
  );
}

const DEFAULT_VISIBLE_COUNT = 5;

interface TimelineSignal extends Signal {
  categoryLabel: string;
}

interface SignalTimelineProps {
  brief: Brief;
}

function SignalTimeline({ brief }: SignalTimelineProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const signals = useMemo(() => flattenSignals(brief), [brief]);
  const visibleSignals = isExpanded ? signals : signals.slice(0, DEFAULT_VISIBLE_COUNT);
  const hasMore = signals.length > DEFAULT_VISIBLE_COUNT;

  return (
    <section className="mt-8" aria-label="Signal timeline">
      <div className="mb-2 flex items-baseline justify-between gap-4">
        <h2 className="m-0 text-sm font-medium text-muted">Signals</h2>
        <span className="text-[0.78rem] text-dim">{signals.length}</span>
      </div>

      {signals.length === 0 ? (
        <p className="mt-2 text-[0.88rem] text-dim">No signals for this location.</p>
      ) : (
        <ol className="m-0 list-none p-0">
          {visibleSignals.map((signal, index) => (
            <li
              className="grid grid-cols-1 gap-1.5 border-t border-line py-3.5 first:border-0 min-[800px]:grid-cols-[110px_100px_minmax(0,1fr)_150px] min-[800px]:items-baseline min-[800px]:gap-4"
              key={`${signal.source}-${signal.observed_at}-${index}`}
            >
              <span className={`font-mono text-xs ${signal.is_anomaly ? "text-danger" : "text-dim"}`}>
                {signal.source}
              </span>
              <time className="font-mono text-xs text-dim" dateTime={signal.observed_at}>
                {formatDate(signal.observed_at)}
              </time>
              <p className="m-0 text-[0.9rem] leading-normal text-ink">{signal.summary}</p>
              <span className="font-mono text-xs text-dim min-[800px]:text-right">{signal.categoryLabel}</span>
            </li>
          ))}
        </ol>
      )}

      {hasMore ? (
        <button
          className="mt-2 bg-transparent p-0 text-[0.82rem] text-muted hover:text-ink"
          onClick={() => setIsExpanded((expanded) => !expanded)}
          type="button"
        >
          {isExpanded ? "Show less" : `Show all ${signals.length}`}
        </button>
      ) : null}
    </section>
  );
}

function flattenSignals(brief: Brief): TimelineSignal[] {
  return brief.modules
    .flatMap((module) => module.signals.map((signal) => ({ ...signal, categoryLabel: module.title })))
    .sort((first, second) => Date.parse(second.observed_at) - Date.parse(first.observed_at));
}

interface BriefViewProps {
  brief: Brief;
  location: Location | null;
}

export function BriefView({ brief, location }: BriefViewProps) {
  const latitude = formatCoordinate(location?.latitude);
  const longitude = formatCoordinate(location?.longitude);
  const coordinates =
    latitude && longitude ? `${latitude}, ${longitude}` : "Coordinates unresolved";
  const entitiesById = new Map(brief.graph.entities.map((entity) => [entity.id, entity]));

  return (
    <article className="mx-auto mb-8 w-full max-w-[860px]" aria-label="Place overview">
      <header className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <div>
          <p
            className={`mb-2 text-xs font-medium tracking-wide uppercase ${
              brief.place_class_assumed ? "text-dim" : "text-muted"
            }`}
          >
            {brief.place_class_label}
            {brief.place_class_assumed ? " · assumed" : ""}
          </p>
          <h1 className="m-0 text-[clamp(1.5rem,3vw,2.25rem)] leading-[1.05] font-medium tracking-tight text-white">
            {brief.address || location?.address}
          </h1>
          <p className="mt-2 text-[0.78rem] text-muted">{coordinates}</p>
          <div className="mt-2.5">
            <StreetView location={location} />
          </div>
        </div>
        <dl className="m-0 flex gap-6 sm:justify-end sm:text-right">
          <div>
            <dt className="text-[0.72rem] text-dim">Generated</dt>
            <dd className="mt-0.5 text-[0.82rem] text-muted">{formatGeneratedAt(brief.generated_at)}</dd>
          </div>
          <div>
            <dt className="text-[0.72rem] text-dim">Signals</dt>
            <dd className="mt-0.5 text-[0.82rem] text-muted">{brief.signal_count}</dd>
          </div>
        </dl>
      </header>

      <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink">{brief.narrative}</p>

      {brief.place_class_reasons.length > 0 ? (
        <ul className="mt-3 flex list-none flex-wrap gap-2 p-0">
          {brief.place_class_reasons.map((reason, index) => (
            <li key={`${reason}-${index}`} className="text-xs text-dim">
              {reason}
            </li>
          ))}
        </ul>
      ) : null}

      {brief.business_license_coverage_note ? (
        <p className="mt-3 text-[0.88rem] text-muted">{brief.business_license_coverage_note}</p>
      ) : null}

      <AnomalyCallout flags={brief.anomaly_flags} />

      <section className="mt-7 grid grid-cols-1 gap-2.5 sm:grid-cols-2" aria-label="Place trails">
        {brief.modules.map((module) => (
          <ModulePanel
            key={module.id}
            module={module}
            entities={entitiesFor(module.entity_ids, entitiesById)}
          />
        ))}
      </section>

      <SignalTimeline brief={brief} />
    </article>
  );
}

function entitiesFor(ids: string[], entitiesById: Map<string, GraphEntity>): GraphEntity[] {
  return ids.flatMap((id) => {
    const entity = entitiesById.get(id);
    return entity ? [entity] : [];
  });
}
