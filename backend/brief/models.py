from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, Field, field_validator

from ..fetch import JsonObject, SignalType
from ..place import PlaceClass

BriefCategoryName: TypeAlias = (
    Literal[
        "physical_condition",
        "regulatory_standing",
        "operational_activity",
        "environmental_context",
    ]
)
ModuleStatus: TypeAlias = Literal["answered", "empty", "uncovered"]
EntityKind: TypeAlias = Literal["person", "business", "contractor", "work", "context"]
EdgeRel: TypeAlias = Literal[
    "LIVED_AT",
    "TENANT_OF",
    "OWNED_BY",
    "OPERATED_AT",
    "LICENSED",
    "WORKED_ON",
    "SERVICED",
    "INSPECTED",
    "NEARBY",
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


class GraphBeat(BaseModel):
    edge_id: str
    when: str = ""
    line: str = ""


class GraphTrailFusion(BaseModel):
    module_id: str
    headline: str = ""
    beats: list[GraphBeat] = Field(default_factory=list)


class GraphGap(BaseModel):
    module_id: str
    why: str


class GraphBridge(BaseModel):
    from_id: str
    to_id: str
    why: str
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    edge_ids: list[str] = Field(default_factory=list)


class GraphThought(BaseModel):
    kind: Literal["link", "watch"]
    line: str
    from_id: str
    to_id: str = ""
    also_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)


class GraphPlan(BaseModel):
    expand: list[str] = Field(default_factory=list)
    tight: list[str] = Field(default_factory=list)
    lead: str | None = None

    @field_validator("expand", "tight", mode="before")
    @classmethod
    def _string_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value else []
        if isinstance(value, list):
            return [str(item) for item in value if item]
        return []


class SourceNote(BaseModel):
    origin: str
    proved: str
    when: str = ""
    edge_id: str = ""


class GraphFusion(BaseModel):
    place_read: str
    trails: list[GraphTrailFusion] = Field(default_factory=list)
    model: str = ""
    plan: GraphPlan | None = None
    sources_read: str = ""
    sources: list[SourceNote] = Field(default_factory=list)
    gaps: list[GraphGap] = Field(default_factory=list)
    bridges: list[GraphBridge] = Field(default_factory=list)
    thoughts: list[GraphThought] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)
    anomalies_judged: bool = False


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
    fusion: GraphFusion | None = None
