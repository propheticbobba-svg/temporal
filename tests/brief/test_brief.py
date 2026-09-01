from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.brief import BriefRequest, build_brief
from backend.store import Base, Location, Signal


def test_build_brief_returns_null_scores_for_empty_categories() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        location = Location(address="100 Main St")
        session.add(location)
        session.flush()
        session.add(
            Signal(
                location_id=location.id,
                source="permits",
                signal_type="activity",
                observed_at=datetime(2026, 1, 15, tzinfo=UTC),
                value={"permit_id": "P-100"},
                summary="A building permit was issued with status issued.",
                is_anomaly=False,
                confidence=1.0,
            )
        )
        session.commit()

        brief = build_brief(session, BriefRequest(address="100 Main St"))

    assert brief.regulatory_standing.score == 0.85
    assert brief.regulatory_standing.signals[0].source == "permits"
    assert brief.physical_condition.score is None
    assert brief.operational_activity.score is None
    assert brief.environmental_context.score is None
    assert brief.signal_count == 1
    assert brief.anomaly_flags == []
    assert brief.place_class == "residential"
    assert brief.place_class_assumed is True
    assert {module.id for module in brief.modules} == {
        "occupancy",
        "tenancy",
        "house_work",
        "household_services",
        "neighborhood",
    }
    house_work = next(module for module in brief.modules if module.id == "house_work")
    assert house_work.status == "answered"
    assert house_work.signals[0].source == "permits"
    assert brief.narrative.startswith("This place reads as a residence")
    assert "A building permit was issued with status issued." in brief.narrative


def test_crime_only_environmental_context_has_null_score_not_zero() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        location = Location(address="1 Market St")
        session.add(location)
        session.flush()
        session.add(
            Signal(
                location_id=location.id,
                source="crime_nearby",
                signal_type="trend",
                observed_at=datetime(2026, 8, 31, tzinfo=UTC),
                value={"total_incidents": 20, "burglary": 5},
                summary=(
                    "20 incidents within 400m in the last 12 months "
                    "(5 burglary, 8 vehicle, 2 robbery, 5 vandalism)."
                ),
                is_anomaly=False,
                confidence=1.0,
            )
        )
        session.commit()

        brief = build_brief(session, BriefRequest(address="1 Market St"))

    assert brief.environmental_context.score is None
    assert brief.environmental_context.score != 0.0
    assert brief.environmental_context.score != 0.85
    assert brief.environmental_context.summary is not None
    assert brief.environmental_context.signals[0].source == "crime_nearby"


def test_mixed_environmental_context_scores_non_crime_signals_only() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        location = Location(address="1 Market St")
        session.add(location)
        session.flush()
        session.add_all(
            [
                Signal(
                    location_id=location.id,
                    source="crime_nearby",
                    signal_type="trend",
                    observed_at=datetime(2026, 8, 31, tzinfo=UTC),
                    value={"total_incidents": 20},
                    summary="20 incidents within 400m in the last 12 months.",
                    is_anomaly=False,
                    confidence=1.0,
                ),
                Signal(
                    location_id=location.id,
                    source="environmental",
                    signal_type="trend",
                    observed_at=datetime(2026, 8, 30, tzinfo=UTC),
                    value={"aqi": 42},
                    summary="Air quality is moderate.",
                    is_anomaly=False,
                    confidence=1.0,
                ),
            ]
        )
        session.commit()

        brief = build_brief(session, BriefRequest(address="1 Market St"))

    assert brief.environmental_context.score == 0.85
    assert {signal.source for signal in brief.environmental_context.signals} == {
        "crime_nearby",
        "environmental",
    }


def test_build_brief_excludes_geocode_signals() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        location = Location(address="100 Main St")
        session.add(location)
        session.flush()
        session.add(
            Signal(
                location_id=location.id,
                source="geocode",
                signal_type="baseline",
                observed_at=datetime(2026, 1, 1, tzinfo=UTC),
                value={"matched_address": "100 MAIN ST"},
                summary="The address was resolved to 100 MAIN ST.",
                is_anomaly=False,
                confidence=1.0,
            )
        )
        session.commit()

        brief = build_brief(session, BriefRequest(address="100 Main St"))

    assert brief.physical_condition.signals == []
