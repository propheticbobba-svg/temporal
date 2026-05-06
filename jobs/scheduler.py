from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ingestion.base import BaseIngester
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
        source="permits",
        refresh_interval=STALENESS_BY_SOURCE["permits"],
        ingester=PermitsIngester(),
    ),
)


def get_registered_ingesters() -> tuple[IngesterRegistration, ...]:
    return REGISTERED_INGESTERS
