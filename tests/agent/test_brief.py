from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agent.brief import build_brief
from agent.schema import BriefRequest
from db.models import Base, Location, Signal


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
    }
    house_work = next(module for module in brief.modules if module.id == "house_work")
    assert house_work.status == "answered"
    assert house_work.signals[0].source == "permits"
    assert brief.narrative.startswith("This place reads as a residence")
    assert "A building permit was issued with status issued." in brief.narrative


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
