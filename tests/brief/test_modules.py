from datetime import UTC, datetime

from backend.brief import SignalRead, build_modules, build_place_graph
from backend.fetch import LocationInput


def test_residential_opens_home_trails_and_keeps_uncovered_honest() -> None:
    graph = build_place_graph("100 Main St Apt 4", "residential", [])
    modules = build_modules("residential", [], graph)
    by_id = {module.id: module for module in modules}

    assert set(by_id) == {
        "occupancy",
        "tenancy",
        "house_work",
        "household_services",
        "neighborhood",
    }
    assert by_id["occupancy"].status == "uncovered"
    assert by_id["household_services"].status == "uncovered"
    assert "gardener" in by_id["household_services"].summary.lower()


def test_warehouse_opens_industrial_trails() -> None:
    modules = build_modules(
        "industrial",
        [],
        build_place_graph("800 Warehouse Way", "industrial", []),
    )

    assert {module.id for module in modules} == {
        "tenancy",
        "business_activity",
        "inspections",
        "site_work",
        "industrial_activity",
        "neighborhood",
    }


def test_permit_answers_house_work_on_a_residence() -> None:
    signals = [
        SignalRead(
            source="permits",
            signal_type="activity",
            observed_at=datetime(2026, 1, 15, tzinfo=UTC),
            value={"permit_id": "P-100", "permit_type": "Reroof"},
            summary="A reroof permit was issued with status issued.",
            is_anomaly=False,
            confidence=1.0,
        )
    ]
    graph = build_place_graph("100 Main St Apt 4", "residential", signals)
    modules = build_modules("residential", signals, graph)
    house_work = next(module for module in modules if module.id == "house_work")

    assert house_work.status == "answered"
    assert house_work.signals[0].source == "permits"


def test_license_registry_marks_operator_empty_when_city_is_covered() -> None:
    location = LocationInput(
        address="123 MAIN ST, CHICAGO, IL, 60601",
        latitude=41.8781,
        longitude=-87.6298,
    )
    modules = build_modules(
        "commercial",
        [],
        build_place_graph(location.address, "commercial", []),
        location,
    )
    operators = next(module for module in modules if module.id == "business_activity")

    assert operators.status == "empty"


def test_crime_answers_neighborhood_with_count_nodes() -> None:
    signals = [_crime_signal()]
    graph = build_place_graph("1 DR CARLTON B GOODLETT PL", "commercial", signals)
    modules = build_modules("commercial", signals, graph)
    nearby = next(module for module in modules if module.id == "neighborhood")

    assert nearby.status == "answered"
    assert nearby.signals[0].source == "crime_nearby"
    assert {entity.kind for entity in graph.entities} >= {"context"}
    assert {edge.rel for edge in graph.edges if edge.capability == "neighborhood"} == {"NEARBY"}


def test_san_francisco_pin_marks_neighborhood_empty_without_crime() -> None:
    location = LocationInput(
        address="1 DR CARLTON B GOODLETT PL, SAN FRANCISCO, CA, 94102",
        latitude=37.7793,
        longitude=-122.4193,
    )
    modules = build_modules(
        "residential",
        [],
        build_place_graph(location.address, "residential", []),
        location,
    )
    nearby = next(module for module in modules if module.id == "neighborhood")
    assert nearby.status == "empty"


def test_chicago_pin_keeps_neighborhood_uncovered() -> None:
    location = LocationInput(
        address="123 MAIN ST, CHICAGO, IL, 60601",
        latitude=41.8781,
        longitude=-87.6298,
    )
    modules = build_modules(
        "commercial",
        [],
        build_place_graph(location.address, "commercial", []),
        location,
    )
    nearby = next(module for module in modules if module.id == "neighborhood")
    assert nearby.status == "uncovered"


def _crime_signal() -> SignalRead:
    return SignalRead(
        source="crime_nearby",
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
