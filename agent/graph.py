from __future__ import annotations

import re
from collections.abc import Sequence

from agent.schema import EdgeRel, EntityKind, GraphEdge, GraphEntity, PlaceGraph, SignalRead
from ingestion.capabilities import PlaceClass

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
