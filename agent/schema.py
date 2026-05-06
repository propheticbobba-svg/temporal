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


class Brief(BaseModel):
    address: str
    generated_at: datetime
    physical_condition: CategoryBrief
    regulatory_standing: CategoryBrief
    operational_activity: CategoryBrief
    environmental_context: CategoryBrief
