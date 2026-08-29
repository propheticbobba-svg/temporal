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
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
}

export interface DagLayout {
  nodes: DagNodeBox[];
  edges: DagEdgePath[];
  width: number;
  height: number;
}

const DEFAULT_SIZE: NodeSize = { width: 280, height: 118 };
const RANK_GAP = 56;
const NODE_GAP = 22;
const CHAIN_GAP = 12;
const PADDING = 48;

export function computePlaceDagLayout(
  rootId: string,
  nodeIds: string[],
  links: DagLink[],
  options?: {
    direction?: "horizontal" | "vertical";
    sizes?: Record<string, NodeSize>;
    defaultSize?: NodeSize;
    rankGap?: number;
    nodeGap?: number;
    padding?: number;
  },
): DagLayout {
  const direction = options?.direction ?? "vertical";
  const defaultSize = options?.defaultSize ?? DEFAULT_SIZE;
  const sizes = options?.sizes ?? {};
  const rankGap = options?.rankGap ?? RANK_GAP;
  const nodeGap = options?.nodeGap ?? NODE_GAP;
  const padding = options?.padding ?? PADDING;
  const uniqueLinks = dedupeLinks(links.filter((link) => link.from !== link.to));
  const sizeOf = (id: string): NodeSize => sizes[id] ?? defaultSize;

  if (direction === "horizontal") {
    return packRanks(rootId, nodeIds, uniqueLinks, sizeOf, defaultSize, rankGap, nodeGap, padding, "horizontal");
  }

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
    if (kids.some((kid) => (children.get(kid) ?? []).length > 0)) {
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
      const total = kids.reduce((sum, kid) => sum + (span.get(kid)?.width ?? sizeOf(kid).width), 0) + nodeGap * (kids.length - 1);
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

  const right = Math.max(defaultSize.width, ...nodes.map((node) => node.x + node.width), padding + rootSpan.width);
  const bottom = Math.max(defaultSize.height, ...nodes.map((node) => node.y + node.height), padding + rootSpan.height);

  return {
    nodes,
    edges: attachEdges(links, byId, "vertical"),
    width: right + padding,
    height: bottom + padding,
  };
}

function packRanks(
  rootId: string,
  nodeIds: string[],
  links: DagLink[],
  sizeOf: (id: string) => NodeSize,
  defaultSize: NodeSize,
  rankGap: number,
  nodeGap: number,
  padding: number,
  direction: "horizontal",
): DagLayout {
  const ranks = longestPathRanks(rootId, nodeIds, links);
  const nodesByRank = new Map<number, string[]>();

  for (const id of nodeIds) {
    const rank = ranks.get(id) ?? 1;
    const bucket = nodesByRank.get(rank) ?? [];
    bucket.push(id);
    nodesByRank.set(rank, bucket);
  }

  const maxRank = Math.max(0, ...nodesByRank.keys());
  const rows = Array.from({ length: maxRank + 1 }, (_, rank) => nodesByRank.get(rank) ?? []);
  const colWidths = rows.map((row) => Math.max(...row.map((id) => sizeOf(id).width), defaultSize.width));
  const colHeights = rows.map((row) => {
    const heights = row.map((id) => sizeOf(id).height);
    return heights.reduce((sum, height) => sum + height, 0) + Math.max(0, row.length - 1) * nodeGap;
  });
  const width = padding * 2 + colWidths.reduce((sum, value) => sum + value, 0) + Math.max(0, rows.length - 1) * rankGap;
  const height = padding * 2 + Math.max(defaultSize.height, ...colHeights);
  const nodes: DagNodeBox[] = [];
  const byId = new Map<string, DagNodeBox>();
  let x = padding;
  rows.forEach((row, rank) => {
    const colHeight = colHeights[rank] ?? defaultSize.height;
    let y = (height - colHeight) / 2;
    row.forEach((id, order) => {
      const size = sizeOf(id);
      const box: DagNodeBox = {
        id,
        rank,
        order,
        width: size.width,
        height: size.height,
        x,
        y,
      };
      nodes.push(box);
      byId.set(id, box);
      y += size.height + nodeGap;
    });
    x += (colWidths[rank] ?? defaultSize.width) + rankGap;
  });
  return {
    nodes,
    edges: attachEdges(links, byId, direction),
    width,
    height,
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

function attachEdges(
  links: DagLink[],
  byId: Map<string, DagNodeBox>,
  direction: "horizontal" | "vertical",
): DagEdgePath[] {
  return links.flatMap((link) => {
    const from = byId.get(link.from);
    const to = byId.get(link.to);
    if (!from || !to) {
      return [];
    }
    if (direction === "vertical") {
      const downward = to.y >= from.y;
      return [
        {
          from: link.from,
          to: link.to,
          sourceX: from.x + from.width / 2,
          sourceY: downward ? from.y + from.height : from.y,
          targetX: to.x + to.width / 2,
          targetY: downward ? to.y : to.y + to.height,
        },
      ];
    }
    return [
      {
        from: link.from,
        to: link.to,
        sourceX: from.x + from.width,
        sourceY: from.y + from.height / 2,
        targetX: to.x,
        targetY: to.y + to.height / 2,
      },
    ];
  });
}

function longestPathRanks(
  rootId: string,
  nodeIds: string[],
  links: DagLink[],
): Map<string, number> {
  const ranks = new Map<string, number>();
  const visiting = new Set<string>();

  function walk(id: string): number {
    if (visiting.has(id)) {
      return ranks.get(id) ?? 0;
    }
    visiting.add(id);
    let rank = id === rootId ? 0 : 1;
    for (const link of links) {
      if (link.to === id && link.from !== id) {
        rank = Math.max(rank, walk(link.from) + 1);
      }
    }
    visiting.delete(id);
    ranks.set(id, rank);
    return rank;
  }

  for (const id of nodeIds) {
    walk(id);
  }
  if (!ranks.has(rootId)) {
    ranks.set(rootId, 0);
  }
  return ranks;
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
