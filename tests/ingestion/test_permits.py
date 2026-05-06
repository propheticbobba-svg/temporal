from datetime import UTC, datetime

import pytest

from ingestion.permits import PermitRecord, PermitsIngester
from ingestion.schema import LocationInput


class StubPermitsIngester(PermitsIngester):
    def __init__(self, records: list[PermitRecord]) -> None:
        super().__init__(api_url="https://permits.example.test")
        self.records = records

    async def _fetch_records(self, location: LocationInput) -> list[PermitRecord]:
        return self.records


@pytest.mark.asyncio
async def test_fetch_returns_standard_signal_envelope() -> None:
    ingester = StubPermitsIngester(
        records=[
            PermitRecord(
                permit_id="P-100",
                status="Issued",
                permit_type="Building",
                description="Tenant improvement",
                issued_at=datetime(2026, 1, 15, tzinfo=UTC),
                valuation=50_000,
            )
        ]
    )

    signals = await ingester.fetch(LocationInput(address="100 Main St"))

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source == "permits"
    assert signal.signal_type == "activity"
    assert signal.observed_at == datetime(2026, 1, 15, tzinfo=UTC)
    assert signal.value == {
        "permit_id": "P-100",
        "status": "Issued",
        "permit_type": "Building",
        "description": "Tenant improvement",
        "valuation": 50_000.0,
    }
    assert signal.summary == "A building permit was issued with status issued valued at $50,000."
    assert signal.is_anomaly is False
    assert signal.confidence == 1.0


@pytest.mark.asyncio
async def test_fetch_flags_unusual_permit_values_as_anomalies() -> None:
    ingester = StubPermitsIngester(
        records=[
            PermitRecord(
                permit_id="P-999",
                status="Issued",
                permit_type="Demolition",
                description="Major demolition",
                issued_at=datetime(2026, 2, 1, tzinfo=UTC),
                valuation=750_000,
            )
        ]
    )

    signals = await ingester.fetch(LocationInput(address="100 Main St"))

    assert signals[0].signal_type == "anomaly"
    assert signals[0].is_anomaly is True


@pytest.mark.asyncio
async def test_fetch_returns_empty_list_when_source_is_unconfigured() -> None:
    ingester = PermitsIngester(api_url=None)

    signals = await ingester.fetch(LocationInput(address="100 Main St"))

    assert signals == []
