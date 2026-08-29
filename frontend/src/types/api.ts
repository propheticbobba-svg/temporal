export type SignalType = "activity" | "anomaly" | "baseline" | "trend";

export type PlaceClass = "residential" | "commercial" | "industrial" | "mixed";

export type ModuleStatus = "answered" | "empty" | "uncovered";

export type EntityKind = "person" | "business" | "contractor" | "work";

export type EdgeRel =
  | "LIVED_AT"
  | "TENANT_OF"
  | "OWNED_BY"
  | "OPERATED_AT"
  | "LICENSED"
  | "WORKED_ON"
  | "SERVICED"
  | "INSPECTED";

export type CategoryKey =
  | "physical_condition"
  | "regulatory_standing"
  | "operational_activity"
  | "environmental_context";

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
}

export interface Location {
  id: number;
  address: string;
  latitude: number | null;
  longitude: number | null;
  confidence: number | null;
}

export interface ApiError {
  message: string;
  status?: number;
}

export const CATEGORIES: readonly { key: CategoryKey; label: string }[] = [
  { key: "physical_condition", label: "Physical Condition" },
  { key: "regulatory_standing", label: "Regulatory Standing" },
  { key: "operational_activity", label: "Operational Activity" },
  { key: "environmental_context", label: "Environmental Context" },
];

export const STATUS_LABEL: Record<ModuleStatus, string> = {
  answered: "On record",
  empty: "None on file",
  uncovered: "Not covered",
};

export const REL_LABEL: Record<EdgeRel, string> = {
  LIVED_AT: "lived here",
  TENANT_OF: "tenant",
  OWNED_BY: "owned",
  OPERATED_AT: "operated",
  LICENSED: "licensed",
  WORKED_ON: "worked on",
  SERVICED: "serviced",
  INSPECTED: "inspected",
};
