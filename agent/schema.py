from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, Field

from ingestion.schema import JsonObject, SignalType

BriefCategoryName: TypeAlias = (
    Literal[
        "physical_condition",
        "regulatory_standing",
        "operational_activity",
        "environmental_context",
    ]
)
PlaceClass: TypeAlias = Literal["residential", "commercial", "industrial", "mixed"]
ModuleStatus: TypeAlias = Literal["answered", "empty", "uncovered"]
EntityKind: TypeAlias = Literal["person", "business", "contractor", "work"]
EdgeRel: TypeAlias = Literal[
    "LIVED_AT",
    "TENANT_OF",
    "OWNED_BY",
    "OPERATED_AT",
    "LICENSED",
    "WORKED_ON",
    "SERVICED",
    "INSPECTED",
]


class BriefRequest(BaseModel):
    address: str = Field(min_length=1)


class SignalRead(BaseModel):
    source: str
    signal_type: SignalType
    observed_at: datetime
    value: JsonObject
    summary: str
    is_anomaly: bool
    confidence: float = Field(ge=0.0, le=1.0)


class CategoryBrief(BaseModel):
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    summary: str | None = None
    signals: list[SignalRead] = Field(default_factory=list)


class BriefModule(BaseModel):
    id: str
    title: str
    question: str
    trail: str
    status: ModuleStatus
    summary: str
    signals: list[SignalRead] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)


class GraphEntity(BaseModel):
    id: str
    kind: EntityKind
    label: str
    key: str


class GraphEdge(BaseModel):
    id: str
    rel: EdgeRel
    from_id: str = "place"
    entity_id: str
    capability: str
    source: str
    origin: str | None = None
    observed_at: datetime
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)


class PlaceGraph(BaseModel):
    place_id: str
    place_label: str
    entities: list[GraphEntity] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class Brief(BaseModel):
    address: str
    generated_at: datetime
    narrative: str
    anomaly_flags: list[str] = Field(default_factory=list)
    signal_count: int = Field(default=0, ge=0)
    place_class: PlaceClass
    place_class_label: str
    place_class_assumed: bool
    place_class_reasons: list[str] = Field(default_factory=list)
    modules: list[BriefModule] = Field(default_factory=list)
    graph: PlaceGraph
    physical_condition: CategoryBrief
    regulatory_standing: CategoryBrief
    operational_activity: CategoryBrief
    environmental_context: CategoryBrief
    business_license_source_count: int = Field(default=0, ge=0)
    business_license_coverage_note: str | None = None
