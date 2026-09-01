from __future__ import annotations

from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..fetch import BaseIngester, BizLicensesIngester, LocationInput
from ..place import (
    STALENESS_BY_SOURCE,
    RefreshInterval,
    capabilities_for_class,
    is_refresh_due,
    refresh_source,
    source_covers,
)
from ..store import BriefSnapshot, Location, Signal, SourceWatermark
from .anomalies import _signals_from_brief, refine_anomalies
from .assemble import build_brief
from .models import Brief, BriefRequest


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
    snapshot = _load_snapshot(session, location.id)
    stored = _brief_from_snapshot(snapshot.payload) if snapshot is not None else None
    catalog_stale = stored is None or not _modules_match(stored)
    refreshed_any = False

    for ingester in ingesters:
        due = _should_refresh(
            session, location.id, ingester.source, location_input, now, catalog_stale
        )
        if not due:
            continue
        if await refresh_source(session, location, location_input, ingester):
            _upsert_watermark(session, location.id, ingester.source, now)
            refreshed_any = True

    if stored is not None and not refreshed_any and not catalog_stale:
        current = _refresh_flags(stored)
        fused = await _maybe_fuse(current)
        if fused.fusion != stored.fusion or fused.anomaly_flags != stored.anomaly_flags:
            _upsert_snapshot(session, location.id, fused)
            session.commit()
        return fused

    covered = _with_coverage(build_brief(session, request), location_input, ingesters)
    brief = await _maybe_fuse(covered)
    _upsert_snapshot(session, location.id, brief)
    session.commit()
    return brief


async def _maybe_fuse(brief: Brief) -> Brief:
    from ..think import attach_fusion

    return await attach_fusion(brief)


def _should_refresh(
    session: Session,
    location_id: int,
    source: str,
    location: LocationInput,
    now: datetime,
    catalog_stale: bool,
) -> bool:
    if _source_is_due(session, location_id, source, now):
        return True
    if not source_covers(source, location):
        return False
    if _has_signal(session, location_id, source):
        return False
    return catalog_stale or source == "crime_nearby"


def _modules_match(brief: Brief) -> bool:
    expected = {spec.id for spec in capabilities_for_class(brief.place_class)}
    return {module.id for module in brief.modules} == expected


def _has_signal(session: Session, location_id: int, source: str) -> bool:
    return (
        session.scalars(
            select(Signal.id).where(Signal.location_id == location_id, Signal.source == source)
        ).first()
        is not None
    )


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


def _refresh_flags(brief: Brief) -> Brief:
    if brief.fusion is not None and brief.fusion.anomalies_judged:
        return brief
    flags = refine_anomalies(_signals_from_brief(brief))
    if flags == brief.anomaly_flags:
        return brief
    return brief.model_copy(update={"anomaly_flags": flags})

def _brief_from_snapshot(payload: object) -> Brief | None:
    try:
        brief = Brief.model_validate(payload)
    except ValidationError:
        return None
    if not brief.modules:
        return None
    if len(brief.place_class_reasons) != len(set(brief.place_class_reasons)):
        return None
    return brief


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
