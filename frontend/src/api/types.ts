export type SignalType = "activity" | "anomaly" | "baseline" | "trend";

export type PlaceClass = "residential" | "commercial" | "industrial" | "mixed";

export type ModuleStatus = "answered" | "empty" | "uncovered";

export type EntityKind = "person" | "business" | "contractor" | "work" | "context";

export type EdgeRel =
  | "LIVED_AT"
  | "TENANT_OF"
  | "OWNED_BY"
  | "OPERATED_AT"
  | "LICENSED"
  | "WORKED_ON"
  | "SERVICED"
  | "INSPECTED"
  | "NEARBY";

export interface Signal {
  source: string;
  signal_type: SignalType;
  observed_at: string;
  value: Record<string, unknown>;
  summary: string;
  is_anomaly: boolean;
  confidence: number;
}

export interface CategoryBrief {
  score: number | null;
  summary: string | null;
  signals: Signal[];
}

export interface BriefModule {
  id: string;
  title: string;
  question: string;
  trail: string;
  status: ModuleStatus;
  summary: string;
  signals: Signal[];
  entity_ids: string[];
}

export interface GraphEntity {
  id: string;
  kind: EntityKind;
  label: string;
  key: string;
}

export interface GraphEdge {
  id: string;
  rel: EdgeRel;
  from_id: string;
  entity_id: string;
  capability: string;
  source: string;
  origin?: string | null;
  observed_at: string;
  summary: string;
  confidence: number;
}

export interface PlaceGraph {
  place_id: string;
  place_label: string;
  entities: GraphEntity[];
  edges: GraphEdge[];
}

export interface GraphBeat {
  edge_id: string;
  when: string;
  line: string;
}

export interface GraphTrailFusion {
  module_id: string;
  headline: string;
  beats: GraphBeat[];
}

export interface GraphPlan {
  expand: string[];
  tight: string[];
  lead?: string | null;
}

export interface GraphGap {
  module_id: string;
  why: string;
}

export interface GraphBridge {
  from_id: string;
  to_id: string;
  why: string;
  confidence: number;
  edge_ids: string[];
}

export type ThoughtKind = "link" | "watch";

export interface GraphThought {
  kind: ThoughtKind;
  line: string;
  from_id: string;
  to_id: string;
  also_ids?: string[];
  edge_ids: string[];
}

export interface SourceNote {
  origin: string;
  proved: string;
  when: string;
  edge_id: string;
}

export interface GraphFusion {
  place_read: string;
  trails: GraphTrailFusion[];
  model: string;
  plan?: GraphPlan | null;
  sources_read?: string;
  sources?: SourceNote[];
  gaps?: GraphGap[];
  bridges?: GraphBridge[];
  thoughts?: GraphThought[];
  anomalies?: string[];
}

export interface Brief {
  address: string;
  generated_at: string;
  narrative: string;
  anomaly_flags: string[];
  signal_count: number;
  place_class: PlaceClass;
  place_class_label: string;
  place_class_assumed: boolean;
  place_class_reasons: string[];
  modules: BriefModule[];
  graph: PlaceGraph;
  physical_condition: CategoryBrief;
  regulatory_standing: CategoryBrief;
  operational_activity: CategoryBrief;
  environmental_context: CategoryBrief;
  business_license_source_count: number;
  business_license_coverage_note: string | null;
  fusion?: GraphFusion | null;
}

export interface Location {
  id: number;
  address: string;
  latitude: number | null;
  longitude: number | null;
  confidence: number | null;
}

export const STATUS_LABEL: Record<ModuleStatus, string> = {
  answered: "On record",
  empty: "None on file",
  uncovered: "Unwired",
};
