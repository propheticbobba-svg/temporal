export interface DagLink {
  from: string;
  to: string;
}

export interface NodeSize {
  width: number;
  height: number;
}

export interface DagNodeBox {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rank: number;
  order: number;
}

export interface DagEdgePath {
  from: string;
  to: string;
  kind: "tree" | "cross";
  d: string;
  points: { x: number; y: number }[];
}

export interface DagLayout {
  nodes: DagNodeBox[];
  edges: DagEdgePath[];
  width: number;
  height: number;
}

const DEFAULT_SIZE: NodeSize = { width: 300, height: 140 };
const RANK_GAP = 88;
const NODE_GAP = 56;
const CHAIN_GAP = 40;
const PADDING = 64;

export function computePlaceDagLayout(
  rootId: string,
  nodeIds: string[],
  links: DagLink[],
  options?: {
    sizes?: Record<string, NodeSize>;
    defaultSize?: NodeSize;
    rankGap?: number;
    nodeGap?: number;
    padding?: number;
  },
): DagLayout {
  const defaultSize = options?.defaultSize ?? DEFAULT_SIZE;
  const sizes = options?.sizes ?? {};
  const rankGap = options?.rankGap ?? RANK_GAP;
  const nodeGap = options?.nodeGap ?? NODE_GAP;
  const padding = options?.padding ?? PADDING;
  const uniqueLinks = dedupeLinks(links.filter((link) => link.from !== link.to));
  const sizeOf = (id: string): NodeSize => sizes[id] ?? defaultSize;
  return packChains(rootId, nodeIds, uniqueLinks, sizeOf, defaultSize, rankGap, nodeGap, padding);
}

function packChains(
  rootId: string,
  nodeIds: string[],
  links: DagLink[],
  sizeOf: (id: string) => NodeSize,
  defaultSize: NodeSize,
  rankGap: number,
  nodeGap: number,
  padding: number,
): DagLayout {
  const { children, claimed } = buildTree(rootId, nodeIds, links);
  const span = new Map<string, { width: number; height: number }>();

  function childAxis(id: string): "row" | "column" {
    const kids = children.get(id) ?? [];
    if (kids.some((kid) => (children.get(kid) ?? []).length > 0) || kids.length >= 3) {
      return "row";
    }
    return "column";
  }

  function measure(id: string): { width: number; height: number } {
    const cached = span.get(id);
    if (cached) {
      return cached;
    }
    const size = sizeOf(id);
    const kids = children.get(id) ?? [];
    if (kids.length === 0) {
      const leaf = { width: size.width, height: size.height };
      span.set(id, leaf);
      return leaf;
    }
    const childSpans = kids.map(measure);
    if (childAxis(id) === "row") {
      const width = Math.max(
        size.width,
        childSpans.reduce((sum, child) => sum + child.width, 0) + nodeGap * (kids.length - 1),
      );
      const height = size.height + rankGap + Math.max(...childSpans.map((child) => child.height));
      const box = { width, height };
      span.set(id, box);
      return box;
    }
    const width = Math.max(size.width, ...childSpans.map((child) => child.width));
    const stacked =
      childSpans.reduce((sum, child) => sum + child.height, 0) + CHAIN_GAP * Math.max(0, kids.length - 1);
    const height = size.height + rankGap + stacked;
    const box = { width, height };
    span.set(id, box);
    return box;
  }

  const rootSpan = nodeIds.includes(rootId) ? measure(rootId) : { width: defaultSize.width, height: defaultSize.height };
  const nodes: DagNodeBox[] = [];
  const byId = new Map<string, DagNodeBox>();

  function place(id: string, left: number, top: number, rank: number): void {
    const allocated = span.get(id) ?? sizeOf(id);
    const size = sizeOf(id);
    const box: DagNodeBox = {
      id,
      rank,
      order: nodes.length,
      width: size.width,
      height: size.height,
      x: left + (allocated.width - size.width) / 2,
      y: top,
    };
    nodes.push(box);
    byId.set(id, box);
    const kids = children.get(id) ?? [];
    if (kids.length === 0) {
      return;
    }
    const childTop = top + size.height + rankGap;
    if (childAxis(id) === "row") {
      const total =
        kids.reduce((sum, kid) => sum + (span.get(kid)?.width ?? sizeOf(kid).width), 0) +
        nodeGap * (kids.length - 1);
      let x = left + (allocated.width - total) / 2;
      for (const kid of kids) {
        const kidSpan = span.get(kid) ?? sizeOf(kid);
        place(kid, x, childTop, rank + 1);
        x += kidSpan.width + nodeGap;
      }
      return;
    }
    let y = childTop;
    for (const kid of kids) {
      const kidSpan = span.get(kid) ?? sizeOf(kid);
      place(kid, left + (allocated.width - kidSpan.width) / 2, y, rank + 1);
      y += kidSpan.height + CHAIN_GAP;
    }
  }

  if (nodeIds.includes(rootId)) {
    place(rootId, padding, padding, 0);
  }

  let extraX = padding;
  let extraY = padding + rootSpan.height + rankGap;
  for (const id of nodeIds) {
    if (claimed.has(id) || byId.has(id)) {
      continue;
    }
    const size = sizeOf(id);
    const box: DagNodeBox = {
      id,
      rank: 1,
      order: nodes.length,
      width: size.width,
      height: size.height,
      x: extraX,
      y: extraY,
    };
    nodes.push(box);
    byId.set(id, box);
    extraX += size.width + nodeGap;
  }

  const edges = attachEdges(links, byId, children);
  const right = Math.max(
    defaultSize.width,
    padding + rootSpan.width,
    ...nodes.map((node) => node.x + node.width),
    ...edges.map((edge) => edge.maxX),
  );
  const bottom = Math.max(
    defaultSize.height,
    padding + rootSpan.height,
    ...nodes.map((node) => node.y + node.height),
    ...edges.map((edge) => edge.maxY),
  );

  return {
    nodes,
    edges: edges.map(({ maxX: _maxX, maxY: _maxY, ...edge }) => edge),
    width: right + padding,
    height: bottom + padding + 24,
  };
}

function buildTree(
  rootId: string,
  nodeIds: string[],
  links: DagLink[],
): { children: Map<string, string[]>; claimed: Set<string> } {
  const children = new Map<string, string[]>();
  for (const id of nodeIds) {
    children.set(id, []);
  }
  const outgoing = new Map<string, string[]>();
  for (const link of links) {
    if (!nodeIds.includes(link.from) || !nodeIds.includes(link.to)) {
      continue;
    }
    const list = outgoing.get(link.from) ?? [];
    list.push(link.to);
    outgoing.set(link.from, list);
  }
  const claimed = new Set<string>(nodeIds.includes(rootId) ? [rootId] : []);
  const queue = nodeIds.includes(rootId) ? [rootId] : [];
  while (queue.length > 0) {
    const id = queue.shift();
    if (!id) {
      break;
    }
    for (const to of outgoing.get(id) ?? []) {
      if (claimed.has(to)) {
        continue;
      }
      claimed.add(to);
      children.get(id)?.push(to);
      queue.push(to);
    }
  }
  return { children, claimed };
}

interface RoutedEdge extends DagEdgePath {
  maxX: number;
  maxY: number;
}

interface Pt {
  x: number;
  y: number;
}

const CLEAR = 18;
const HIT_PAD = 8;

function attachEdges(
  links: DagLink[],
  byId: Map<string, DagNodeBox>,
  children: Map<string, string[]>,
): RoutedEdge[] {
  const tree = new Set<string>();
  const ports = new Map<string, number>();
  for (const [parent, kids] of children) {
    kids.forEach((kid, index) => {
      const key = `${parent}->${kid}`;
      tree.add(key);
      ports.set(key, index);
    });
  }

  const boxes = [...byId.values()];
  const paths: RoutedEdge[] = [];
  for (const link of links) {
    const from = byId.get(link.from);
    const to = byId.get(link.to);
    if (!from || !to) {
      continue;
    }
    const key = `${link.from}->${link.to}`;
    const kind = tree.has(key) ? "tree" : "cross";
    const kids = children.get(link.from) ?? [];
    const index = ports.get(key) ?? 0;
    const portX = from.x + from.width * ((index + 1) / (kids.length + 1));
    const points = route(from, to, boxes, kind, portX);
    const d = pathD(points);
    paths.push({
      from: link.from,
      to: link.to,
      kind,
      d,
      points,
      maxX: Math.max(...points.map((point) => point.x)),
      maxY: Math.max(...points.map((point) => point.y)),
    });
  }
  return paths;
}

function route(
  from: DagNodeBox,
  to: DagNodeBox,
  boxes: DagNodeBox[],
  kind: "tree" | "cross",
  portX: number,
): Pt[] {
  const others = boxes.filter((box) => box.id !== from.id && box.id !== to.id);
  const ends = [from, to];
  if (kind === "tree") {
    const start = { x: portX, y: from.y + from.height };
    const end = { x: to.x + to.width / 2, y: to.y };
    return via(start, end, others, ends) ?? around(start, end, others, from, to);
  }

  const pairs: Array<[Side, Side]> = [
    ["bottom", "top"],
    ["bottom", "bottom"],
    ["top", "top"],
    ["top", "bottom"],
    ["right", "left"],
    ["left", "right"],
    ["right", "top"],
    ["left", "top"],
    ["bottom", "left"],
    ["bottom", "right"],
  ];
  let best: Pt[] | null = null;
  let bestLen = Number.POSITIVE_INFINITY;
  for (const [out, inn] of pairs) {
    const points = via(port(from, out), port(to, inn), others, ends);
    if (!points) {
      continue;
    }
    const len = lengthOf(points);
    if (len < bestLen) {
      best = points;
      bestLen = len;
    }
  }
  if (best) {
    return best;
  }
  return around(port(from, "bottom"), port(to, "top"), others, from, to);
}

type Side = "top" | "bottom" | "left" | "right";

function port(box: DagNodeBox, side: Side): Pt {
  if (side === "top") {
    return { x: box.x + box.width / 2, y: box.y };
  }
  if (side === "bottom") {
    return { x: box.x + box.width / 2, y: box.y + box.height };
  }
  if (side === "left") {
    return { x: box.x, y: box.y + box.height / 2 };
  }
  return { x: box.x + box.width, y: box.y + box.height / 2 };
}

function via(start: Pt, end: Pt, others: DagNodeBox[], ends: DagNodeBox[]): Pt[] | null {
  return elbow(start, end, others, ends, "vhv") ?? elbow(start, end, others, ends, "hvh");
}

function elbow(
  start: Pt,
  end: Pt,
  others: DagNodeBox[],
  ends: DagNodeBox[],
  shape: "vhv" | "hvh",
): Pt[] | null {
  const values = shape === "vhv" ? candidateYs(start, end, others) : candidateXs(start, end, others);
  for (const value of values) {
    const points =
      shape === "vhv"
        ? tidy([start, { x: start.x, y: value }, { x: end.x, y: value }, end])
        : tidy([start, { x: value, y: start.y }, { x: value, y: end.y }, end]);
    if (!blocked(points, others, ends)) {
      return points;
    }
  }
  return null;
}

function around(start: Pt, end: Pt, others: DagNodeBox[], from: DagNodeBox, to: DagNodeBox): Pt[] {
  const ends = [from, to];
  const pack = [from, to, ...others];
  for (const pad of [CLEAR, 40, 72, 120]) {
    const left = Math.min(...pack.map((box) => box.x)) - pad;
    const right = Math.max(...pack.map((box) => box.x + box.width)) + pad;
    const top = Math.min(...pack.map((box) => box.y)) - pad;
    const bottom = Math.max(...pack.map((box) => box.y + box.height)) + pad;
    const wraps = [
      [start, { x: start.x, y: top }, { x: end.x, y: top }, end],
      [start, { x: start.x, y: bottom }, { x: end.x, y: bottom }, end],
      [start, { x: left, y: start.y }, { x: left, y: end.y }, end],
      [start, { x: right, y: start.y }, { x: right, y: end.y }, end],
      [start, { x: start.x, y: top }, { x: left, y: top }, { x: left, y: end.y }, end],
      [start, { x: start.x, y: top }, { x: right, y: top }, { x: right, y: end.y }, end],
      [start, { x: start.x, y: bottom }, { x: left, y: bottom }, { x: left, y: end.y }, end],
      [start, { x: start.x, y: bottom }, { x: right, y: bottom }, { x: right, y: end.y }, end],
    ].map(tidy);
    const clear = wraps.find((points) => !blocked(points, others, ends));
    if (clear) {
      return clear;
    }
  }
  const floor = Math.max(...pack.map((box) => box.y + box.height)) + 120;
  return tidy([start, { x: start.x, y: floor }, { x: end.x, y: floor }, end]);
}

function candidateYs(start: Pt, end: Pt, others: DagNodeBox[]): number[] {
  const x0 = Math.min(start.x, end.x);
  const x1 = Math.max(start.x, end.x);
  const raw = [start.y, end.y, start.y - CLEAR, start.y + CLEAR, end.y - CLEAR, end.y + CLEAR];
  for (const box of others) {
    if (box.x + box.width < x0 || box.x > x1) {
      continue;
    }
    raw.push(box.y - CLEAR, box.y + box.height + CLEAR);
  }
  return rankCandidates(raw, (start.y + end.y) / 2);
}

function candidateXs(start: Pt, end: Pt, others: DagNodeBox[]): number[] {
  const y0 = Math.min(start.y, end.y);
  const y1 = Math.max(start.y, end.y);
  const raw = [start.x, end.x, start.x - CLEAR, start.x + CLEAR, end.x - CLEAR, end.x + CLEAR];
  for (const box of others) {
    if (box.y + box.height < y0 || box.y > y1) {
      continue;
    }
    raw.push(box.x - CLEAR, box.x + box.width + CLEAR);
  }
  return rankCandidates(raw, (start.x + end.x) / 2);
}

function rankCandidates(raw: number[], prefer: number): number[] {
  return [...new Set(raw.map((value) => Math.round(value)))].sort(
    (a, b) => Math.abs(a - prefer) - Math.abs(b - prefer),
  );
}

function blocked(points: Pt[], others: DagNodeBox[], ends: DagNodeBox[]): boolean {
  return hitsAny(points, others) || hitsInterior(points, ends);
}

function hitsInterior(points: Pt[], boxes: DagNodeBox[]): boolean {
  for (let index = 0; index < points.length - 1; index += 1) {
    const a = points[index];
    const b = points[index + 1];
    if (Math.abs(a.x - b.x) < 0.5 && Math.abs(a.y - b.y) < 0.5) {
      continue;
    }
    for (const box of boxes) {
      if (segmentHitsInterior(a, b, box)) {
        return true;
      }
    }
  }
  return false;
}

function segmentHitsInterior(a: Pt, b: Pt, box: DagNodeBox): boolean {
  const left = box.x + 1;
  const top = box.y + 1;
  const right = box.x + box.width - 1;
  const bottom = box.y + box.height - 1;
  if (right <= left || bottom <= top) {
    return false;
  }
  if (Math.abs(a.x - b.x) < 0.5) {
    if (a.x <= left || a.x >= right) {
      return false;
    }
    return Math.min(a.y, b.y) < bottom && Math.max(a.y, b.y) > top;
  }
  if (Math.abs(a.y - b.y) < 0.5) {
    if (a.y <= top || a.y >= bottom) {
      return false;
    }
    return Math.min(a.x, b.x) < right && Math.max(a.x, b.x) > left;
  }
  return true;
}

function hitsAny(points: Pt[], others: DagNodeBox[]): boolean {
  for (let index = 0; index < points.length - 1; index += 1) {
    const a = points[index];
    const b = points[index + 1];
    if (Math.abs(a.x - b.x) < 0.5 && Math.abs(a.y - b.y) < 0.5) {
      continue;
    }
    for (const box of others) {
      if (segmentHits(a, b, box)) {
        return true;
      }
    }
  }
  return false;
}

function segmentHits(a: Pt, b: Pt, box: DagNodeBox): boolean {
  const left = box.x - HIT_PAD;
  const top = box.y - HIT_PAD;
  const right = box.x + box.width + HIT_PAD;
  const bottom = box.y + box.height + HIT_PAD;
  if (Math.abs(a.x - b.x) < 0.5) {
    const x = a.x;
    if (x < left || x > right) {
      return false;
    }
    return Math.min(a.y, b.y) < bottom && Math.max(a.y, b.y) > top;
  }
  if (Math.abs(a.y - b.y) < 0.5) {
    const y = a.y;
    if (y < top || y > bottom) {
      return false;
    }
    return Math.min(a.x, b.x) < right && Math.max(a.x, b.x) > left;
  }
  return true;
}

function tidy(points: Pt[]): Pt[] {
  const out: Pt[] = [];
  for (const point of points) {
    const last = out[out.length - 1];
    if (last && Math.abs(last.x - point.x) < 0.5 && Math.abs(last.y - point.y) < 0.5) {
      continue;
    }
    if (out.length >= 2 && last) {
      const prior = out[out.length - 2];
      if (
        (Math.abs(prior.x - last.x) < 0.5 && Math.abs(last.x - point.x) < 0.5) ||
        (Math.abs(prior.y - last.y) < 0.5 && Math.abs(last.y - point.y) < 0.5)
      ) {
        out[out.length - 1] = point;
        continue;
      }
    }
    out.push(point);
  }
  return out;
}

function lengthOf(points: Pt[]): number {
  let length = 0;
  for (let index = 0; index < points.length - 1; index += 1) {
    length += Math.abs(points[index + 1].x - points[index].x) + Math.abs(points[index + 1].y - points[index].y);
  }
  return length;
}

function pathD(points: Pt[]): string {
  if (points.length === 0) {
    return "";
  }
  if (points.length === 1) {
    return `M ${points[0].x} ${points[0].y}`;
  }
  const radius = 10;
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let index = 1; index < points.length - 1; index += 1) {
    const prev = points[index - 1];
    const curr = points[index];
    const next = points[index + 1];
    const inLen = Math.hypot(curr.x - prev.x, curr.y - prev.y);
    const outLen = Math.hypot(next.x - curr.x, next.y - curr.y);
    const corner = Math.min(radius, inLen / 2, outLen / 2);
    if (corner < 1) {
      d += ` L ${curr.x} ${curr.y}`;
      continue;
    }
    const ax = curr.x - ((curr.x - prev.x) / inLen) * corner;
    const ay = curr.y - ((curr.y - prev.y) / inLen) * corner;
    const bx = curr.x + ((next.x - curr.x) / outLen) * corner;
    const by = curr.y + ((next.y - curr.y) / outLen) * corner;
    d += ` L ${ax} ${ay} Q ${curr.x} ${curr.y} ${bx} ${by}`;
  }
  const last = points[points.length - 1];
  d += ` L ${last.x} ${last.y}`;
  return d;
}

function dedupeLinks(links: DagLink[]): DagLink[] {
  const seen = new Set<string>();
  const unique: DagLink[] = [];
  for (const link of links) {
    const key = `${link.from}->${link.to}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    unique.push(link);
  }
  return unique;
}
