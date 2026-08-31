from datetime import UTC, datetime

import httpx
import pytest

from backend.brief import SOURCE_TO_CATEGORY
from backend.fetch import (
    CRIME_LOOKBACK_DAYS,
    CRIME_RADIUS_METERS,
    CrimeAggregateRow,
    CrimeNearbyIngester,
    LocationInput,
    socrata_resource_url,
)
from backend.store import Settings


class StubCrimeNearbyIngester(CrimeNearbyIngester):
    def __init__(
        self,
        row: CrimeAggregateRow | None = None,
        error: Exception | None = None,
    ) -> None:
        super().__init__(host="opendata.example.test", api_version="v2")
        self.row = row
        self.error = error

    async def _fetch_aggregate(self, location: LocationInput) -> CrimeAggregateRow | None:
        if self.error is not None:
            raise self.error
        return self.row


def sf_location() -> LocationInput:
    return LocationInput(
        address="1 DR CARLTON B GOODLETT PL, SAN FRANCISCO, CA, 94102",
        latitude=37.7749,
        longitude=-122.4194,
    )


def chicago_location() -> LocationInput:
    return LocationInput(
        address="123 MAIN ST, CHICAGO, IL, 60601",
        latitude=41.8781,
        longitude=-87.6298,
    )


def make_row(
    *,
    total_incidents: int = 20,
    distinct_intersections: int = 10,
    burglary: int = 5,
    robbery: int = 2,
    vehicle: int = 8,
    vandalism: int = 5,
    data_as_of: str | None = "2026-08-31T09:43:16.000",
) -> CrimeAggregateRow:
    return CrimeAggregateRow(
        total_incidents=total_incidents,
        distinct_intersections=distinct_intersections,
        burglary=burglary,
        robbery=robbery,
        vehicle=vehicle,
        vandalism=vandalism,
        data_as_of=data_as_of,
    )


def test_default_socrata_host_and_version_come_from_settings() -> None:
    assert Settings.model_fields["socrata_host"].default == "data.sf.gov"
    assert Settings.model_fields["socrata_api_version"].default == "v2"
    assert socrata_resource_url("data.sf.gov", "v2", "wg3w-h783") == (
        "https://data.sf.gov/resource/wg3w-h783.json"
    )
    assert "data.sfgov.org" not in socrata_resource_url("data.sf.gov", "v2", "wg3w-h783")


def test_api_url_uses_constructor_host_and_version_not_a_literal() -> None:
    v2 = CrimeNearbyIngester(host="opendata.example.test", api_version="v2")
    v3 = CrimeNearbyIngester(host="opendata.example.test", api_version="v3")

    assert v2.api_url == "https://opendata.example.test/resource/wg3w-h783.json"
    assert v3.api_url == "https://opendata.example.test/api/v3/views/wg3w-h783/query.json"
    assert "data.sfgov.org" not in v2.api_url
    assert "data.sfgov.org" not in v3.api_url


def test_query_params_filter_circle_categories_report_type_and_window() -> None:
    ingester = CrimeNearbyIngester(host="opendata.example.test")
    now = datetime(2026, 8, 31, 17, 0, 0, tzinfo=UTC)

    params = ingester._query_params(sf_location(), now=now)

    assert "within_circle(point, 37.7749, -122.4194, 400)" in params["$where"]
    assert "incident_datetime >= '2025-08-31T17:00:00'" in params["$where"]
    assert "report_type_description in ('Initial', 'Coplogic Initial', 'Vehicle Initial')" in (
        params["$where"]
    )
    assert "resolution != 'Unfounded'" in params["$where"]
    assert "Burglary" in params["$where"]
    assert "Robbery" in params["$where"]
    assert "Motor Vehicle Theft" in params["$where"]
    assert "Motor Vehicle Theft?" in params["$where"]
    assert "Larceny - From Vehicle" in params["$where"]
    assert "Theft From Vehicle" in params["$where"]
    assert "Larceny - Auto Parts" in params["$where"]
    assert "Malicious Mischief" in params["$where"]
    assert "Vandalism" in params["$where"]
    assert "count(distinct incident_id)" in params["$select"]
    assert "count(distinct intersection)" in params["$select"]
    assert "count(distinct case(incident_category = 'Burglary', incident_id))" in params["$select"]


def test_source_maps_to_environmental_context() -> None:
    assert SOURCE_TO_CATEGORY["crime_nearby"] == "environmental_context"


def test_aggregate_row_coerces_socrata_string_numbers() -> None:
    row = CrimeAggregateRow.model_validate(
        {
            "total_incidents": "310",
            "distinct_intersections": "51",
            "burglary": "67",
            "robbery": "23",
            "vehicle": "129",
            "vandalism": "102",
            "data_as_of": "2026-08-31T09:43:16.000",
        }
    )

    assert row.total_incidents == 310
    assert row.distinct_intersections == 51
    assert row.burglary == 67
    assert row.vehicle == 129


@pytest.mark.asyncio
async def test_fetch_returns_empty_list_without_coordinates() -> None:
    ingester = StubCrimeNearbyIngester(row=make_row())

    signals = await ingester.fetch(LocationInput(address="1 Market St"))

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_returns_empty_list_outside_san_francisco() -> None:
    ingester = StubCrimeNearbyIngester(row=make_row())

    signals = await ingester.fetch(chicago_location())

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_returns_empty_list_when_intersections_are_thin() -> None:
    ingester = StubCrimeNearbyIngester(row=make_row(distinct_intersections=5))

    signals = await ingester.fetch(sf_location())

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_returns_empty_list_when_api_is_unreachable() -> None:
    ingester = StubCrimeNearbyIngester(error=httpx.ConnectError("unreachable"))

    signals = await ingester.fetch(sf_location())

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_returns_one_trend_signal() -> None:
    ingester = StubCrimeNearbyIngester(row=make_row())

    signals = await ingester.fetch(sf_location())

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source == "crime_nearby"
    assert signal.signal_type == "trend"
    assert signal.is_anomaly is False
    assert signal.confidence == 1.0
    assert signal.value == {
        "burglary": 5,
        "vehicle": 8,
        "robbery": 2,
        "vandalism": 5,
        "total_incidents": 20,
        "distinct_intersections": 10,
        "radius_meters": CRIME_RADIUS_METERS,
        "window_days": CRIME_LOOKBACK_DAYS,
        "data_as_of": "2026-08-31T09:43:16.000",
    }
    assert signal.summary == (
        "20 incidents within 400m in the last 12 months "
        "(5 burglary, 8 vehicle, 2 robbery, 5 vandalism)."
    )
