from datetime import UTC, datetime

from backend.brief import SignalRead, build_place_graph, normalize_entity_key


def test_normalize_strips_legal_suffixes() -> None:
    assert normalize_entity_key("Cafe Luna Inc.") == normalize_entity_key("CAFE LUNA LLC")


def test_two_license_spellings_become_one_business() -> None:
    graph = build_place_graph(
        "123 MAIN ST, CHICAGO, IL, 60601",
        "commercial",
        [
            _license("CAFE LUNA INC", "Retail Food"),
            _license("Cafe Luna LLC", "Retail Food"),
        ],
    )

    businesses = [entity for entity in graph.entities if entity.kind == "business"]
    assert len(businesses) == 1
    assert businesses[0].key == "CAFE LUNA"
    assert {edge.rel for edge in graph.edges} >= {"OPERATED_AT", "LICENSED"}
    assert {edge.origin for edge in graph.edges} == {"Chicago Business Licenses"}


def test_permit_and_license_stay_related_through_the_place() -> None:
    graph = build_place_graph(
        "100 Main St Apt 4",
        "residential",
        [
            _license("JOE LANDSCAPING LLC", "Landscape"),
            _permit("Reroof", contractor="Joe Landscaping"),
        ],
    )

    keys = {entity.key for entity in graph.entities}
    assert "JOE LANDSCAPING" in keys
    joe = next(entity for entity in graph.entities if entity.key == "JOE LANDSCAPING")
    joe_edges = {edge.rel for edge in graph.edges if edge.entity_id == joe.id}
    assert {"OPERATED_AT", "SERVICED"} <= joe_edges
    house_work = [edge for edge in graph.edges if edge.capability == "house_work"]
    assert house_work
    work = next(entity for entity in graph.entities if entity.kind == "work")
    assert any(
        edge.from_id == joe.id and edge.entity_id == work.id and edge.rel == "SERVICED"
        for edge in graph.edges
    )


def test_crime_becomes_neighborhood_slices() -> None:
    graph = build_place_graph(
        "1 DR CARLTON B GOODLETT PL",
        "residential",
        [
            SignalRead(
                source="crime_nearby",
                signal_type="trend",
                observed_at=datetime(2026, 8, 31, tzinfo=UTC),
                value={
                    "burglary": 5,
                    "vehicle": 8,
                    "robbery": 0,
                    "vandalism": 3,
                    "total_incidents": 16,
                    "radius_meters": 400,
                    "window_days": 365,
                },
                summary="16 incidents within 400m in the last 12 months.",
                is_anomaly=False,
                confidence=1.0,
            )
        ],
    )

    labels = {entity.label for entity in graph.entities}
    assert labels == {"Nearby incidents", "Burglary", "Vehicle theft", "Vandalism"}
    assert all(edge.rel == "NEARBY" for edge in graph.edges)
    assert {edge.origin for edge in graph.edges} == {"SFPD incidents"}
    burglary = next(edge for edge in graph.edges if "burglary" in edge.id)
    assert burglary.summary.startswith("5 burglary")


def _license(name: str, license_type: str) -> SignalRead:
    return SignalRead(
        source="biz_licenses",
        signal_type="activity",
        observed_at=datetime(2026, 1, 15, tzinfo=UTC),
        value={
            "legal_name": name,
            "license_type": license_type,
            "source_name": "Chicago Business Licenses",
        },
        summary=f"A {license_type.lower()} license for {name} was issued.",
        is_anomaly=False,
        confidence=1.0,
    )


def _permit(permit_type: str, contractor: str | None = None) -> SignalRead:
    value: dict[str, str] = {"permit_id": "P-100", "permit_type": permit_type}
    if contractor:
        value["contractor"] = contractor
    return SignalRead(
        source="permits",
        signal_type="activity",
        observed_at=datetime(2026, 2, 1, tzinfo=UTC),
        value=value,
        summary=f"A {permit_type.lower()} permit was issued.",
        is_anomaly=False,
        confidence=1.0,
    )
