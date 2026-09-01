from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, Field, JsonValue

JsonObject: TypeAlias = dict[str, JsonValue]
RawRow: TypeAlias = Mapping[str, object]
SignalType: TypeAlias = Literal["activity", "anomaly", "baseline", "trend"]


class LocationInput(BaseModel):
    address: str = Field(min_length=1)
    latitude: float | None = None
    longitude: float | None = None


class SignalCreate(BaseModel):
    source: str = Field(min_length=1)
    signal_type: SignalType
    observed_at: datetime
    value: JsonObject
    summary: str = Field(min_length=1)
    is_anomaly: bool
    confidence: float = Field(ge=0.0, le=1.0)


class BaseIngester(ABC):
    source: str

    @abstractmethod
    async def fetch(self, location: LocationInput) -> list[SignalCreate]:
        raise NotImplementedError
