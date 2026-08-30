from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .catalog import CAPABILITIES_PATH
from .fetch import (
    BaseIngester,
    BizLicensesIngester,
    GeocodeIngester,
    JsonObject,
    LocationInput,
    PermitsIngester,
    SignalCreate,
    is_compact_address,
)
from .store import Location, Signal, encode_place_key, get_settings

logger = logging.getLogger(__name__)

PlaceClass: TypeAlias = Literal["residential", "commercial", "industrial", "mixed"]
ProviderStatus: TypeAlias = Literal["live", "planned"]
CoverKind: TypeAlias = Literal["never", "always", "license_registry", "permits_configured"]

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


def load_capabilities(path: Path = CAPABILITIES_PATH) -> list[CapabilitySpec]:
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


@lru_cache
def _license_ingester() -> BizLicensesIngester:
    return BizLicensesIngester()


def _license_registry_covers(location: LocationInput) -> bool:
    return bool(_license_ingester().matching_sources(location))


class RefreshInterval(StrEnum):
    NEVER = "never"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class IngesterRegistration(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    source: str = Field(min_length=1)
    refresh_interval: RefreshInterval
    ingester: BaseIngester


STALENESS_BY_SOURCE: dict[str, RefreshInterval] = {
    "geocode": RefreshInterval.NEVER,
    "permits": RefreshInterval.WEEKLY,
    "biz_licenses": RefreshInterval.WEEKLY,
    "satellite": RefreshInterval.MONTHLY,
    "environmental": RefreshInterval.MONTHLY,
}

REGISTERED_INGESTERS: tuple[IngesterRegistration, ...] = (
    IngesterRegistration(
        source="geocode",
        refresh_interval=STALENESS_BY_SOURCE["geocode"],
        ingester=GeocodeIngester(),
    ),
    IngesterRegistration(
        source="permits",
        refresh_interval=STALENESS_BY_SOURCE["permits"],
        ingester=PermitsIngester(),
    ),
    IngesterRegistration(
        source="biz_licenses",
        refresh_interval=STALENESS_BY_SOURCE["biz_licenses"],
        ingester=BizLicensesIngester(),
    ),
)


def get_registered_ingesters() -> tuple[IngesterRegistration, ...]:
    return REGISTERED_INGESTERS


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def is_refresh_due(
    interval: RefreshInterval,
    refreshed_at: datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    if refreshed_at is None:
        return True
    if interval is RefreshInterval.NEVER:
        return False

    current = as_utc(now or datetime.now(tz=UTC))
    stamped = as_utc(refreshed_at)
    if interval is RefreshInterval.WEEKLY:
        return current - stamped >= timedelta(days=7)
    if interval is RefreshInterval.MONTHLY:
        return current - stamped >= timedelta(days=30)
    return True


class LocationResolutionError(ValueError):
    pass


async def ingest_location(
    session: Session,
    location_input: LocationInput,
    ingester: BaseIngester,
) -> int:
    signals = await ingester.fetch(location_input)
    if not signals:
        return 0

    location = _get_or_create_location(session, location_input)
    _apply_geocode_signal(location, signals)
    _persist_signals(session, location, signals)
    session.commit()
    return len(signals)


async def refresh_source(
    session: Session,
    location: Location,
    location_input: LocationInput,
    ingester: BaseIngester,
) -> bool:
    """Replace one source's signals after a successful fetch. Does not commit.

    Fetch failures leave existing facts in place so a flaky upstream cannot
    wipe a previously good brief.
    """
    try:
        signals = await ingester.fetch(location_input)
    except Exception:
        logger.exception(
            "Ingestion failed for source=%s address=%s",
            ingester.source,
            location.address,
        )
        return False

    session.execute(
        delete(Signal).where(
            Signal.location_id == location.id,
            Signal.source == ingester.source,
        )
    )
    _apply_geocode_signal(location, signals)
    _persist_signals(session, location, signals)
    session.flush()
    return True


async def resolve_location(
    session: Session,
    location_input: LocationInput,
    ingester: BaseIngester | None = None,
) -> tuple[Location, float]:
    known = _known_pin(session, location_input.address)
    if known is not None:
        logger.info("Using stored coordinates for %s", location_input.address)
        return known, 1.0

    geocode_ingester = ingester or GeocodeIngester()
    signals = await geocode_ingester.fetch(location_input)
    if not signals:
        raise LocationResolutionError(f"Unable to geocode address: {location_input.address}")

    geocode_signal = _get_geocode_signal(signals)
    if geocode_signal is None:
        raise LocationResolutionError(f"Unable to geocode address: {location_input.address}")

    matched_address = _required_str(geocode_signal.value, "matched_address")
    latitude = _required_float(geocode_signal.value, "latitude")
    longitude = _required_float(geocode_signal.value, "longitude")

    location = _upsert_resolved_location(
        session=session,
        requested_address=location_input.address,
        matched_address=matched_address,
        latitude=latitude,
        longitude=longitude,
    )
    _persist_signals(session, location, [geocode_signal])
    session.commit()
    session.refresh(location)
    return location, geocode_signal.confidence


def _get_or_create_location(session: Session, location_input: LocationInput) -> Location:
    statement = select(Location).where(Location.address == location_input.address)
    location = session.scalars(statement).one_or_none()
    if location is not None:
        if location.latitude is None and location_input.latitude is not None:
            location.latitude = location_input.latitude
        if location.longitude is None and location_input.longitude is not None:
            location.longitude = location_input.longitude
        return location

    location = Location(
        address=location_input.address,
        latitude=location_input.latitude,
        longitude=location_input.longitude,
    )
    session.add(location)
    session.flush()
    return location


def _upsert_resolved_location(
    session: Session,
    requested_address: str,
    matched_address: str,
    latitude: float,
    longitude: float,
) -> Location:
    location = _find_location_by_address(session, matched_address)
    if location is None:
        location = _find_location_by_address(session, requested_address)

    address = _canonical_address(requested_address, matched_address, None)
    if location is None:
        location = Location(address=address, latitude=latitude, longitude=longitude)
        session.add(location)
        session.flush()
        return location

    location.address = _canonical_address(requested_address, matched_address, location.address)
    location.latitude = latitude
    location.longitude = longitude
    session.flush()
    return location


def _known_pin(session: Session, address: str) -> Location | None:
    location = _find_location_by_address(session, address)
    if location is not None and location.latitude is not None and location.longitude is not None:
        return location
    return None


def _find_location_by_address(session: Session, address: str) -> Location | None:
    exact = session.scalars(select(Location).where(Location.address == address)).one_or_none()
    if exact is not None:
        return exact

    key = encode_place_key(address)
    if key is None:
        return None

    candidates = list(session.scalars(select(Location).where(Location.place_key == key)).all())
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda location: (len(location.address), location.address.count(",")),
    )


def _canonical_address(requested: str, matched: str, existing: str | None) -> str:
    compact_matched = matched if is_compact_address(matched) else requested
    if existing and is_compact_address(existing):
        return existing
    if existing and not is_compact_address(compact_matched):
        return existing
    return compact_matched if is_compact_address(compact_matched) else requested


def _apply_geocode_signal(location: Location, signals: list[SignalCreate]) -> None:
    geocode_signal = _get_geocode_signal(signals)
    if geocode_signal is None:
        return

    location.latitude = _required_float(geocode_signal.value, "latitude")
    location.longitude = _required_float(geocode_signal.value, "longitude")


def _get_geocode_signal(signals: list[SignalCreate]) -> SignalCreate | None:
    for signal in signals:
        if signal.source == "geocode":
            return signal
    return None


def _required_str(value: JsonObject, key: str) -> str:
    raw_value = value.get(key)
    if isinstance(raw_value, str) and raw_value:
        return raw_value
    raise LocationResolutionError(f"Geocode signal is missing {key}")


def _required_float(value: JsonObject, key: str) -> float:
    raw_value = value.get(key)
    if isinstance(raw_value, bool):
        raise LocationResolutionError(f"Geocode signal has invalid {key}")
    if isinstance(raw_value, int | float):
        return float(raw_value)
    raise LocationResolutionError(f"Geocode signal is missing {key}")


def _persist_signals(
    session: Session,
    location: Location,
    signals: list[SignalCreate],
) -> None:
    for signal in signals:
        session.add(
            Signal(
                location_id=location.id,
                source=signal.source,
                signal_type=signal.signal_type,
                observed_at=signal.observed_at,
                value=signal.value,
                summary=signal.summary,
                is_anomaly=signal.is_anomaly,
                confidence=signal.confidence,
            )
        )
