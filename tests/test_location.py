from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import app, get_geocode_ingester
from backend.fetch import BaseIngester, LocationInput, SignalCreate
from backend.store import Base, Location, get_session


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


def test_post_location_reuses_stored_pin_when_live_geocode_fails() -> None:
    client, session_factory = build_test_client(StubGeocodeIngester([]))
    try:
        with session_factory() as session:
            session.add(
                Location(
                    address="501 OFARRELL ST, SAN FRANCISCO, CA, 94102",
                    latitude=37.7857,
                    longitude=-122.4130,
                )
            )
            session.commit()
        response = client.post(
            "/location",
            json={"address": "501 OFARRELL ST, SAN FRANCISCO, CA, 94102"},
        )
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["address"] == "501 OFARRELL ST, SAN FRANCISCO, CA, 94102"
    assert response.json()["latitude"] == 37.7857


def test_post_location_reuses_pin_for_verbose_same_place_address() -> None:
    verbose = (
        "200 South Wacker, 200, South Wacker Drive, Financial District, Loop, "
        "Chicago, South Chicago Township, Cook County, Illinois, 60606, United States"
    )
    client, session_factory = build_test_client(StubGeocodeIngester([]))
    try:
        with session_factory() as session:
            session.add(
                Location(
                    address="200 S WACKER DR, CHICAGO, IL, 60606",
                    latitude=41.8793,
                    longitude=-87.6370,
                )
            )
            session.commit()
        response = client.post("/location", json={"address": verbose})
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["address"] == "200 S WACKER DR, CHICAGO, IL, 60606"
    assert response.json()["latitude"] == 41.8793


def test_post_location_stores_requested_address_when_match_label_is_verbose() -> None:
    verbose = (
        "200 South Wacker, 200, South Wacker Drive, Financial District, Loop, "
        "Chicago, South Chicago Township, Cook County, Illinois, 60606, United States"
    )
    client, _session_factory = build_test_client(
        StubGeocodeIngester(
            [
                SignalCreate(
                    source="geocode",
                    signal_type="baseline",
                    observed_at=datetime(2026, 1, 1, tzinfo=UTC),
                    value={
                        "matched_address": verbose,
                        "latitude": 41.8789,
                        "longitude": -87.6373,
                        "tiger_line_id": "nominatim",
                        "side": "N",
                    },
                    summary="Resolved by nominatim.",
                    is_anomaly=False,
                    confidence=0.7,
                )
            ]
        )
    )
    try:
        response = client.post(
            "/location",
            json={"address": "200 South Wacker Drive, Chicago, IL, 60606"},
        )
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["address"] == "200 South Wacker Drive, Chicago, IL, 60606"
