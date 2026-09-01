from __future__ import annotations

from collections.abc import Sequence

from ..fetch import LocationInput
from ..place import CapabilitySpec, PlaceClass, capabilities_for_class, covering_providers
from .models import BriefModule, PlaceGraph, SignalRead


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
