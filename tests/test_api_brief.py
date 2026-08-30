from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import app, get_signal_ingesters
from backend.fetch import BaseIngester, BizLicensesIngester, LocationInput, SignalCreate
from backend.store import Base, Location, get_session


class StubBizLicensesIngester(BaseIngester):
    source = "biz_licenses"

    def __init__(self) -> None:
        self.fetch_calls = 0

    async def fetch(self, location: LocationInput) -> list[SignalCreate]:
        self.fetch_calls += 1
        return [
            SignalCreate(
                source=self.source,
                signal_type="activity",
                observed_at=datetime(2026, 1, 15, tzinfo=UTC),
                value={
                    "license_id": "L-100",
                    "license_type": "Retail Food",
                    "license_status": "AAI",
                },
                summary="A retail food license for CAFE LUNA was issued, currently active.",
                is_anomaly=False,
                confidence=1.0,
            )
        ]


def build_test_client() -> tuple[TestClient, sessionmaker[Session]]:
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
    app.dependency_overrides[get_signal_ingesters] = lambda: (StubBizLicensesIngester(),)
    return TestClient(app), session_factory


def test_post_brief_refreshes_business_license_signals() -> None:
    client, session_factory = build_test_client()
    try:
        with session_factory() as session:
            session.add(
                Location(
                    address="123 MAIN ST, CHICAGO, IL, 60601",
                    latitude=41.8781,
                    longitude=-87.6298,
                )
            )
            session.commit()

        response = client.post("/brief", json={"address": "123 MAIN ST, CHICAGO, IL, 60601"})
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    signals = data["operational_activity"]["signals"]
    assert len(signals) == 1
    assert signals[0]["source"] == "biz_licenses"
    assert data["place_class"] == "commercial"
    operators = next(module for module in data["modules"] if module["id"] == "business_activity")
    assert operators["status"] == "answered"
    assert data["graph"]["entities"]


def test_post_brief_replaces_previous_business_license_signals() -> None:
    client, session_factory = build_test_client()
    try:
        with session_factory() as session:
            session.add(
                Location(
                    address="123 MAIN ST, CHICAGO, IL, 60601",
                    latitude=41.8781,
                    longitude=-87.6298,
                )
            )
            session.commit()

        first_response = client.post("/brief", json={"address": "123 MAIN ST, CHICAGO, IL, 60601"})
        second_response = client.post("/brief", json={"address": "123 MAIN ST, CHICAGO, IL, 60601"})
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    signals = second_response.json()["operational_activity"]["signals"]
    assert len(signals) == 1


def test_post_brief_reports_uncovered_business_license_location() -> None:
    client, session_factory = build_test_client()
    app.dependency_overrides[get_signal_ingesters] = lambda: (BizLicensesIngester(sources=[]),)
    try:
        with session_factory() as session:
            session.add(
                Location(
                    address="950 REDWOOD SHORES PKWY, REDWOOD CITY, CA, 94065",
                    latitude=37.538,
                    longitude=-122.234,
                )
            )
            session.commit()

        response = client.post(
            "/brief",
            json={"address": "950 REDWOOD SHORES PKWY, REDWOOD CITY, CA, 94065"},
        )
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["business_license_source_count"] == 0
    assert response.json()["business_license_coverage_note"] == (
        "No configured public license source covers this location yet."
    )


def test_post_brief_serves_materialized_snapshot_when_sources_are_fresh() -> None:
    stub = StubBizLicensesIngester()
    client, session_factory = build_test_client()
    app.dependency_overrides[get_signal_ingesters] = lambda: (stub,)
    try:
        with session_factory() as session:
            session.add(
                Location(
                    address="123 MAIN ST, CHICAGO, IL, 60601",
                    latitude=41.8781,
                    longitude=-87.6298,
                )
            )
            session.commit()

        first = client.post("/brief", json={"address": "123 MAIN ST, CHICAGO, IL, 60601"})
        second = client.post("/brief", json={"address": "123 MAIN ST, CHICAGO, IL, 60601"})
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert stub.fetch_calls == 1
    assert first.json()["signal_count"] == 1
    assert second.json()["operational_activity"]["signals"] == first.json()["operational_activity"][
        "signals"
    ]
    assert second.json()["narrative"]
