import logging
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from db.models import Location, Signal
from ingestion.base import BaseIngester
from ingestion.geocode import GeocodeIngester, is_compact_address
from ingestion.schema import JsonObject, LocationInput, SignalCreate

logger = logging.getLogger(__name__)


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

    key = _place_key(address)
    if key is None:
        return None

    candidates = [
        location
        for location in session.scalars(select(Location)).all()
        if _place_key(location.address) == key
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda location: (len(location.address), location.address.count(",")))


def _canonical_address(requested: str, matched: str, existing: str | None) -> str:
    compact_matched = matched if is_compact_address(matched) else requested
    if existing and is_compact_address(existing):
        return existing
    if existing and not is_compact_address(compact_matched):
        return existing
    return compact_matched if is_compact_address(compact_matched) else requested


_STREET_ALIASES = {
    "STREET": "ST",
    "AVENUE": "AVE",
    "DRIVE": "DR",
    "ROAD": "RD",
    "BOULEVARD": "BLVD",
    "LANE": "LN",
    "COURT": "CT",
    "PLACE": "PL",
    "SOUTH": "S",
    "NORTH": "N",
    "EAST": "E",
    "WEST": "W",
}
_DIRECTION = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}
_SUFFIXES = {"ST", "AVE", "DR", "RD", "BLVD", "LN", "CT", "PL", "WAY", "TER", "CIR"}
_SKIP_TOKENS = {"UNITED", "STATES", "TOWNSHIP", "COUNTY", "DISTRICT"}


def _place_key(address: str) -> tuple[str, str, str, str] | None:
    tokens = [
        _STREET_ALIASES.get(token, token)
        for token in re.sub(r"[^A-Z0-9]+", " ", address.upper()).split()
        if token not in _SKIP_TOKENS
    ]
    if not tokens:
        return None

    zip_code = ""
    if tokens[-1].isdigit() and len(tokens[-1]) == 5:
        zip_code = tokens[-1]
        tokens = tokens[:-1]
        if tokens and len(tokens[-1]) == 2 and tokens[-1].isalpha():
            tokens = tokens[:-1]

    house = next((token for token in tokens if token.isdigit()), None)
    if house is None:
        return None
    index = tokens.index(house) + 1
    direction = ""
    if index < len(tokens) and tokens[index] in _DIRECTION:
        direction = tokens[index]
        index += 1

    street: list[str] = []
    while index < len(tokens):
        token = tokens[index]
        if token in _SUFFIXES or token.isdigit():
            break
        street.append(token)
        index += 1
        if len(street) >= 4:
            break
    if not street:
        return None
    return (house, direction, " ".join(street), zip_code)


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
