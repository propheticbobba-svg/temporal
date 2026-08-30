from datetime import UTC

import httpx
import pytest

from backend.fetch import CensusAddressMatch, GeocodeIngester, LocationInput, compact_geocode_query


class StubGeocodeIngester(GeocodeIngester):
    def __init__(
        self,
        matches: list[CensusAddressMatch] | None = None,
        error: httpx.HTTPError | None = None,
    ) -> None:
        super().__init__(api_url="https://geocoder.example.test")
        self.matches = matches or []
        self.error = error

    async def _fetch_matches(self, location: LocationInput) -> list[CensusAddressMatch]:
        if self.error is not None:
            raise self.error
        return self.matches


def make_match(match_status: str | None = "Exact") -> CensusAddressMatch:
    return CensusAddressMatch.model_validate(
        {
            "matchedAddress": "123 MAIN ST, CHICAGO, IL, 60601",
            "coordinates": {"x": -87.6298, "y": 41.8781},
            "tigerLine": {"tigerLineId": "123456789", "side": "L"},
            "matchStatus": match_status,
        }
    )


@pytest.mark.asyncio
async def test_fetch_returns_baseline_signal_for_successful_match() -> None:
    ingester = StubGeocodeIngester(matches=[make_match()])

    signals = await ingester.fetch(LocationInput(address="123 Main St, Chicago IL"))

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source == "geocode"
    assert signal.signal_type == "baseline"
    assert signal.observed_at.tzinfo is UTC
    assert signal.value == {
        "matched_address": "123 MAIN ST, CHICAGO, IL, 60601",
        "latitude": 41.8781,
        "longitude": -87.6298,
        "tiger_line_id": "123456789",
        "side": "L",
    }
    assert signal.summary == (
        "The address was resolved to 123 MAIN ST, CHICAGO, IL, 60601 at "
        "41.878100, -87.629800."
    )
    assert signal.is_anomaly is False


@pytest.mark.asyncio
async def test_fetch_returns_empty_list_when_api_is_unreachable() -> None:
    ingester = StubGeocodeIngester(error=httpx.ConnectError("unreachable"))

    signals = await ingester.fetch(LocationInput(address="123 Main St, Chicago IL"))

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_returns_empty_list_when_address_has_no_match() -> None:
    ingester = StubGeocodeIngester(matches=[])

    signals = await ingester.fetch(LocationInput(address="Unknown address"))

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_falls_back_to_nominatim_when_census_is_forbidden() -> None:
    request = httpx.Request("GET", "https://geocoding.geo.census.gov")
    forbidden = httpx.HTTPStatusError(
        "403 Forbidden",
        request=request,
        response=httpx.Response(403, request=request),
    )

    class FallbackIngester(GeocodeIngester):
        async def _fetch_census(self, location: LocationInput) -> list[CensusAddressMatch]:
            raise forbidden

        async def _fetch_photon(self, location: LocationInput) -> list[CensusAddressMatch]:
            return []

        async def _fetch_nominatim(self, location: LocationInput) -> list[CensusAddressMatch]:
            return [make_match()]

    signals = await FallbackIngester().fetch(LocationInput(address="123 Main St, Chicago IL"))

    assert len(signals) == 1
    assert signals[0].value["matched_address"] == "123 MAIN ST, CHICAGO, IL, 60601"


@pytest.mark.asyncio
async def test_fetch_falls_back_to_photon_when_census_returns_no_matches() -> None:
    class FallbackIngester(GeocodeIngester):
        async def _fetch_census(self, location: LocationInput) -> list[CensusAddressMatch]:
            return []

        async def _fetch_photon(self, location: LocationInput) -> list[CensusAddressMatch]:
            return [make_match("Non_Exact")]

        async def _fetch_nominatim(self, location: LocationInput) -> list[CensusAddressMatch]:
            raise AssertionError("nominatim should not run after photon matches")

    signals = await FallbackIngester().fetch(
        LocationInput(address="501 OFARRELL ST, SAN FRANCISCO, CA, 94102")
    )

    assert len(signals) == 1
    assert signals[0].confidence == 0.7


@pytest.mark.asyncio
async def test_fetch_sets_confidence_from_match_quality() -> None:
    exact_ingester = StubGeocodeIngester(matches=[make_match("Exact")])
    non_exact_ingester = StubGeocodeIngester(matches=[make_match("Non_Exact")])

    exact_signals = await exact_ingester.fetch(LocationInput(address="123 Main St, Chicago IL"))
    non_exact_signals = await non_exact_ingester.fetch(
        LocationInput(address="123 Main St, Chicago IL")
    )

    assert exact_signals[0].confidence == 1.0
    assert non_exact_signals[0].confidence == 0.7


@pytest.mark.asyncio
async def test_fetch_falls_back_when_census_raises_unexpected_error() -> None:
    class FallbackIngester(GeocodeIngester):
        async def _fetch_census(self, location: LocationInput) -> list[CensusAddressMatch]:
            raise RuntimeError("html outage page")

        async def _fetch_photon(self, location: LocationInput) -> list[CensusAddressMatch]:
            return [make_match("Non_Exact")]

        async def _fetch_nominatim(self, location: LocationInput) -> list[CensusAddressMatch]:
            raise AssertionError("nominatim should not run after photon matches")

    signals = await FallbackIngester().fetch(
        LocationInput(address="501 OFARRELL ST, SAN FRANCISCO, CA, 94102")
    )

    assert len(signals) == 1
    assert signals[0].value["matched_address"] == "123 MAIN ST, CHICAGO, IL, 60601"


def test_compact_geocode_query_strips_nominatim_display_name() -> None:
    verbose = (
        "200 South Wacker, 200, South Wacker Drive, Financial District, Loop, "
        "Chicago, South Chicago Township, Cook County, Illinois, 60606, United States"
    )

    assert compact_geocode_query(verbose) == "200 South Wacker, 60606"
    assert compact_geocode_query("200 S WACKER DR, CHICAGO, IL, 60606") == (
        "200 S WACKER DR, CHICAGO, IL, 60606"
    )
