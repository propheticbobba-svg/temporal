from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.graph import build_place_graph
from agent.modules import build_modules
from agent.place_class import PlaceClassification, classify_place
from agent.schema import (
    Brief,
    BriefCategoryName,
    BriefModule,
    BriefRequest,
    CategoryBrief,
    SignalRead,
)
from db.models import Location, Signal
from ingestion.schema import LocationInput

CATEGORY_NAMES: tuple[BriefCategoryName, ...] = (
    "physical_condition",
    "regulatory_standing",
    "operational_activity",
    "environmental_context",
)

SOURCE_TO_CATEGORY: dict[str, BriefCategoryName] = {
    "permits": "regulatory_standing",
    "biz_licenses": "operational_activity",
    "satellite": "physical_condition",
    "environmental": "environmental_context",
}


def build_brief(session: Session, request: BriefRequest) -> Brief:
    location = _load_location(session, request.address)
    location_input = (
        LocationInput(
            address=location.address,
            latitude=location.latitude,
            longitude=location.longitude,
        )
        if location is not None
        else LocationInput(address=request.address)
    )
    signals = _load_signals(session, request)
    grouped = _group_signals(signals)
    reads = [signal for category in grouped.values() for signal in category]
    classification = classify_place(request.address, reads)
    graph = build_place_graph(request.address, classification.place_class, reads)
    modules = build_modules(classification.place_class, reads, graph, location_input)

    return Brief(
        address=request.address,
        generated_at=datetime.now(tz=UTC),
        narrative=_narrative(classification, modules, reads),
        anomaly_flags=_anomaly_flags(reads),
        signal_count=len(reads),
        place_class=classification.place_class,
        place_class_label=classification.label,
        place_class_assumed=classification.assumed,
        place_class_reasons=classification.reasons,
        modules=modules,
        graph=graph,
        physical_condition=_build_category(grouped["physical_condition"]),
        regulatory_standing=_build_category(grouped["regulatory_standing"]),
        operational_activity=_build_category(grouped["operational_activity"]),
        environmental_context=_build_category(grouped["environmental_context"]),
    )


def _load_location(session: Session, address: str) -> Location | None:
    return session.scalars(select(Location).where(Location.address == address)).one_or_none()


def _load_signals(session: Session, request: BriefRequest) -> list[Signal]:
    statement = (
        select(Signal)
        .join(Location)
        .where(Location.address == request.address)
        .where(Signal.source != "geocode")
        .order_by(Signal.observed_at.desc())
    )
    return list(session.scalars(statement).all())


def _group_signals(signals: list[Signal]) -> dict[BriefCategoryName, list[SignalRead]]:
    grouped: dict[BriefCategoryName, list[SignalRead]] = {name: [] for name in CATEGORY_NAMES}

    for signal in signals:
        category = SOURCE_TO_CATEGORY.get(signal.source, _fallback_category(signal))
        grouped[category].append(_to_signal_read(signal))

    return grouped


def _to_signal_read(signal: Signal) -> SignalRead:
    return SignalRead(
        source=signal.source,
        signal_type=signal.signal_type,
        observed_at=signal.observed_at,
        value=signal.value,
        summary=signal.summary,
        is_anomaly=signal.is_anomaly,
        confidence=signal.confidence,
    )


def _fallback_category(signal: Signal) -> BriefCategoryName:
    if signal.signal_type == "activity":
        return "operational_activity"
    if signal.signal_type == "baseline":
        return "physical_condition"
    if signal.signal_type == "trend":
        return "environmental_context"
    return "regulatory_standing"


def _build_category(signals: list[SignalRead]) -> CategoryBrief:
    if not signals:
        return CategoryBrief()

    return CategoryBrief(
        score=_score(signals),
        summary=signals[0].summary,
        signals=signals,
    )


def _score(signals: list[SignalRead]) -> float:
    weighted_scores = [
        signal.confidence * (0.35 if signal.is_anomaly else 0.85) for signal in signals
    ]
    total_confidence = sum(signal.confidence for signal in signals)
    if total_confidence == 0:
        return 0.0
    return round(sum(weighted_scores) / total_confidence, 2)


def _narrative(
    classification: PlaceClassification,
    modules: list[BriefModule],
    signals: list[SignalRead],
) -> str:
    opened = ", ".join(module.title.lower() for module in modules)
    if classification.assumed:
        lead = (
            f"This place reads as a {classification.label.lower()} — assumed, because we have "
            f"little type evidence yet."
        )
    else:
        why = classification.reasons[0] if classification.reasons else "the public record"
        lead = f"This place reads as {classification.label.lower()}. {why}"

    trails = f"We opened {opened}." if opened else "No class-specific trails are configured."
    answered = [
        module.summary
        for module in modules
        if module.status == "answered" and module.summary
    ]
    if answered:
        return f"{lead} {trails} {answered[0]}"
    if signals:
        return f"{lead} {trails}"
    return (
        f"{lead} {trails} Those trails are not covered by a live feed for this address, "
        "so we are not inventing occupants, tenants, or contractors."
    )


def _anomaly_flags(signals: list[SignalRead]) -> list[str]:
    return [signal.summary for signal in signals if signal.is_anomaly]
