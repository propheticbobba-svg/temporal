from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .fetch import BaseIngester, BizLicensesIngester, JsonObject, LocationInput, SignalType
from .place import (
    PLACE_CLASS_LABELS,
    STALENESS_BY_SOURCE,
    CapabilitySpec,
    PlaceClass,
    RefreshInterval,
    capabilities_for_class,
    covering_providers,
    is_refresh_due,
    refresh_source,
)
from .store import BriefSnapshot, Location, Signal, SourceWatermark

BriefCategoryName: TypeAlias = (
    Literal[
        "physical_condition",
        "regulatory_standing",
        "operational_activity",
        "environmental_context",
    ]
)
ModuleStatus: TypeAlias = Literal["answered", "empty", "uncovered"]
EntityKind: TypeAlias = Literal["person", "business", "contractor", "work"]
EdgeRel: TypeAlias = Literal[
    "LIVED_AT",
    "TENANT_OF",
    "OWNED_BY",
    "OPERATED_AT",
    "LICENSED",
    "WORKED_ON",
    "SERVICED",
    "INSPECTED",
]


class BriefRequest(BaseModel):
    address: str = Field(min_length=1)


class SignalRead(BaseModel):
    source: str
    signal_type: SignalType
    observed_at: datetime
    value: JsonObject
    summary: str
    is_anomaly: bool
    confidence: float = Field(ge=0.0, le=1.0)


class CategoryBrief(BaseModel):
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    summary: str | None = None
    signals: list[SignalRead] = Field(default_factory=list)


class BriefModule(BaseModel):
    id: str
    title: str
    question: str
    trail: str
    status: ModuleStatus
    summary: str
    signals: list[SignalRead] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)


class GraphEntity(BaseModel):
    id: str
    kind: EntityKind
    label: str
    key: str


class GraphEdge(BaseModel):
    id: str
    rel: EdgeRel
    from_id: str = "place"
    entity_id: str
    capability: str
    source: str
    origin: str | None = None
    observed_at: datetime
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)


class PlaceGraph(BaseModel):
    place_id: str
    place_label: str
    entities: list[GraphEntity] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class Brief(BaseModel):
    address: str
    generated_at: datetime
    narrative: str
    anomaly_flags: list[str] = Field(default_factory=list)
    signal_count: int = Field(default=0, ge=0)
    place_class: PlaceClass
    place_class_label: str
    place_class_assumed: bool
    place_class_reasons: list[str] = Field(default_factory=list)
    modules: list[BriefModule] = Field(default_factory=list)
    graph: PlaceGraph
    physical_condition: CategoryBrief
    regulatory_standing: CategoryBrief
    operational_activity: CategoryBrief
    environmental_context: CategoryBrief
    business_license_source_count: int = Field(default=0, ge=0)
    business_license_coverage_note: str | None = None


INDUSTRIAL_TOKENS = (
    "warehouse",
    "depot",
    "terminal",
    "yard",
    "plant",
    "mill",
    "industrial",
    "freight",
    "logistics",
    "distribution",
)
COMMERCIAL_TOKENS = ("suite", "ste", "retail", "plaza", "mall", "shop", "storefront")
RESIDENTIAL_TOKENS = ("apt", "apartment", "condo", "residence", "dwelling")
ASSUMED_WEIGHT = 0.5
Vote = tuple[PlaceClass, float, str]


class PlaceClassification(BaseModel):
    place_class: PlaceClass
    label: str
    assumed: bool
    scores: dict[PlaceClass, float]
    reasons: list[str] = Field(default_factory=list)


def classify_place(address: str, signals: Sequence[SignalRead] = ()) -> PlaceClassification:
    scores: dict[PlaceClass, float] = {
        "residential": 0.0,
        "commercial": 0.0,
        "industrial": 0.0,
        "mixed": 0.0,
    }
    reasons: list[str] = []

    for place_class, weight, reason in _address_votes(address):
        scores[place_class] += weight
        reasons.append(reason)

    for signal in signals:
        for place_class, weight, reason in _signal_votes(signal):
            scores[place_class] += weight
            reasons.append(reason)

    return _decide(scores, reasons)


def _address_votes(address: str) -> Iterator[Vote]:
    text = address.lower()
    for token in INDUSTRIAL_TOKENS:
        if _has_token(text, token):
            yield "industrial", 2.0, f"Address token “{token}” votes industrial."
            break
    for token in COMMERCIAL_TOKENS:
        if _has_token(text, token):
            yield "commercial", 1.2, f"Address token “{token}” votes commercial."
            break
    for token in RESIDENTIAL_TOKENS:
        if _has_token(text, token):
            yield "residential", 1.5, f"Address token “{token}” votes residential."
            break


def _signal_votes(signal: SignalRead) -> Iterator[Vote]:
    value = signal.value
    use_code = _text(value, "land_use", "use_code", "property_class")
    if use_code:
        guessed = _class_from_text(use_code)
        if guessed is not None:
            yield guessed, 3.0, f"Assessor use “{use_code}” votes {guessed}."

    blob = " ".join(
        part
        for part in (
            _text(value, "license_type", "legal_name", "doing_business_as"),
            _text(value, "permit_type", "description"),
            signal.summary,
        )
        if part
    )
    if signal.source == "biz_licenses":
        if _class_from_text(blob) == "industrial":
            yield "industrial", 2.2, "A warehouse or industrial license is on file."
        else:
            yield "commercial", 1.8, "A business license is on file."
        return
    if signal.source == "permits":
        guessed = _class_from_text(blob)
        if guessed is not None:
            yield guessed, 1.0, f"Permit language votes {guessed}."


def _class_from_text(text: str) -> PlaceClass | None:
    lowered = text.lower()
    if any(_has_token(lowered, token) for token in INDUSTRIAL_TOKENS):
        return "industrial"
    if any(_has_token(lowered, token) for token in RESIDENTIAL_TOKENS + ("house", "housing")):
        return "residential"
    if any(_has_token(lowered, token) for token in COMMERCIAL_TOKENS + ("office", "retail")):
        return "commercial"
    return None


def _decide(scores: dict[PlaceClass, float], reasons: list[str]) -> PlaceClassification:
    residential = scores["residential"]
    commercial = scores["commercial"]
    industrial = scores["industrial"]
    total = residential + commercial + industrial

    if industrial >= 2.0 and industrial > commercial and industrial > residential:
        chosen: PlaceClass = "industrial"
    elif (
        residential >= 1.5
        and commercial >= 1.5
        and abs(residential - commercial) < 0.8
        and industrial < max(residential, commercial)
    ):
        chosen = "mixed"
    elif commercial >= 1.5 and commercial > residential and commercial >= industrial:
        chosen = "commercial"
    elif industrial >= 1.5 and industrial > residential:
        chosen = "industrial"
    else:
        chosen = "residential"

    return PlaceClassification(
        place_class=chosen,
        label=PLACE_CLASS_LABELS[chosen],
        assumed=total < ASSUMED_WEIGHT,
        scores=scores,
        reasons=_collapse_reasons(reasons),
    )


def _collapse_reasons(reasons: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    order: list[str] = []
    for reason in reasons:
        if reason not in counts:
            order.append(reason)
            counts[reason] = 0
        counts[reason] += 1

    collapsed: list[str] = []
    for reason in order:
        count = counts[reason]
        if count == 1:
            collapsed.append(reason)
        elif reason == "A business license is on file.":
            collapsed.append(f"{count} business licenses are on file.")
        elif reason == "A warehouse or industrial license is on file.":
            collapsed.append(f"{count} warehouse or industrial licenses are on file.")
        else:
            collapsed.append(f"{reason} ×{count}")
    return collapsed


def _has_token(text: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", text, flags=re.IGNORECASE) is not None


def _text(value: Mapping[str, object] | JsonObject, *keys: str) -> str:
    parts: list[str] = []
    for key in keys:
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            parts.append(item.strip())
    return " ".join(parts)


LEGAL_SUFFIXES = re.compile(
    r"\b(INC|INCORPORATED|LLC|L\.L\.C|LTD|CORP|CORPORATION|CO|COMPANY|LP|PLLC|PC|PA)\b"
)
NON_ALNUM = re.compile(r"[^A-Z0-9\s]")
SPACES = re.compile(r"\s+")
INDUSTRIAL_MARKERS = (
    "warehouse",
    "depot",
    "freight",
    "logistics",
    "industrial",
    "distribution",
    "terminal",
)


def build_place_graph(
    address: str,
    place_class: PlaceClass,
    signals: Sequence[SignalRead],
) -> PlaceGraph:
    entities: dict[str, GraphEntity] = {}
    edges: list[GraphEdge] = []
    work_capability = "house_work" if place_class in {"residential", "mixed"} else "site_work"

    for index, signal in enumerate(signals):
        for entity, edge in _project_signal(signal, index, work_capability):
            entities[entity.id] = _prefer_kind(entities.get(entity.id), entity)
            edges.append(edge)

    return PlaceGraph(
        place_id="place",
        place_label=address,
        entities=list(entities.values()),
        edges=edges,
    )


def normalize_entity_key(label: str) -> str:
    text = label.upper()
    text = NON_ALNUM.sub(" ", text)
    text = LEGAL_SUFFIXES.sub(" ", text)
    return SPACES.sub(" ", text).strip()


def _project_signal(
    signal: SignalRead,
    index: int,
    work_capability: str,
) -> list[tuple[GraphEntity, GraphEdge]]:
    if signal.source == "biz_licenses":
        return _project_license(signal, index)
    if signal.source == "permits":
        return _project_permit(signal, index, work_capability)
    return []


def _project_license(signal: SignalRead, index: int) -> list[tuple[GraphEntity, GraphEdge]]:
    label = _first_text(signal.value, "doing_business_as", "legal_name") or "Licensed operator"
    entity = _entity("business", label)
    projected = [
        (
            entity,
            _edge(
                rel="OPERATED_AT",
                entity_id=entity.id,
                capability="business_activity",
                signal=signal,
                edge_id=f"operated-{index}",
            ),
        ),
        (
            entity,
            _edge(
                rel="LICENSED",
                entity_id=entity.id,
                capability="business_activity",
                signal=signal,
                edge_id=f"licensed-{index}",
            ),
        ),
    ]
    if _looks_industrial(signal):
        projected.append(
            (
                entity,
                _edge(
                    rel="OPERATED_AT",
                    entity_id=entity.id,
                    capability="industrial_activity",
                    signal=signal,
                    edge_id=f"industrial-{index}",
                ),
            )
        )
    return projected


def _project_permit(
    signal: SignalRead,
    index: int,
    work_capability: str,
) -> list[tuple[GraphEntity, GraphEdge]]:
    permit_type = _first_text(signal.value, "permit_type") or "Permit"
    permit_id = _first_text(signal.value, "permit_id") or str(index)
    work = _entity("work", f"{permit_type} {permit_id}")
    projected = [
        (
            work,
            _edge(
                rel="WORKED_ON",
                entity_id=work.id,
                capability=work_capability,
                signal=signal,
                edge_id=f"work-{index}",
            ),
        )
    ]
    contractor = _first_text(signal.value, "contractor", "contractor_name")
    if contractor:
        person = _entity("contractor", contractor)
        projected.extend(
            [
                (
                    person,
                    _edge(
                        rel="SERVICED",
                        entity_id=person.id,
                        capability=work_capability,
                        signal=signal,
                        edge_id=f"serviced-{index}",
                    ),
                ),
                (
                    work,
                    _edge(
                        rel="SERVICED",
                        from_id=person.id,
                        entity_id=work.id,
                        capability=work_capability,
                        signal=signal,
                        edge_id=f"serviced-work-{index}",
                    ),
                ),
            ]
        )
    return projected


_KIND_RANK: dict[EntityKind, int] = {
    "person": 3,
    "contractor": 3,
    "business": 2,
    "work": 1,
}


def _entity(kind: EntityKind, label: str) -> GraphEntity:
    key = normalize_entity_key(label) or label.upper()
    return GraphEntity(id=f"entity:{key}", kind=kind, label=label, key=key)


def _prefer_kind(existing: GraphEntity | None, incoming: GraphEntity) -> GraphEntity:
    if existing is None:
        return incoming
    if _KIND_RANK[incoming.kind] > _KIND_RANK[existing.kind]:
        return incoming.model_copy(update={"label": existing.label})
    return existing


def _edge(
    *,
    rel: EdgeRel,
    entity_id: str,
    capability: str,
    signal: SignalRead,
    edge_id: str,
    from_id: str = "place",
) -> GraphEdge:
    return GraphEdge(
        id=edge_id,
        rel=rel,
        from_id=from_id,
        entity_id=entity_id,
        capability=capability,
        source=signal.source,
        origin=_first_text(signal.value, "source_name") or signal.source,
        observed_at=signal.observed_at,
        summary=signal.summary,
        confidence=signal.confidence,
    )


def _looks_industrial(signal: SignalRead) -> bool:
    blob = " ".join(
        part
        for part in (
            _first_text(signal.value, "license_type", "legal_name", "doing_business_as"),
            signal.summary,
        )
        if part
    ).lower()
    return any(re.search(rf"\b{re.escape(marker)}\b", blob) for marker in INDUSTRIAL_MARKERS)


def _first_text(value: object, *keys: str) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in keys:
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


def build_modules(
    place_class: PlaceClass,
    signals: Sequence[SignalRead],
    graph: PlaceGraph,
    location: LocationInput | None = None,
) -> list[BriefModule]:
    return [
        _build_module(spec, signals, graph, location)
        for spec in capabilities_for_class(place_class)
    ]


def _build_module(
    spec: CapabilitySpec,
    signals: Sequence[SignalRead],
    graph: PlaceGraph,
    location: LocationInput | None,
) -> BriefModule:
    edges = [edge for edge in graph.edges if edge.capability == spec.id]
    sources = {edge.source for edge in edges}
    matched = [signal for signal in signals if signal.source in sources]
    entity_ids = list(dict.fromkeys(edge.entity_id for edge in edges))

    if matched or edges:
        return BriefModule(
            id=spec.id,
            title=spec.title,
            question=spec.question,
            trail=spec.trail,
            status="answered",
            summary=matched[0].summary if matched else edges[0].summary,
            signals=list(matched),
            entity_ids=entity_ids,
        )

    if covering_providers(spec, location):
        return BriefModule(
            id=spec.id,
            title=spec.title,
            question=spec.question,
            trail=spec.trail,
            status="empty",
            summary=spec.empty_copy,
        )

    return BriefModule(
        id=spec.id,
        title=spec.title,
        question=spec.question,
        trail=spec.trail,
        status="uncovered",
        summary=spec.uncovered_copy,
    )


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


async def load_brief(
    session: Session,
    request: BriefRequest,
    ingesters: tuple[BaseIngester, ...],
) -> Brief:
    location = session.scalars(
        select(Location).where(Location.address == request.address)
    ).one_or_none()
    if location is None:
        return build_brief(session, request)

    location_input = LocationInput(
        address=location.address,
        latitude=location.latitude,
        longitude=location.longitude,
    )
    now = datetime.now(tz=UTC)
    refreshed_any = False

    for ingester in ingesters:
        if not _source_is_due(session, location.id, ingester.source, now):
            continue
        if await refresh_source(session, location, location_input, ingester):
            _upsert_watermark(session, location.id, ingester.source, now)
            refreshed_any = True

    snapshot = _load_snapshot(session, location.id)
    if snapshot is not None and not refreshed_any:
        current = _brief_from_snapshot(snapshot.payload)
        if current is not None:
            return current

    brief = _with_coverage(build_brief(session, request), location_input, ingesters)
    _upsert_snapshot(session, location.id, brief)
    session.commit()
    return brief


def _source_is_due(session: Session, location_id: int, source: str, now: datetime) -> bool:
    interval = STALENESS_BY_SOURCE.get(source, RefreshInterval.WEEKLY)
    watermark = session.scalars(
        select(SourceWatermark).where(
            SourceWatermark.location_id == location_id,
            SourceWatermark.source == source,
        )
    ).one_or_none()
    refreshed_at = watermark.refreshed_at if watermark is not None else None
    return is_refresh_due(interval, refreshed_at, now=now)


def _brief_from_snapshot(payload: object) -> Brief | None:
    try:
        brief = Brief.model_validate(payload)
    except ValidationError:
        return None
    if not brief.modules:
        return None
    if len(brief.place_class_reasons) != len(set(brief.place_class_reasons)):
        return None
    return brief


def _load_snapshot(session: Session, location_id: int) -> BriefSnapshot | None:
    return session.scalars(
        select(BriefSnapshot).where(BriefSnapshot.location_id == location_id)
    ).one_or_none()


def _upsert_watermark(session: Session, location_id: int, source: str, now: datetime) -> None:
    watermark = session.scalars(
        select(SourceWatermark).where(
            SourceWatermark.location_id == location_id,
            SourceWatermark.source == source,
        )
    ).one_or_none()
    if watermark is None:
        session.add(
            SourceWatermark(location_id=location_id, source=source, refreshed_at=now)
        )
        return
    watermark.refreshed_at = now


def _upsert_snapshot(session: Session, location_id: int, brief: Brief) -> None:
    snapshot = _load_snapshot(session, location_id)
    payload = brief.model_dump(mode="json")
    if snapshot is None:
        session.add(
            BriefSnapshot(
                location_id=location_id,
                generated_at=brief.generated_at,
                payload=payload,
            )
        )
        return
    snapshot.generated_at = brief.generated_at
    snapshot.payload = payload


def _with_coverage(
    brief: Brief,
    location_input: LocationInput,
    ingesters: tuple[BaseIngester, ...],
) -> Brief:
    source_count = _business_license_source_count(location_input, ingesters)
    if source_count is None:
        return brief

    coverage_note = (
        "No configured public license source covers this location yet."
        if source_count == 0
        else None
    )
    return brief.model_copy(
        update={
            "business_license_source_count": source_count,
            "business_license_coverage_note": coverage_note,
        }
    )


def _business_license_source_count(
    location_input: LocationInput,
    ingesters: tuple[BaseIngester, ...],
) -> int | None:
    for ingester in ingesters:
        if isinstance(ingester, BizLicensesIngester):
            return len(ingester.matching_sources(location_input))
    return None
