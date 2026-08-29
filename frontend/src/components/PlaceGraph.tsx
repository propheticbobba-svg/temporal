import { useMemo, useState } from "react";

import { usePanZoom } from "../hooks/usePanZoom";
import { computePlaceDagLayout } from "../lib/dagLayout";
import type { WorkspaceGraph, WorkspaceNode } from "../lib/workspaceGraph";
import styles from "./PlaceGraph.module.css";

interface PlaceGraphProps {
  graph: WorkspaceGraph;
  onOpenSources: (focus?: string) => void;
}

export default function PlaceGraph({ graph, onOpenSources }: PlaceGraphProps) {
  const [activeId, setActiveId] = useState<string | null>(null);
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
        { direction: "vertical", sizes },
      ),
    [graph, sizes],
  );
  const nodeById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);
  const linkByPair = useMemo(
    () => new Map(graph.links.map((link) => [`${link.from}->${link.to}`, link])),
    [graph.links],
  );
  const neighbors = useMemo(() => adjacency(graph), [graph]);
  const pan = usePanZoom(layout.width, layout.height, graph.nodes[0]?.id ?? "");

  return (
    <div
      ref={pan.viewportRef}
      className={styles.viewport}
      aria-label="Place graph"
      data-panning={pan.panning}
      onPointerDown={pan.onPointerDown}
      onPointerMove={pan.onPointerMove}
      onPointerUp={pan.onPointerUp}
      onPointerCancel={pan.onPointerUp}
      onDoubleClick={pan.fit}
    >
      <div
        className={styles.world}
        style={{
          width: layout.width,
          height: layout.height,
          transform: `translate(${pan.view.x}px, ${pan.view.y}px) scale(${pan.view.k})`,
        }}
      >
        <svg className={styles.edges} width={layout.width} height={layout.height}>
          {layout.edges.map((edge) => {
            const meta = linkByPair.get(`${edge.from}->${edge.to}`);
            const active = activeId === null || edge.from === activeId || edge.to === activeId;
            return (
              <g key={`${edge.from}-${edge.to}`} data-active={active}>
                <path
                  className={styles.edge}
                  d={curve(edge.sourceX, edge.sourceY, edge.targetX, edge.targetY)}
                />
                {meta?.label ? (
                  <text className={styles.edgeLabel} x={(edge.sourceX + edge.targetX) / 2} y={(edge.sourceY + edge.targetY) / 2 - 4}>
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
              className={styles.card}
              data-active={activeId === null || activeId === node.id || Boolean(neighbors.get(activeId)?.has(node.id))}
              data-role={node.role}
              onClick={() => {
                if (pan.consumeClick()) {
                  return;
                }
                if (node.role === "more") {
                  onOpenSources(node.focus);
                  return;
                }
                setActiveId((current) => (current === node.id ? null : node.id));
              }}
              style={{ left: box.x, top: box.y, width: box.width, height: box.height }}
            >
              <h3 className={styles.title}>{node.title}</h3>
              <p className={styles.body}>{node.body}</p>
              <footer>
                <span className={styles.tag}>{node.tag}</span>
                {node.confidence != null ? (
                  <span className={styles.score}>{Math.round(node.confidence * 100)}%</span>
                ) : null}
              </footer>
            </article>
          );
        })}
      </div>
      <div className={styles.tools}>
        <p>Drag to pan · scroll to zoom</p>
        <button onClick={pan.fit} type="button">
          Recenter
        </button>
      </div>
    </div>
  );
}

function adjacency(graph: WorkspaceGraph): Map<string, Set<string>> {
  const next = new Map<string, Set<string>>();
  for (const link of graph.links) {
    const from = next.get(link.from) ?? new Set<string>();
    const to = next.get(link.to) ?? new Set<string>();
    from.add(link.to);
    to.add(link.from);
    next.set(link.from, from);
    next.set(link.to, to);
  }
  return next;
}

function sizeFor(node: WorkspaceNode): { width: number; height: number } {
  if (node.role === "place") {
    return { width: 360, height: 132 };
  }
  if (node.role === "facet") {
    return { width: 220, height: 96 };
  }
  if (node.role === "more") {
    return { width: 200, height: 84 };
  }
  return { width: 240, height: 112 };
}

function curve(x1: number, y1: number, x2: number, y2: number): string {
  const mid = (y1 + y2) / 2;
  return `M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`;
}
