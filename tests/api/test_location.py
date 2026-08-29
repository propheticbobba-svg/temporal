from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from api.routes.location import get_geocode_ingester
from db.models import Base, Location
from db.session import get_session
from ingestion.base import BaseIngester
from ingestion.schema import LocationInput, SignalCreate


class StubGeocodeIngester(BaseIngester):
    source = "geocode"

    def __init__(self, signals: list[SignalCreate]) -> None:
        self.signals = signals

    async def fetch(self, location: LocationInput) -> list[SignalCreate]:
        return self.signals


def make_geocode_signal(confidence: float = 1.0) -> SignalCreate:
    return SignalCreate(
        source="geocode",
        signal_type="baseline",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        value={
            "matched_address": "123 MAIN ST, CHICAGO, IL, 60601",
            "latitude": 41.8781,
            "longitude": -87.6298,
            "tiger_line_id": "123456789",
            "side": "L",
        },
        summary="The address was resolved to 123 MAIN ST, CHICAGO, IL, 60601.",
        is_anomaly=False,
        confidence=confidence,
    )


def build_test_client(
    ingester: BaseIngester,
) -> tuple[TestClient, sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)

    def override_get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_geocode_ingester] = lambda: ingester
    return TestClient(app), session_factory


def test_post_location_returns_resolved_coordinates() -> None:
    client, _session_factory = build_test_client(StubGeocodeIngester([make_geocode_signal()]))
    try:
        response = client.post("/location", json={"address": "123 Main St, Chicago IL"})
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "address": "123 MAIN ST, CHICAGO, IL, 60601",
        "latitude": 41.8781,
        "longitude": -87.6298,
        "confidence": 1.0,
    }


def test_post_location_returns_non_exact_confidence() -> None:
    client, _session_factory = build_test_client(
        StubGeocodeIngester([make_geocode_signal(confidence=0.7)])
    )
    try:
        response = client.post("/location", json={"address": "123 Main St, Chicago IL"})
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "address": "123 MAIN ST, CHICAGO, IL, 60601",
        "latitude": 41.8781,
        "longitude": -87.6298,
        "confidence": 0.7,
    }


def test_post_location_does_not_create_duplicate_location_rows() -> None:
    client, session_factory = build_test_client(StubGeocodeIngester([make_geocode_signal()]))
    try:
        first_response = client.post("/location", json={"address": "123 Main St, Chicago IL"})
        second_response = client.post("/location", json={"address": "123 Main St, Chicago IL"})

        with session_factory() as session:
            location_count = session.scalar(select(func.count()).select_from(Location))
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert location_count == 1


def test_post_location_returns_422_when_geocode_fails() -> None:
    client, _session_factory = build_test_client(StubGeocodeIngester([]))
    try:
        response = client.post("/location", json={"address": "Unknown address"})
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json() == {"detail": "Unable to geocode address: Unknown address"}
