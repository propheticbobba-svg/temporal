export type SignalType = "activity" | "anomaly" | "baseline" | "trend";

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

export interface Brief {
  address: string;
  generated_at: string;
  narrative: string;
  anomaly_flags: string[];
  signal_count: number;
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
