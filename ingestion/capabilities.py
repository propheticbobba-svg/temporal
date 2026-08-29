from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal, TypeAlias

from pydantic import BaseModel, Field, TypeAdapter

from core.config import get_settings
from ingestion.schema import LocationInput

PlaceClass: TypeAlias = Literal["residential", "commercial", "industrial", "mixed"]
ProviderStatus: TypeAlias = Literal["live", "planned"]
CoverKind: TypeAlias = Literal["never", "always", "license_registry", "permits_configured"]

DEFAULT_CAPABILITY_PATH = Path(__file__).with_name("capabilities.json")
PLACE_CLASSES: tuple[PlaceClass, ...] = (
    "residential",
    "commercial",
    "industrial",
    "mixed",
)
PLACE_CLASS_LABELS: dict[PlaceClass, str] = {
    "residential": "Residence",
    "commercial": "Commercial",
    "industrial": "Warehouse / industrial",
    "mixed": "Mixed use",
}


class CoverRule(BaseModel):
    kind: CoverKind = "never"


class ProviderSpec(BaseModel):
    id: str = Field(min_length=1)
    status: ProviderStatus
    covers: CoverRule = Field(default_factory=CoverRule)


class CapabilitySpec(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)
    trail: str = Field(min_length=1)
    place_classes: list[PlaceClass]
    edge_types: list[str] = Field(default_factory=list)
    uncovered_copy: str = Field(min_length=1)
    empty_copy: str = Field(min_length=1)
    providers: list[ProviderSpec]


def load_capabilities(path: Path = DEFAULT_CAPABILITY_PATH) -> list[CapabilitySpec]:
    payload = json.loads(path.read_text())
    return TypeAdapter(list[CapabilitySpec]).validate_python(payload)


@lru_cache
def capability_catalog() -> tuple[CapabilitySpec, ...]:
    return tuple(load_capabilities())


def capabilities_for_class(place_class: PlaceClass) -> list[CapabilitySpec]:
    return [spec for spec in capability_catalog() if place_class in spec.place_classes]


def covering_providers(spec: CapabilitySpec, location: LocationInput | None) -> list[ProviderSpec]:
    if location is None:
        return []
    return [
        provider
        for provider in spec.providers
        if provider.status == "live" and provider_covers(provider, location)
    ]


def provider_covers(provider: ProviderSpec, location: LocationInput) -> bool:
    kind = provider.covers.kind
    if kind == "never":
        return False
    if kind == "always":
        return True
    if kind == "permits_configured":
        return get_settings().permits_api_url is not None
    if kind == "license_registry":
        return _license_registry_covers(location)
    return False


def _license_registry_covers(location: LocationInput) -> bool:
    from ingestion.biz_licenses import BizLicensesIngester

    return bool(BizLicensesIngester().matching_sources(location))
