from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.brief import build_brief
from agent.schema import Brief, BriefRequest
from db.models import BriefSnapshot, Location, SourceWatermark
from ingestion.base import BaseIngester
from ingestion.biz_licenses import BizLicensesIngester
from ingestion.schema import LocationInput
from ingestion.service import refresh_source
from jobs.scheduler import STALENESS_BY_SOURCE, RefreshInterval, is_refresh_due


async def load_brief(
    session: Session,
    request: BriefRequest,
    ingesters: tuple[BaseIngester, ...],
) -> Brief:
    location = session.scalars(
        select(Location).where(Location.address == request.address)
    ).one_or_none()
    if location is None:
        return build_brief(session, request)

    location_input = LocationInput(
        address=location.address,
        latitude=location.latitude,
        longitude=location.longitude,
    )
    now = datetime.now(tz=UTC)
    refreshed_any = False

    for ingester in ingesters:
        if not _source_is_due(session, location.id, ingester.source, now):
            continue
        if await refresh_source(session, location, location_input, ingester):
            _upsert_watermark(session, location.id, ingester.source, now)
            refreshed_any = True

    snapshot = _load_snapshot(session, location.id)
    if snapshot is not None and not refreshed_any:
        return Brief.model_validate(snapshot.payload)

    brief = _with_coverage(build_brief(session, request), location_input, ingesters)
    _upsert_snapshot(session, location.id, brief)
    session.commit()
    return brief


def _source_is_due(session: Session, location_id: int, source: str, now: datetime) -> bool:
    interval = STALENESS_BY_SOURCE.get(source, RefreshInterval.WEEKLY)
    watermark = session.scalars(
        select(SourceWatermark).where(
            SourceWatermark.location_id == location_id,
            SourceWatermark.source == source,
        )
    ).one_or_none()
    refreshed_at = watermark.refreshed_at if watermark is not None else None
    return is_refresh_due(interval, refreshed_at, now=now)


def _load_snapshot(session: Session, location_id: int) -> BriefSnapshot | None:
    return session.scalars(
        select(BriefSnapshot).where(BriefSnapshot.location_id == location_id)
    ).one_or_none()


def _upsert_watermark(session: Session, location_id: int, source: str, now: datetime) -> None:
    watermark = session.scalars(
        select(SourceWatermark).where(
            SourceWatermark.location_id == location_id,
            SourceWatermark.source == source,
        )
    ).one_or_none()
    if watermark is None:
        session.add(
            SourceWatermark(location_id=location_id, source=source, refreshed_at=now)
        )
        return
    watermark.refreshed_at = now


def _upsert_snapshot(session: Session, location_id: int, brief: Brief) -> None:
    snapshot = _load_snapshot(session, location_id)
    payload = brief.model_dump(mode="json")
    if snapshot is None:
        session.add(
            BriefSnapshot(
                location_id=location_id,
                generated_at=brief.generated_at,
                payload=payload,
            )
        )
        return
    snapshot.generated_at = brief.generated_at
    snapshot.payload = payload


def _with_coverage(
    brief: Brief,
    location_input: LocationInput,
    ingesters: tuple[BaseIngester, ...],
) -> Brief:
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


def _business_license_source_count(
    location_input: LocationInput,
    ingesters: tuple[BaseIngester, ...],
) -> int | None:
    for ingester in ingesters:
        if isinstance(ingester, BizLicensesIngester):
            return len(ingester.matching_sources(location_input))
    return None
