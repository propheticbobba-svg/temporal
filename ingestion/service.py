import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from db.models import Location, Signal
from ingestion.base import BaseIngester
from ingestion.geocode import GeocodeIngester
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
) -> Location:
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
    return location


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

    if location is None:
        location = Location(address=matched_address, latitude=latitude, longitude=longitude)
        session.add(location)
        session.flush()
        return location

    location.address = matched_address
    location.latitude = latitude
    location.longitude = longitude
    session.flush()
    return location


def _find_location_by_address(session: Session, address: str) -> Location | None:
    statement = select(Location).where(Location.address == address)
    return session.scalars(statement).one_or_none()


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
