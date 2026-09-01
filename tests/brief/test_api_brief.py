from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import app, get_signal_ingesters
from backend.brief import Brief, BriefModule, CategoryBrief, PlaceGraph
from backend.fetch import BaseIngester, BizLicensesIngester, LocationInput, SignalCreate
from backend.store import Base, BriefSnapshot, Location, SourceWatermark, get_session


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


class StubCrimeNearbyIngester(BaseIngester):
    source = "crime_nearby"

    def __init__(self) -> None:
        self.fetch_calls = 0

    async def fetch(self, location: LocationInput) -> list[SignalCreate]:
        self.fetch_calls += 1
        return [
            SignalCreate(
                source=self.source,
                signal_type="trend",
                observed_at=datetime(2026, 8, 31, tzinfo=UTC),
                value={
                    "burglary": 5,
                    "vehicle": 8,
                    "robbery": 2,
                    "vandalism": 5,
                    "total_incidents": 20,
                    "radius_meters": 400,
                    "window_days": 365,
                },
                summary="20 incidents within 400m in the last 12 months.",
                is_anomaly=False,
                confidence=1.0,
            )
        ]


def test_post_brief_rebuilds_when_snapshot_is_missing_a_live_trail() -> None:
    licenses = StubBizLicensesIngester()
    crime = StubCrimeNearbyIngester()
    client, session_factory = build_test_client()
    app.dependency_overrides[get_signal_ingesters] = lambda: (licenses, crime)
    address = "501 OFARRELL ST, SAN FRANCISCO, CA, 94102"
    empty = CategoryBrief()
    try:
        with session_factory() as session:
            location = Location(address=address, latitude=37.78573, longitude=-122.41303)
            session.add(location)
            session.flush()
            session.add(
                SourceWatermark(
                    location_id=location.id,
                    source="crime_nearby",
                    refreshed_at=datetime(2026, 8, 31, tzinfo=UTC),
                )
            )
            session.add(
                BriefSnapshot(
                    location_id=location.id,
                    generated_at=datetime(2026, 8, 31, tzinfo=UTC),
                    payload=Brief(
                        address=address,
                        generated_at=datetime(2026, 8, 31, tzinfo=UTC),
                        narrative="Commercial.",
                        place_class="commercial",
                        place_class_label="Commercial",
                        place_class_assumed=False,
                        modules=[
                            BriefModule(
                                id="tenancy",
                                title="Tenure",
                                question="Tenure?",
                                trail="Tenure.",
                                status="uncovered",
                                summary="No assessor feed.",
                            ),
                            BriefModule(
                                id="business_activity",
                                title="Who operated here",
                                question="Who operated?",
                                trail="Licenses.",
                                status="empty",
                                summary="No operator on file.",
                            ),
                            BriefModule(
                                id="inspections",
                                title="Inspections",
                                question="Inspections?",
                                trail="Inspections.",
                                status="uncovered",
                                summary="No inspection feed.",
                            ),
                            BriefModule(
                                id="site_work",
                                title="Site work",
                                question="Site work?",
                                trail="Permits.",
                                status="uncovered",
                                summary="No permit portal.",
                            ),
                        ],
                        graph=PlaceGraph(place_id="place", place_label=address),
                        physical_condition=empty,
                        regulatory_standing=empty,
                        operational_activity=empty,
                        environmental_context=empty,
                    ).model_dump(mode="json"),
                )
            )
            session.commit()

        response = client.post("/brief", json={"address": address})
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert crime.fetch_calls == 1
    nearby = next(module for module in data["modules"] if module["id"] == "neighborhood")
    assert nearby["status"] == "answered"
    assert {entity["kind"] for entity in data["graph"]["entities"]} >= {"context"}
    assert any(edge["capability"] == "neighborhood" for edge in data["graph"]["edges"])
