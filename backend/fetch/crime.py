from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel, TypeAdapter

from ..store import get_settings
from .base import BaseIngester, LocationInput, RawRow, SignalCreate

logger = logging.getLogger(__name__)


SFPD_INCIDENTS_DATASET_ID = "wg3w-h783"
CRIME_RADIUS_METERS = 400
CRIME_LOOKBACK_DAYS = 365
SF_LAT_MIN = 37.70
SF_LAT_MAX = 37.84
SF_LNG_MIN = -122.55
SF_LNG_MAX = -122.35
CRIME_REPORT_TYPES = ("Initial", "Coplogic Initial", "Vehicle Initial")
CRIME_VEHICLE_CATEGORIES = ("Motor Vehicle Theft", "Motor Vehicle Theft?")
CRIME_LARCENY_VEHICLE_SUBCATEGORIES = (
    "Larceny - From Vehicle",
    "Theft From Vehicle",
    "Larceny - Auto Parts",
)
CRIME_VANDALISM_CATEGORIES = ("Malicious Mischief", "Vandalism")


class CrimeAggregateRow(BaseModel):
    total_incidents: int = 0
    distinct_intersections: int = 0
    burglary: int = 0
    robbery: int = 0
    vehicle: int = 0
    vandalism: int = 0
    data_as_of: str | None = None


class CrimeNearbyIngester(BaseIngester):
    source = "crime_nearby"

    def __init__(
        self,
        host: str | None = None,
        api_version: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        settings = get_settings()
        self.host = host if host is not None else settings.socrata_host
        self.api_version = api_version if api_version is not None else settings.socrata_api_version
        self.timeout_seconds = timeout_seconds
        self.socrata_app_token = settings.socrata_app_token
        self.api_url = socrata_resource_url(
            self.host,
            self.api_version,
            SFPD_INCIDENTS_DATASET_ID,
        )

    async def fetch(self, location: LocationInput) -> list[SignalCreate]:
        if location.latitude is None or location.longitude is None:
            logger.info("Crime nearby skipped: no coordinates for %s", location.address)
            return []
        if not in_san_francisco(location.latitude, location.longitude):
            logger.info("Crime nearby skipped: %s is outside San Francisco", location.address)
            return []

        row = await self._fetch_aggregate(location)
        if row is None:
            return []
        return [self._to_signal(row)]

    async def _fetch_aggregate(self, location: LocationInput) -> CrimeAggregateRow | None:
        headers: dict[str, str] = {}
        if self.socrata_app_token is not None:
            headers["X-App-Token"] = self.socrata_app_token

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                self.api_url,
                params=self._query_params(location),
                headers=headers,
            )
            response.raise_for_status()

        rows = TypeAdapter(list[RawRow]).validate_python(response.json())
        if not rows:
            return None
        return CrimeAggregateRow.model_validate(rows[0])

    def _query_params(
        self,
        location: LocationInput,
        *,
        now: datetime | None = None,
    ) -> dict[str, str]:
        if location.latitude is None or location.longitude is None:
            raise ValueError("Crime nearby query requires latitude and longitude")

        current = now or datetime.now(tz=UTC)
        since = (current - timedelta(days=CRIME_LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
        report_types = _soql_in(CRIME_REPORT_TYPES)
        vehicle_categories = _soql_in(CRIME_VEHICLE_CATEGORIES)
        larceny_subcategories = _soql_in(CRIME_LARCENY_VEHICLE_SUBCATEGORIES)
        vandalism_categories = _soql_in(CRIME_VANDALISM_CATEGORIES)
        vehicle_case = (
            f"incident_category in ({vehicle_categories}) OR "
            f"(incident_category = 'Larceny Theft' AND "
            f"incident_subcategory in ({larceny_subcategories}))"
        )
        category_filter = (
            f"incident_category in ('Burglary', 'Robbery', {vehicle_categories}, "
            f"{vandalism_categories}) OR "
            f"(incident_category = 'Larceny Theft' AND "
            f"incident_subcategory in ({larceny_subcategories}))"
        )
        return {
            "$select": (
                "count(distinct incident_id) as total_incidents, "
                "count(distinct intersection) as distinct_intersections, "
                "max(data_as_of) as data_as_of, "
                "count(distinct case(incident_category = 'Burglary', incident_id)) as burglary, "
                "count(distinct case(incident_category = 'Robbery', incident_id)) as robbery, "
                f"count(distinct case({vehicle_case}, incident_id)) as vehicle, "
                f"count(distinct case(incident_category in ({vandalism_categories}), "
                f"incident_id)) as vandalism"
            ),
            "$where": (
                f"within_circle(point, {location.latitude}, {location.longitude}, "
                f"{CRIME_RADIUS_METERS}) AND incident_datetime >= '{since}' AND "
                f"report_type_description in ({report_types}) AND "
                f"resolution != 'Unfounded' AND ({category_filter})"
            ),
        }

    def _to_signal(self, row: CrimeAggregateRow) -> SignalCreate:
        return SignalCreate(
            source=self.source,
            signal_type="trend",
            observed_at=datetime.now(tz=UTC),
            value={
                "burglary": row.burglary,
                "vehicle": row.vehicle,
                "robbery": row.robbery,
                "vandalism": row.vandalism,
                "total_incidents": row.total_incidents,
                "distinct_intersections": row.distinct_intersections,
                "radius_meters": CRIME_RADIUS_METERS,
                "window_days": CRIME_LOOKBACK_DAYS,
                "data_as_of": row.data_as_of,
            },
            summary=(
                f"{row.total_incidents} incidents within {CRIME_RADIUS_METERS}m in the last "
                f"12 months ({row.burglary} burglary, {row.vehicle} vehicle, "
                f"{row.robbery} robbery, {row.vandalism} vandalism)."
            ),
            is_anomaly=False,
            confidence=1.0,
        )


def socrata_resource_url(host: str, api_version: str, dataset_id: str) -> str:
    if api_version == "v3":
        return f"https://{host}/api/v3/views/{dataset_id}/query.json"
    return f"https://{host}/resource/{dataset_id}.json"


def in_san_francisco(latitude: float, longitude: float) -> bool:
    return SF_LAT_MIN <= latitude <= SF_LAT_MAX and SF_LNG_MIN <= longitude <= SF_LNG_MAX


def _soql_in(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)
