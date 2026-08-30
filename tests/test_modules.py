from datetime import UTC, datetime

from backend.brief import SignalRead, build_modules, build_place_graph
from backend.fetch import LocationInput


def test_residential_opens_home_trails_and_keeps_uncovered_honest() -> None:
    graph = build_place_graph("100 Main St Apt 4", "residential", [])
    modules = build_modules("residential", [], graph)
    by_id = {module.id: module for module in modules}

    assert set(by_id) == {"occupancy", "tenancy", "house_work", "household_services"}
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
