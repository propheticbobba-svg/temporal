from datetime import UTC, datetime

import httpx
import pytest

from ingestion.biz_licenses import (
    BizLicenseRecord,
    BizLicensesIngester,
    BizLicenseSource,
    load_license_sources,
)
from ingestion.schema import LocationInput


class StubBizLicensesIngester(BizLicensesIngester):
    def __init__(
        self,
        records: list[BizLicenseRecord] | None = None,
        error: httpx.HTTPError | None = None,
    ) -> None:
        super().__init__(sources=[])
        self.records = records or []
        self.error = error

    async def _fetch_records(self, location: LocationInput) -> list[BizLicenseRecord]:
        if self.error is not None:
            raise self.error
        return self.records


class MultiSourceBizLicensesIngester(BizLicensesIngester):
    def __init__(self, sources: list[BizLicenseSource]) -> None:
        super().__init__(sources=sources)
        self.queried_source_ids: list[str] = []

    async def _fetch_records_for_source(
        self,
        client: httpx.AsyncClient,
        source: BizLicenseSource,
        location: LocationInput,
        headers: dict[str, str],
    ) -> list[BizLicenseRecord]:
        self.queried_source_ids.append(source.id)
        return [
            make_record(
                license_id=f"L-{source.id}",
                source_dataset_id=source.id,
                source_name=source.name,
            )
        ]


def make_source(source_id: str = "test_source") -> BizLicenseSource:
    return BizLicenseSource.model_validate(
        {
            "id": source_id,
            "name": f"Source {source_id}",
            "api_url": f"https://{source_id}.example.test/resource/licenses.json",
            "cities": ["CHICAGO"],
            "states": ["IL"],
            "query": {
                "strategy": "coordinate_columns",
                "latitude_field": "latitude",
                "longitude_field": "longitude",
                "date_field": "license_start_date",
                "order_field": "license_start_date",
                "required_non_null": ["license_start_date"],
            },
            "fields": {
                "license_id": "license_id",
                "account_number": "account_number",
                "legal_name": "legal_name",
                "doing_business_as": "doing_business_as_name",
                "license_type": "license_description",
                "license_status": "license_status",
                "license_start_date": "license_start_date",
                "expiration_date": "expiration_date",
            },
        }
    )


def source_by_id(source_id: str) -> BizLicenseSource:
    for source in load_license_sources():
        if source.id == source_id:
            return source
    raise AssertionError(f"Missing source fixture: {source_id}")


def make_record(
    *,
    license_id: str = "L-100",
    license_status: str = "AAI",
    expiration_date: datetime | None = datetime(2099, 1, 1, tzinfo=UTC),
    source_dataset_id: str = "test_source",
    source_name: str = "Test Source",
) -> BizLicenseRecord:
    return BizLicenseRecord(
        license_id=license_id,
        account_number="A-200",
        legal_name="Cafe Luna LLC",
        doing_business_as="CAFE LUNA",
        license_type="Retail Food",
        license_status=license_status,
        license_start_date=datetime(2026, 1, 15, tzinfo=UTC),
        expiration_date=expiration_date,
        source_dataset_id=source_dataset_id,
        source_name=source_name,
    )


@pytest.mark.asyncio
async def test_fetch_returns_standard_signal_envelope_for_active_license() -> None:
    ingester = StubBizLicensesIngester(records=[make_record()])

    signals = await ingester.fetch(LocationInput(address="100 Main St"))

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source == "biz_licenses"
    assert signal.signal_type == "activity"
    assert signal.observed_at == datetime(2026, 1, 15, tzinfo=UTC)
    assert signal.value == {
        "license_id": "L-100",
        "account_number": "A-200",
        "legal_name": "Cafe Luna LLC",
        "doing_business_as": "CAFE LUNA",
        "license_type": "Retail Food",
        "license_status": "AAI",
        "expiration_date": "2099-01-01T00:00:00Z",
        "source_dataset_id": "test_source",
        "source_name": "Test Source",
    }
    assert signal.summary == (
        "A retail food license for CAFE LUNA was issued, currently active, "
        "expiring 2099-01-01."
    )
    assert signal.is_anomaly is False
    assert signal.confidence == 1.0


@pytest.mark.asyncio
async def test_fetch_flags_revoked_license_as_anomaly() -> None:
    ingester = StubBizLicensesIngester(records=[make_record(license_status="REV")])

    signals = await ingester.fetch(LocationInput(address="100 Main St"))

    assert signals[0].signal_type == "anomaly"
    assert signals[0].is_anomaly is True


@pytest.mark.asyncio
async def test_fetch_flags_expired_license_as_anomaly() -> None:
    ingester = StubBizLicensesIngester(
        records=[make_record(expiration_date=datetime(2000, 1, 1, tzinfo=UTC))]
    )

    signals = await ingester.fetch(LocationInput(address="100 Main St"))

    assert signals[0].signal_type == "anomaly"
    assert signals[0].is_anomaly is True


@pytest.mark.asyncio
async def test_fetch_returns_empty_list_when_no_source_matches_location() -> None:
    ingester = BizLicensesIngester(sources=[make_source("chicago")])

    signals = await ingester.fetch(
        LocationInput(
            address="950 REDWOOD SHORES PKWY, REDWOOD CITY, CA, 94065",
            latitude=37.538,
            longitude=-122.234,
        )
    )

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_returns_empty_list_when_api_is_unreachable() -> None:
    ingester = StubBizLicensesIngester(error=httpx.ConnectError("unreachable"))

    signals = await ingester.fetch(LocationInput(address="100 Main St"))

    assert signals == []


@pytest.mark.asyncio
async def test_summary_contains_business_name_and_license_type() -> None:
    ingester = StubBizLicensesIngester(records=[make_record()])

    signals = await ingester.fetch(LocationInput(address="100 Main St"))

    assert "CAFE LUNA" in signals[0].summary
    assert "retail food" in signals[0].summary


@pytest.mark.asyncio
async def test_fetch_queries_all_matching_sources() -> None:
    source_a = make_source("city_source")
    source_b = make_source("county_source")
    ingester = MultiSourceBizLicensesIngester(sources=[source_a, source_b])

    signals = await ingester.fetch(
        LocationInput(
            address="123 MAIN ST, CHICAGO, IL, 60601",
            latitude=41.8781,
            longitude=-87.6298,
        )
    )

    assert ingester.queried_source_ids == ["city_source", "county_source"]
    assert [signal.value["source_dataset_id"] for signal in signals] == [
        "city_source",
        "county_source",
    ]


def test_matching_sources_uses_resolved_city_and_state() -> None:
    ingester = BizLicensesIngester(sources=load_license_sources())

    matches = ingester.matching_sources(
        LocationInput(address="123 MARKET ST, SAN FRANCISCO, CA, 94103")
    )

    assert [source.id for source in matches] == ["sf_registered_business_locations"]


def test_coordinate_query_params_include_bounding_box() -> None:
    ingester = BizLicensesIngester(sources=[])
    source = source_by_id("nyc_issued_licenses")

    params = ingester._query_params(
        source,
        LocationInput(
            address="608 8TH AVE, NEW YORK, NY, 10018",
            latitude=40.755613,
            longitude=-73.990962,
        ),
    )

    assert params["$limit"] == "50"
    assert params["$order"] == "license_creation_date DESC"
    assert "latitude between" in params["$where"]
    assert "license_creation_date IS NOT NULL" in params["$where"]


def test_address_query_params_use_street_city_state_and_zip() -> None:
    ingester = BizLicensesIngester(sources=[])
    source = source_by_id("seattle_active_business_licenses")

    params = ingester._query_params(
        source,
        LocationInput(address="706 UNION ST # 409, SEATTLE, WA, 98101"),
    )

    assert "upper(street_address) = '706 UNION ST # 409'" in params["$where"]
    assert "upper(city) = 'SEATTLE'" in params["$where"]
    assert "upper(state) = 'WA'" in params["$where"]
    assert "zip like '98101%'" in params["$where"]


def test_source_schemas_normalize_into_standard_records() -> None:
    ingester = BizLicensesIngester(sources=[])
    examples = [
        (
            "chicago_business_licenses",
            {
                "license_id": "3074723",
                "account_number": "36477",
                "legal_name": "HAMILTON CONSTRUCTION INC.",
                "doing_business_as_name": "HAMILTON CONSTRUCTION",
                "license_description": "Limited Business License",
                "license_status": "AAI",
                "license_start_date": "2026-05-16T00:00:00.000",
                "expiration_date": "2028-05-15T00:00:00.000",
            },
        ),
        (
            "nyc_issued_licenses",
            {
                "license_nbr": "0002902-DCA",
                "business_unique_id": "BA-1216876-2022",
                "business_name": "GEM FINANCIAL SERVICES, INC.",
                "dba_trade_name": "GEM PAWNBROKERS",
                "business_category": "Pawnbroker",
                "license_status": "Ready for Renewal",
                "license_creation_date": "2007-04-18T00:00:00.000",
                "lic_expir_dd": "2026-04-30T00:00:00.000",
            },
        ),
        (
            "seattle_active_business_licenses",
            {
                "city_account_number": "0007748490686809",
                "business_legal_name": "ABDURAKHMANOV RASULZHON",
                "trade_name": "RASULZHON ABDURAKHMANOV",
                "naics_description": "Limousine Service",
                "license_start_date": "20140814",
            },
        ),
        (
            "sf_registered_business_locations",
            {
                "uniqueid": "1009572-10-141-0472588",
                "certificate_number": "0472588",
                "ownership_name": "Saysette Grant W",
                "dba_name": "Call Cpr",
                "location_start_date": "2014-07-01T00:00:00.000",
                "location_end_date": "2014-05-29T00:00:00.000",
            },
        ),
        (
            "la_active_businesses",
            {
                "location_account": "0000000108-0001-3",
                "business_name": "PALACE OF VENICE GUEST HOME /C",
                "primary_naics_description": "Rooming & boarding houses",
                "location_start_date": "1991-05-15T00:00:00.000",
            },
        ),
    ]

    records = [
        ingester._normalize_row(source_by_id(source_id), row)
        for source_id, row in examples
    ]

    assert {record.source_dataset_id for record in records} == {
        "chicago_business_licenses",
        "nyc_issued_licenses",
        "seattle_active_business_licenses",
        "sf_registered_business_locations",
        "la_active_businesses",
    }
    assert all(record.license_id for record in records)
    assert all(record.legal_name for record in records)
    assert records[2].license_start_date == datetime(2014, 8, 14, tzinfo=UTC)
    assert records[3].license_status == "EXP"
