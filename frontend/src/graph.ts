import type { Brief, GraphEdge, GraphEntity, Signal } from "./types";
import { STATUS_LABEL } from "./types";

export const ENTITY_CAP = 3;
export const FACET_CAP = 2;

export type WorkspaceRole = "place" | "trail" | "facet" | "entity" | "more";

export interface WorkspaceNode {
  id: string;
  role: WorkspaceRole;
  title: string;
  body: string;
  tag: string;
  confidence: number | null;
  focus?: string;
}

export interface WorkspaceLink {
  from: string;
  to: string;
  confidence: number | null;
  label: string;
}

export interface WorkspaceGraph {
  nodes: WorkspaceNode[];
  links: WorkspaceLink[];
}

export function trailId(moduleId: string): string {
  return `trail:${moduleId}`;
}

export function facetId(moduleId: string, key: string): string {
  return `facet:${moduleId}:${key}`;
}

export function moreId(moduleId: string, key = ""): string {
  return key ? `more:${moduleId}:${key}` : `more:${moduleId}`;
}

export function entityNodeId(facetKey: string, entityId: string): string {
  return `${facetKey}:${entityId}`;
}

export function buildWorkspaceGraph(brief: Brief): WorkspaceGraph {
  const entities = new Map(brief.graph.entities.map((entity) => [entity.id, entity]));
  const nodes: WorkspaceNode[] = [
    {
      id: brief.graph.place_id,
      role: "place",
      title: brief.address,
      body: brief.narrative,
      tag: brief.place_class_assumed
        ? `${brief.place_class_label} · assumed`
        : brief.place_class_label,
      confidence: brief.place_class_assumed ? 0.7 : 1,
    },
  ];
  const links: WorkspaceLink[] = [];
  const nodesByEntity = new Map<string, string[]>();

  for (const module of brief.modules) {
    const moduleNodeId = trailId(module.id);
    nodes.push({
      id: moduleNodeId,
      role: "trail",
      title: module.title,
      body: module.summary,
      tag: STATUS_LABEL[module.status],
      confidence: module.status === "answered" ? maxConfidence(module.signals.map((signal) => signal.confidence)) : null,
    });
    links.push({
      from: brief.graph.place_id,
      to: moduleNodeId,
      confidence: module.status === "answered" ? 1 : null,
      label: module.status === "answered" ? "100%" : module.status === "empty" ? "none" : "gap",
    });

    const related = uniqueEntities(module.entity_ids, entities);
    if (related.length === 0) {
      continue;
    }

    const chains = groupByAttribute(related, module.signals, brief.graph.edges, module.id);
    const typed = chains.length > 1 || (chains.length === 1 && chains[0]?.key !== "records");
    if (typed) {
      const trail = nodes.find((node) => node.id === moduleNodeId);
      if (trail) {
        trail.body = `${chains.length} ${typeWord(chains[0]?.family)} types · ${related.length} named records.`;
      }
    }

    if (!typed || chains.length > FACET_CAP) {
      attachEntities({
        nodes,
        links,
        nodesByEntity,
        parentId: moduleNodeId,
        related,
        edges: brief.graph.edges,
        moduleId: module.id,
        fallback: module.summary,
      });
      continue;
    }

    for (const chain of chains) {
      const facetNodeId = facetId(module.id, chain.key);
      nodes.push({
        id: facetNodeId,
        role: "facet",
        title: chain.title,
        body: recordCopy(chain.family, chain.count),
        tag: chain.family.toLowerCase(),
        confidence: maxConfidence(chain.entities.flatMap((entity) =>
          edgesFor(brief.graph.edges, entity.id, module.id).map((edge) => edge.confidence),
        )),
        focus: chain.title,
      });
      links.push({
        from: moduleNodeId,
        to: facetNodeId,
        confidence: 1,
        label: String(chain.count),
      });
      attachEntities({
        nodes,
        links,
        nodesByEntity,
        parentId: facetNodeId,
        related: chain.entities,
        edges: brief.graph.edges,
        moduleId: module.id,
        fallback: module.summary,
        facetKey: chain.key,
        focus: chain.title,
        summaries: chain.summaries,
      });
    }
  }

  const seenLinks = new Set(links.map((link) => `${link.from}->${link.to}`));
  for (const edge of brief.graph.edges) {
    if (!edge.from_id || edge.from_id === brief.graph.place_id) {
      continue;
    }
    const fromIds = nodesByEntity.get(edge.from_id) ?? [];
    const toIds = nodesByEntity.get(edge.entity_id) ?? [];
    for (const from of fromIds) {
      for (const to of toIds) {
        const key = `${from}->${to}`;
        if (from === to || seenLinks.has(key)) {
          continue;
        }
        seenLinks.add(key);
        links.push({
          from,
          to,
          confidence: edge.confidence,
          label: percent(edge.confidence),
        });
      }
    }
  }

  return { nodes: dedupeNodes(nodes), links };
}

export function sourceCards(brief: Brief): SourceCard[] {
  const entities = new Map(brief.graph.entities.map((entity) => [entity.id, entity]));
  const cards = new Map<string, SourceCard>();
  const signals = new Map(
    brief.modules
      .flatMap((module) => module.signals)
      .map((signal) => [`${signal.source}\0${signal.summary}`, signal] as const),
  );

  for (const edge of brief.graph.edges) {
    const entity = entities.get(edge.entity_id);
    if (!entity) {
      continue;
    }
    const signal = signals.get(`${edge.source}\0${edge.summary}`);
    const attribute = attributeFrom(signal, edge);
    const origin = edge.origin ?? text(signal?.value, "source_name") ?? connectorLabel(edge.source);
    const id = `${edge.source}:${attribute.title}:${entity.id}`;
    const existing = cards.get(id);
    const tags = new Set(existing?.tags ?? []);
    tags.add(entity.kind);
    tags.add(edge.rel.toLowerCase().replaceAll("_", " "));
    tags.add(edge.capability.replaceAll("_", " "));
    tags.add(attribute.title);
    cards.set(id, {
      id,
      source: origin,
      connector: edge.source,
      path: entity.label,
      tags: [...tags],
      observedAt: edge.observed_at,
      summary: edge.summary,
      category: attribute.title,
      family: attribute.family,
    });
  }

  return [...cards.values()].sort((left, right) => {
    const family = left.family.localeCompare(right.family);
    if (family !== 0) {
      return family;
    }
    const category = left.category.localeCompare(right.category);
    return category !== 0 ? category : left.path.localeCompare(right.path);
  });
}

export function searchSources(cards: SourceCard[], query: string, category: string | null): SourceCard[] {
  const needle = query.trim().toLowerCase();
  return cards.filter((card) => {
    if (category && card.category !== category) {
      return false;
    }
    if (!needle) {
      return true;
    }
    return `${card.source} ${card.connector} ${card.path} ${card.category} ${card.family} ${card.tags.join(" ")} ${card.summary}`
      .toLowerCase()
      .includes(needle);
  });
}

export function sourceCategories(cards: SourceCard[]): SourceCategory[] {
  const counts = new Map<string, SourceCategory>();
  for (const card of cards) {
    const existing = counts.get(card.category);
    if (existing) {
      existing.count += 1;
      continue;
    }
    counts.set(card.category, { title: card.category, family: card.family, count: 1 });
  }
  return [...counts.values()].sort((left, right) => right.count - left.count || left.title.localeCompare(right.title));
}

export interface SourceCard {
  id: string;
  source: string;
  connector: string;
  path: string;
  tags: string[];
  observedAt: string;
  summary: string;
  category: string;
  family: string;
}

export interface SourceCategory {
  title: string;
  family: string;
  count: number;
}

interface AttributeChain {
  key: string;
  title: string;
  family: string;
  count: number;
  entities: GraphEntity[];
  summaries: Record<string, string>;
}

interface Attribute {
  key: string;
  title: string;
  family: string;
}

function attachEntities(input: {
  nodes: WorkspaceNode[];
  links: WorkspaceLink[];
  nodesByEntity: Map<string, string[]>;
  parentId: string;
  related: GraphEntity[];
  edges: GraphEdge[];
  moduleId: string;
  fallback: string;
  facetKey?: string;
  focus?: string;
  summaries?: Record<string, string>;
}): void {
  const summaries = input.summaries ?? {};
  const visible = input.related.slice(0, ENTITY_CAP);
  const hidden = input.related.length - visible.length;

  for (const entity of visible) {
    const entityEdges = edgesFor(input.edges, entity.id, input.moduleId);
    const nodeId = input.facetKey ? entityNodeId(input.facetKey, entity.id) : entity.id;
    input.nodes.push({
      id: nodeId,
      role: "entity",
      title: entity.label,
      body: summaries[entity.id] ?? entityEdges[0]?.summary ?? input.fallback,
      tag: entity.kind,
      confidence: maxConfidence(entityEdges.map((edge) => edge.confidence)),
      focus: input.focus,
    });
    input.links.push({
      from: input.parentId,
      to: nodeId,
      confidence: maxConfidence(entityEdges.map((edge) => edge.confidence)),
      label: percent(maxConfidence(entityEdges.map((edge) => edge.confidence))),
    });
    const seen = input.nodesByEntity.get(entity.id) ?? [];
    seen.push(nodeId);
    input.nodesByEntity.set(entity.id, seen);
  }

  if (hidden > 0) {
    const extraId = moreId(input.moduleId, input.facetKey ?? "");
    input.nodes.push({
      id: extraId,
      role: "more",
      title: input.focus ? `${hidden} more of this type` : `${hidden} more records`,
      body: input.focus ? `Open Sources, filtered to ${input.focus}.` : "Open Sources to read the rest of this trail.",
      tag: "sources",
      confidence: null,
      focus: input.focus,
    });
    input.links.push({
      from: input.parentId,
      to: extraId,
      confidence: null,
      label: "more",
    });
  }
}

function groupByAttribute(
  related: GraphEntity[],
  signals: Signal[],
  edges: GraphEdge[],
  moduleId: string,
): AttributeChain[] {
  const groups = new Map<string, AttributeChain>();

  for (const entity of related) {
    for (const hit of attributeHits(entity, signals, edges, moduleId)) {
      const existing = groups.get(hit.attribute.key);
      if (existing) {
        if (!existing.entities.some((item) => item.id === entity.id)) {
          existing.entities.push(entity);
          existing.count += 1;
        }
        existing.summaries[entity.id] = hit.summary;
        continue;
      }
      groups.set(hit.attribute.key, {
        key: hit.attribute.key,
        title: hit.attribute.title,
        family: hit.attribute.family,
        count: 1,
        entities: [entity],
        summaries: { [entity.id]: hit.summary },
      });
    }
  }

  for (const group of groups.values()) {
    group.entities.sort((left, right) => latest(edges, right.id, moduleId) - latest(edges, left.id, moduleId));
    group.count = group.entities.length;
  }

  return [...groups.values()].sort((left, right) => right.count - left.count || left.title.localeCompare(right.title));
}

function attributeHits(
  entity: GraphEntity,
  signals: Signal[],
  edges: GraphEdge[],
  moduleId: string,
): { attribute: Attribute; summary: string }[] {
  const matched = signalsFor(entity, signals, edges, moduleId);
  const found = new Map<string, { attribute: Attribute; summary: string }>();
  for (const signal of matched) {
    const attribute = attributeFrom(signal);
    if (attribute.key === "records") {
      continue;
    }
    found.set(attribute.key, { attribute, summary: signal.summary });
  }
  if (found.size > 0) {
    return [...found.values()];
  }
  return [{ attribute: { key: "records", title: "Records", family: "Records" }, summary: matched[0]?.summary ?? "" }];
}

function signalsFor(entity: GraphEntity, signals: Signal[], edges: GraphEdge[], moduleId: string): Signal[] {
  const summaries = new Set(edgesFor(edges, entity.id, moduleId).map((edge) => edge.summary));
  const bySummary = signals.filter((signal) => summaries.has(signal.summary));
  if (bySummary.length > 0) {
    return bySummary;
  }
  const key = normalizeLabel(entity.label);
  return signals.filter((signal) =>
    signalNames(signal).some((name) => normalizeLabel(name) === key || normalizeLabel(name) === entity.key),
  );
}

function attributeFrom(signal?: Signal, edge?: GraphEdge): Attribute {
  const licenseType = text(signal?.value, "license_type");
  if (licenseType) {
    return { key: slug(licenseType), title: licenseType, family: "Licenses" };
  }
  const permitType = text(signal?.value, "permit_type");
  if (permitType) {
    return { key: slug(permitType), title: permitType, family: "Permits" };
  }
  if (edge?.source === "biz_licenses") {
    return { key: "licenses", title: "Licenses", family: "Licenses" };
  }
  if (edge?.source === "permits") {
    return { key: "permits", title: "Permits", family: "Permits" };
  }
  return { key: "records", title: "Records", family: "Records" };
}

function edgesFor(edges: GraphEdge[], entityId: string, moduleId: string): GraphEdge[] {
  return edges.filter((edge) => edge.entity_id === entityId && edge.capability === moduleId);
}

function latest(edges: GraphEdge[], entityId: string, moduleId: string): number {
  return Math.max(0, ...edgesFor(edges, entityId, moduleId).map((edge) => Date.parse(edge.observed_at) || 0));
}

function uniqueEntities(ids: string[], entities: Map<string, GraphEntity>): GraphEntity[] {
  const seen = new Set<string>();
  const out: GraphEntity[] = [];
  for (const id of ids) {
    const entity = entities.get(id);
    if (!entity || seen.has(entity.id)) {
      continue;
    }
    seen.add(entity.id);
    out.push(entity);
  }
  return out;
}

function dedupeNodes(nodes: WorkspaceNode[]): WorkspaceNode[] {
  const seen = new Set<string>();
  return nodes.filter((node) => {
    if (seen.has(node.id)) {
      return false;
    }
    seen.add(node.id);
    return true;
  });
}

function maxConfidence(values: number[]): number | null {
  if (values.length === 0) {
    return null;
  }
  return Math.max(...values);
}

function percent(value: number | null): string {
  return value == null ? "" : `${Math.round(value * 100)}%`;
}

function recordCopy(family: string, count: number): string {
  const unit = typeWord(family);
  return count === 1 ? `1 ${unit} record of this type.` : `${count} ${unit} records of this type.`;
}

function typeWord(family?: string): string {
  if (family === "Licenses") {
    return "license";
  }
  if (family === "Permits") {
    return "permit";
  }
  return "record";
}

function connectorLabel(source: string): string {
  if (source === "biz_licenses") {
    return "Business licenses";
  }
  if (source === "permits") {
    return "Building permits";
  }
  return source.replaceAll("_", " ");
}

function text(value: Record<string, unknown> | undefined, key: string): string | null {
  const item = value?.[key];
  return typeof item === "string" && item.trim() ? item.trim() : null;
}

function signalNames(signal: Signal): string[] {
  return ["doing_business_as", "legal_name", "contractor", "contractor_name"]
    .map((key) => text(signal.value, key))
    .filter((value): value is string => Boolean(value));
}

function slug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "type";
}

function normalizeLabel(label: string): string {
  return label
    .toUpperCase()
    .replace(/[^A-Z0-9\s]/g, " ")
    .replace(/\b(INC|INCORPORATED|LLC|L\.L\.C|LTD|CORP|CORPORATION|CO|COMPANY|LP|PLLC|PC|PA)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

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

const DEFAULT_SIZE: NodeSize = { width: 280, height: 128 };
const RANK_GAP = 48;
const NODE_GAP = 24;
const CHAIN_GAP = 18;
const PADDING = 40;

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
    height: bottom + padding + 24,
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
