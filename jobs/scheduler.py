from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ingestion.base import BaseIngester
from ingestion.biz_licenses import BizLicensesIngester
from ingestion.geocode import GeocodeIngester
from ingestion.permits import PermitsIngester


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
