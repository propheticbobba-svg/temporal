from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Location, Signal
from ingestion.base import BaseIngester
from ingestion.schema import LocationInput, SignalCreate


async def ingest_location(
    session: Session,
    location_input: LocationInput,
    ingester: BaseIngester,
) -> int:
    signals = await ingester.fetch(location_input)
    if not signals:
        return 0

    location = _get_or_create_location(session, location_input)
    _persist_signals(session, location, signals)
    session.commit()
    return len(signals)


def _get_or_create_location(session: Session, location_input: LocationInput) -> Location:
    statement = select(Location).where(Location.address == location_input.address)
    location = session.scalars(statement).one_or_none()
    if location is not None:
        return location

    location = Location(
        address=location_input.address,
        latitude=location_input.latitude,
        longitude=location_input.longitude,
    )
    session.add(location)
    session.flush()
    return location


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
