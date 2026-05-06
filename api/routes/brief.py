from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from agent.brief import build_brief
from agent.schema import Brief, BriefRequest
from db.models import Location, Signal
from db.session import get_session
from ingestion.base import BaseIngester
from ingestion.biz_licenses import BizLicensesIngester
from ingestion.schema import LocationInput
from ingestion.service import ingest_location
from jobs.scheduler import get_registered_ingesters

router = APIRouter(prefix="/brief", tags=["brief"])


def get_signal_ingesters() -> tuple[BaseIngester, ...]:
    return tuple(
        registration.ingester
        for registration in get_registered_ingesters()
        if registration.source != "geocode"
    )


@router.post("", response_model=Brief)
async def create_brief(
    request: BriefRequest,
    session: Annotated[Session, Depends(get_session)],
    ingesters: Annotated[tuple[BaseIngester, ...], Depends(get_signal_ingesters)],
) -> Brief:
    location_input = await _refresh_signals(session, request, ingesters)
    brief = build_brief(session, request)
    if location_input is None:
        return brief

    source_count = _business_license_source_count(location_input, ingesters)
    if source_count is None:
        return brief

    coverage_note = (
        "No configured public license source covers this location yet."
        if source_count == 0
        else None
    )
    return brief.model_copy(
        update={
            "business_license_source_count": source_count,
            "business_license_coverage_note": coverage_note,
        }
    )


async def _refresh_signals(
    session: Session,
    request: BriefRequest,
    ingesters: tuple[BaseIngester, ...],
) -> LocationInput | None:
    statement = select(Location).where(Location.address == request.address)
    location = session.scalars(statement).one_or_none()
    if location is None:
        return None

    location_input = LocationInput(
        address=location.address,
        latitude=location.latitude,
        longitude=location.longitude,
    )
    for ingester in ingesters:
        _delete_existing_source_signals(session, location, ingester.source)
        await ingest_location(session, location_input, ingester)
    return location_input


def _business_license_source_count(
    location_input: LocationInput,
    ingesters: tuple[BaseIngester, ...],
) -> int | None:
    for ingester in ingesters:
        if isinstance(ingester, BizLicensesIngester):
            return len(ingester.matching_sources(location_input))
    return None


def _delete_existing_source_signals(session: Session, location: Location, source: str) -> None:
    statement = delete(Signal).where(
        Signal.location_id == location.id,
        Signal.source == source,
    )
    session.execute(statement)
    session.commit()
