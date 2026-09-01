import { formatDate } from "../format";
import type {
  Brief,
  GraphBeat,
  GraphBridge,
  GraphEdge,
  GraphEntity,
  GraphThought,
  ModuleStatus,
  Signal,
  SourceNote,
} from "../api/types";
import { STATUS_LABEL } from "../api/types";

const ENTITY_CAP = 5;
const FACET_CAP = 2;

export type WorkspaceRole = "place" | "trail" | "facet" | "entity" | "more" | "thought";

/** pin = here, file = on-record, near = street, gap = unwired, think/watch = AI reading */
export type NodeTone = "pin" | "file" | "near" | "gap" | "think" | "watch";

export interface WorkspaceNode {
  id: string;
  role: WorkspaceRole;
  tone: NodeTone;
  title: string;
  body: string;
  tag: string;
  meta?: string;
  watch?: boolean;
  confidence: number | null;
  focus?: string;
  when?: string;
  origin?: string;
  note?: string;
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

function trailId(moduleId: string): string {
  return `trail:${moduleId}`;
}

function facetId(moduleId: string, key: string): string {
  return `facet:${moduleId}:${key}`;
}

function moreId(moduleId: string, key = ""): string {
  return key ? `more:${moduleId}:${key}` : `more:${moduleId}`;
}

function entityNodeId(facetKey: string, entityId: string): string {
  return `${facetKey}:${entityId}`;
}

export function buildWorkspaceGraph(brief: Brief): WorkspaceGraph {
  const entities = new Map(brief.graph.entities.map((entity) => [entity.id, entity]));
  const fused = indexFusion(brief);
  const nodes: WorkspaceNode[] = [
    {
      id: brief.graph.place_id,
      role: "place",
      tone: "pin",
      title: brief.address,
      body: pinCopy(fused.placeRead ?? brief.narrative),
      tag: brief.place_class_assumed
        ? `${brief.place_class_label} · assumed`
        : brief.place_class_label,
      watch: brief.anomaly_flags.length > 0,
      confidence: brief.place_class_assumed ? 0.7 : 1,
    },
  ];
  const links: WorkspaceLink[] = [];
  const nodesByEntity = new Map<string, string[]>();

  for (const module of brief.modules) {
    const moduleNodeId = trailId(module.id);
    const trailOrigin = brief.graph.edges.find((edge) => edge.capability === module.id)?.origin;
    const gapWhy = fused.gaps.get(module.id);
    const answered = module.status === "answered";
    const tone = toneOf(module.id, module.status);
    nodes.push({
      id: moduleNodeId,
      role: "trail",
      tone,
      title: module.title,
      body: answered ? (fused.trails.get(module.id) ?? module.summary) : (gapWhy ?? module.summary),
      tag: STATUS_LABEL[module.status],
      meta: answered ? trailOrigin ?? undefined : undefined,
      confidence: answered ? maxConfidence(module.signals.map((signal) => signal.confidence)) : null,
      origin: trailOrigin ?? undefined,
      note: gapWhy,
    });
    links.push({
      from: brief.graph.place_id,
      to: moduleNodeId,
      confidence: answered ? 1 : null,
      label: answered ? "on file" : module.status === "empty" ? "none" : "unwired",
    });

    const related = chronologic(
      withoutRollup(module.id, uniqueEntities(module.entity_ids, entities)),
      brief.graph.edges,
      module.id,
    );
    if (related.length === 0) {
      continue;
    }

    const chains = namedChains(groupByAttribute(related, module.signals, brief.graph.edges, module.id));
    const typed = chains.length > 1 || (chains.length === 1 && chains[0]?.key !== "records");

    const opened = shouldExpand(module.id, typed && chains.length >= 3, fused);
    const entityCap = opened ? 8 : fused.tight.has(module.id) ? 2 : ENTITY_CAP;
    const facetCap = opened ? 6 : FACET_CAP;

    if (chains.length <= 1 || !typed || chains.length > facetCap) {
      attachEntities({
        nodes,
        links,
        nodesByEntity,
        parentId: moduleNodeId,
        related,
        edges: brief.graph.edges,
        moduleId: module.id,
        tone,
        fallback: module.summary,
        beats: fused.beats,
        cap: entityCap,
      });
      continue;
    }

    for (const chain of chains) {
      const facetNodeId = facetId(module.id, chain.key);
      nodes.push({
        id: facetNodeId,
        role: "facet",
        tone,
        title: chain.title,
        body: "",
        tag: chain.family.toLowerCase(),
        meta: chain.count === 1 ? "1 named" : `${chain.count} named`,
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
        related: chronologic(chain.entities, brief.graph.edges, module.id),
        edges: brief.graph.edges,
        moduleId: module.id,
        tone,
        fallback: module.summary,
        facetKey: chain.key,
        focus: chain.title,
        summaries: chain.summaries,
        beats: fused.beats,
        cap: entityCap,
      });
    }
  }

  attachRecordedLinks(brief, links, nodesByEntity);
  attachBridges(brief, fused.bridges, nodes, links, nodesByEntity);
  attachThoughts(brief, fused.thoughts, nodes, links, nodesByEntity);

  return { nodes: dedupeNodes(nodes), links };
}

export function sourceNotes(brief: Brief): SourceNote[] {
  const seen = new Set<string>();
  const notes: SourceNote[] = [];
  const raw = brief.fusion?.sources?.length
    ? brief.fusion.sources
    : brief.graph.edges.map((edge) => ({
        origin: edge.origin || edge.source || "Public record",
        proved: edge.summary,
        when: formatDate(edge.observed_at),
        edge_id: edge.id,
      }));
  for (const note of raw) {
    if (!note.origin || seen.has(note.origin)) {
      continue;
    }
    seen.add(note.origin);
    notes.push({
      ...note,
      when: /^\d{4}-\d{2}/.test(note.when) ? formatDate(note.when) : note.when,
    });
  }
  return notes;
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
  tone: NodeTone;
  fallback: string;
  facetKey?: string;
  focus?: string;
  summaries?: Record<string, string>;
  beats?: Map<string, GraphBeat>;
  cap?: number;
}): void {
  const summaries = input.summaries ?? {};
  const visible = input.related.slice(0, input.cap ?? ENTITY_CAP);
  const hidden = input.related.length - visible.length;

  for (const entity of visible) {
    const entityEdges = edgesFor(input.edges, entity.id, input.moduleId);
    const beat = input.beats?.get(`${input.moduleId}:${entity.id}`);
    const nodeId = input.facetKey ? entityNodeId(input.facetKey, entity.id) : entity.id;
    const origin = entityEdges[0]?.origin ?? undefined;
    input.nodes.push({
      id: nodeId,
      role: "entity",
      tone: input.tone,
      title: entity.label,
      body: beat?.line ?? summaries[entity.id] ?? entityEdges[0]?.summary ?? input.fallback,
      tag: entity.kind === "context" ? "nearby" : entity.kind,
      meta: whisper(beat?.when, origin),
      confidence: maxConfidence(entityEdges.map((edge) => edge.confidence)),
      focus: input.focus,
      when: beat?.when,
      origin,
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
      tone: input.tone,
      title: input.focus ? `${hidden} more of this type` : `${hidden} more records`,
      body: "",
      tag: "overview",
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
  const incident = text(signal?.value, "incident_category");
  if (incident || edge?.source === "crime_nearby") {
    return {
      key: slug(incident ?? "nearby"),
      title: incident ?? "Nearby incidents",
      family: "Neighborhood",
    };
  }
  return { key: "records", title: "Records", family: "Records" };
}

function edgesFor(edges: GraphEdge[], entityId: string, moduleId: string): GraphEdge[] {
  return edges.filter((edge) => edge.entity_id === entityId && edge.capability === moduleId);
}

function latest(edges: GraphEdge[], entityId: string, moduleId: string): number {
  return Math.max(0, ...edgesFor(edges, entityId, moduleId).map((edge) => Date.parse(edge.observed_at) || 0));
}

function indexFusion(brief: Brief): {
  placeRead: string | undefined;
  trails: Map<string, string>;
  beats: Map<string, GraphBeat>;
  expand: Set<string>;
  tight: Set<string>;
  gaps: Map<string, string>;
  bridges: GraphBridge[];
  thoughts: GraphThought[];
} {
  const trails = new Map<string, string>();
  const beats = new Map<string, GraphBeat>();
  for (const trail of brief.fusion?.trails ?? []) {
    trails.set(trail.module_id, trail.headline);
    for (const beat of trail.beats) {
      const edge = brief.graph.edges.find((item) => item.id === beat.edge_id);
      if (edge) {
        beats.set(`${trail.module_id}:${edge.entity_id}`, beat);
      }
    }
  }
  const expand = new Set(brief.fusion?.plan?.expand ?? []);
  expand.add("neighborhood");
  const gaps = new Map<string, string>();
  for (const gap of brief.fusion?.gaps ?? []) {
    gaps.set(gap.module_id, gap.why);
  }
  return {
    placeRead: brief.fusion?.place_read,
    trails,
    beats,
    expand,
    tight: new Set(brief.fusion?.plan?.tight ?? []),
    gaps,
    bridges: brief.fusion?.bridges ?? [],
    thoughts: brief.fusion?.thoughts ?? [],
  };
}

function attachRecordedLinks(
  brief: Brief,
  links: WorkspaceLink[],
  nodesByEntity: Map<string, string[]>,
): void {
  const seen = new Set(links.map((link) => `${link.from}->${link.to}`));
  for (const edge of brief.graph.edges) {
    if (!edge.from_id || edge.from_id === brief.graph.place_id) {
      continue;
    }
    for (const from of nodesByEntity.get(edge.from_id) ?? []) {
      for (const to of nodesByEntity.get(edge.entity_id) ?? []) {
        const key = `${from}->${to}`;
        if (from === to || seen.has(key)) {
          continue;
        }
        seen.add(key);
        links.push({ from, to, confidence: edge.confidence, label: percent(edge.confidence) });
      }
    }
  }
}

function attachBridges(
  brief: Brief,
  bridges: GraphBridge[],
  nodes: WorkspaceNode[],
  links: WorkspaceLink[],
  nodesByEntity: Map<string, string[]>,
): void {
  const entities = new Map(brief.graph.entities.map((entity) => [entity.id, entity]));
  for (const bridge of bridges) {
    ensureEntityNode(brief, bridge.from_id, nodes, links, nodesByEntity, entities);
    ensureEntityNode(brief, bridge.to_id, nodes, links, nodesByEntity, entities);
    const fromIds = nodesByEntity.get(bridge.from_id) ?? [];
    const toIds = nodesByEntity.get(bridge.to_id) ?? [];
    const note = bridge.why;
    for (const id of [...fromIds, ...toIds]) {
      const node = nodes.find((item) => item.id === id);
      if (node && !node.note) {
        node.note = note;
      }
    }
  }
}

function attachThoughts(
  brief: Brief,
  thoughts: GraphThought[],
  nodes: WorkspaceNode[],
  links: WorkspaceLink[],
  nodesByEntity: Map<string, string[]>,
): void {
  const entities = new Map(brief.graph.entities.map((entity) => [entity.id, entity]));
  for (const [index, thought] of thoughts.slice(0, 4).entries()) {
    if (entities.has(thought.from_id)) {
      ensureEntityNode(brief, thought.from_id, nodes, links, nodesByEntity, entities);
    }
    if (thought.to_id && entities.has(thought.to_id)) {
      ensureEntityNode(brief, thought.to_id, nodes, links, nodesByEntity, entities);
    }
    const from = resolveEnd(thought.from_id, brief, nodes, nodesByEntity);
    if (!from) {
      continue;
    }
    const id = `thought:${thought.kind}:${thought.from_id}:${thought.to_id}:${index}`;
    const to = thought.to_id ? resolveEnd(thought.to_id, brief, nodes, nodesByEntity) : null;
    nodes.push({
      id,
      role: "thought",
      tone: thought.kind === "watch" ? "watch" : "think",
      title: thought.line,
      body: "",
      tag: thought.kind === "watch" ? "watch" : "thought",
      watch: thought.kind === "watch",
      confidence: null,
    });
    if (to && to !== from) {
      spliceBetween(links, from, id, to);
    } else {
      const inbound = [...links].reverse().find((link) => link.to === from);
      if (inbound) {
        spliceBetween(links, inbound.from, id, from);
      } else {
        links.push({ from, to: id, confidence: null, label: thought.kind });
      }
    }
    const extras = [...(thought.also_ids ?? [])];
    if (thought.from_id === "neighborhood" && nodes.some((node) => node.id === trailId("business_activity"))) {
      extras.push("business_activity");
    }
    for (const extra of extras) {
      const also = resolveEnd(extra, brief, nodes, nodesByEntity);
      if (!also || also === from || also === to || also === id) {
        continue;
      }
      if (links.some((link) => link.from === id && link.to === also)) {
        continue;
      }
      links.push({ from: id, to: also, confidence: null, label: "thought" });
    }
  }
}

function spliceBetween(links: WorkspaceLink[], from: string, mid: string, to: string): void {
  dropLink(links, from, to);
  links.push({ from, to: mid, confidence: null, label: "thought" });
  links.push({ from: mid, to, confidence: null, label: "thought" });
}

function dropLink(links: WorkspaceLink[], from: string, to: string): void {
  const index = links.findIndex((link) => link.from === from && link.to === to);
  if (index >= 0) {
    links.splice(index, 1);
  }
}

function resolveEnd(
  id: string,
  brief: Brief,
  nodes: WorkspaceNode[],
  nodesByEntity: Map<string, string[]>,
): string | null {
  if (id === brief.graph.place_id || id === "place") {
    return brief.graph.place_id;
  }
  const mapped = nodesByEntity.get(id);
  if (mapped?.[0]) {
    return mapped[0];
  }
  const trail = trailId(id);
  if (nodes.some((node) => node.id === trail)) {
    return trail;
  }
  return nodes.some((node) => node.id === id) ? id : null;
}

function ensureEntityNode(
  brief: Brief,
  entityId: string,
  nodes: WorkspaceNode[],
  links: WorkspaceLink[],
  nodesByEntity: Map<string, string[]>,
  entities: Map<string, GraphEntity>,
): void {
  if ((nodesByEntity.get(entityId) ?? []).length > 0) {
    return;
  }
  const entity = entities.get(entityId);
  const edge = brief.graph.edges.find((item) => item.entity_id === entityId);
  if (!entity || !edge) {
    return;
  }
  const parentId = trailId(edge.capability);
  if (!nodes.some((node) => node.id === parentId)) {
    return;
  }
  nodes.push({
    id: entity.id,
    role: "entity",
    tone: toneOf(edge.capability, "answered", entity.kind),
    title: entity.label,
    body: edge.summary,
    tag: entity.kind === "context" ? "nearby" : entity.kind,
    meta: whisper(edge.observed_at, edge.origin ?? undefined),
    confidence: edge.confidence,
    origin: edge.origin ?? undefined,
    when: edge.observed_at,
  });
  links.push({
    from: parentId,
    to: entity.id,
    confidence: edge.confidence,
    label: percent(edge.confidence),
  });
  nodesByEntity.set(entityId, [entity.id]);
}

function shouldExpand(moduleId: string, dense: boolean, fused: ReturnType<typeof indexFusion>): boolean {
  if (fused.tight.has(moduleId) && !fused.expand.has(moduleId)) {
    return false;
  }
  return dense || fused.expand.has(moduleId);
}

function chronologic(entities: GraphEntity[], edges: GraphEdge[], moduleId: string): GraphEntity[] {
  return [...entities].sort(
    (left, right) => latest(edges, left.id, moduleId) - latest(edges, right.id, moduleId),
  );
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

function withoutRollup(moduleId: string, related: GraphEntity[]): GraphEntity[] {
  if (moduleId !== "neighborhood") {
    return related;
  }
  const slices = related.filter((entity) => entity.label !== "Nearby incidents");
  return slices.length > 0 ? slices : related;
}

function namedChains(chains: AttributeChain[]): AttributeChain[] {
  const named = chains.filter((chain) => chain.key !== "records" && chain.key !== "nearby");
  return named.length > 0 ? named : chains;
}

function pinCopy(text: string): string {
  const sentences = text.match(/[^.!?]+[.!?]+/g)?.map((part) => part.trim()) ?? [];
  const used = sentences.length > 0 ? sentences.slice(0, 2).join(" ") : text;
  const clean = used.replace(/\s+/g, " ").trim();
  if (clean.length <= 180) {
    return clean;
  }
  return `${clean.slice(0, 179).replace(/\s+\S*$/, "")}…`;
}

function toneOf(moduleId: string, status: ModuleStatus, kind?: string): NodeTone {
  if (status === "uncovered" || status === "empty") {
    return "gap";
  }
  if (moduleId === "neighborhood" || kind === "context") {
    return "near";
  }
  return "file";
}

function whisper(when?: string, origin?: string): string | undefined {
  const parts = [when ? formatDate(when) : "", origin ?? ""].filter(Boolean);
  return parts.length ? parts.join(" · ") : undefined;
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
