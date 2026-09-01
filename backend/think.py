"""Fuse fetched records onto the place-graph template via Vertex DeepSeek.

Uses Application Default Credentials. Does not invent people, firms, or edges.
Unknown module or edge ids in the model reply are dropped.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx
from pydantic import ValidationError

from .brief import (
    Brief,
    GraphBridge,
    GraphEdge,
    GraphFusion,
    GraphGap,
    GraphPlan,
    GraphThought,
    SourceNote,
    candidate_anomalies,
)
from .store import get_settings

logger = logging.getLogger(__name__)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


async def attach_fusion(brief: Brief) -> Brief:
    if brief.fusion is not None:
        fusion = _with_sources(brief, brief.fusion)
        return _with_flags(brief, fusion)
    if not get_settings().graph_ai or not worth_fusing(brief):
        return _with_flags(brief, _local_fusion(brief))
    raw = await complete_fusion(brief)
    if raw is None:
        return _with_flags(brief, _local_fusion(brief))
    return _with_flags(brief, ground_fusion(brief, raw))


def _with_flags(brief: Brief, fusion: GraphFusion) -> Brief:
    return brief.model_copy(update={"fusion": fusion, "anomaly_flags": fusion.anomalies})


def _local_fusion(brief: Brief) -> GraphFusion:
    return GraphFusion(
        place_read=brief.narrative,
        sources_read=_default_sources_read(brief),
        sources=fallback_sources(brief),
        gaps=_local_gaps(brief),
        bridges=_local_bridges(brief),
        thoughts=_local_thoughts(brief),
        anomalies=candidate_anomalies(brief),
        anomalies_judged=True,
    )


def _with_sources(brief: Brief, fusion: GraphFusion) -> GraphFusion:
    notes = _unique_origins(
        [
            note.model_copy(update={"when": _when(note.when)})
            for note in fusion.sources
        ]
        if fusion.sources
        else fallback_sources(brief)
    )
    read = fusion.sources_read or _default_sources_read(brief)
    gaps = fusion.gaps or _local_gaps(brief)
    bridges = fusion.bridges or _local_bridges(brief)
    judged = fusion.anomalies_judged
    flags = fusion.anomalies if judged else candidate_anomalies(brief)
    thoughts = _fill_thought_links(brief, fusion.thoughts or _local_thoughts(brief, bridges, flags), bridges, flags)
    update = {
        "sources": notes,
        "sources_read": read,
        "gaps": gaps,
        "bridges": bridges,
        "thoughts": thoughts,
        "anomalies": flags,
        "anomalies_judged": True,
    }
    if (
        notes == fusion.sources
        and read == fusion.sources_read
        and gaps == fusion.gaps
        and bridges == fusion.bridges
        and thoughts == fusion.thoughts
        and flags == fusion.anomalies
        and judged
    ):
        return fusion
    return fusion.model_copy(update=update)


async def complete_fusion(brief: Brief) -> GraphFusion | None:
    settings = get_settings()
    url = (
        f"https://aiplatform.googleapis.com/v1/projects/{settings.vertex_project}"
        f"/locations/{settings.vertex_location}/endpoints/openapi/chat/completions"
    )
    try:
        token = _access_token()
        payload = {
            "model": settings.vertex_model,
            "max_tokens": 640,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": json.dumps(_facts(brief), default=str)},
            ],
        }
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            logger.warning("Graph fusion skipped; Vertex returned %s.", response.status_code)
            return None
        content = response.json()["choices"][0]["message"]["content"]
        parsed = _fusion_from_model(_parse_json(content))
        return parsed.model_copy(update={"model": settings.vertex_model})
    except Exception as exc:
        logger.warning("Graph fusion skipped: %s", type(exc).__name__)
        return None


def _fusion_from_model(payload: dict[str, Any]) -> GraphFusion:
    try:
        return GraphFusion.model_validate(payload)
    except ValidationError:
        payload.pop("plan", None)
        payload.pop("sources", None)
        payload.pop("gaps", None)
        payload.pop("bridges", None)
        payload.pop("thoughts", None)
        payload.pop("anomalies", None)
        return GraphFusion.model_validate(payload)


def ground_fusion(brief: Brief, raw: GraphFusion) -> GraphFusion:
    module_ids = {module.id for module in brief.modules}
    edge_ids = {edge.id for edge in brief.graph.edges}
    trails = []
    for trail in raw.trails:
        if trail.module_id not in module_ids:
            continue
        trails.append(
            trail.model_copy(
                update={
                    "headline": _clip(trail.headline, 150),
                    "beats": [
                        beat.model_copy(
                            update={
                                "when": _when(beat.when),
                                "line": _clip(beat.line, 150),
                            }
                        )
                        for beat in trail.beats
                        if beat.edge_id in edge_ids
                    ],
                }
            )
        )
    plan = None
    if raw.plan is not None:
        expand = [item for item in raw.plan.expand if item in module_ids]
        tight = [item for item in raw.plan.tight if item in module_ids and item not in expand]
        lead = raw.plan.lead if raw.plan.lead in module_ids else None
        plan = GraphPlan(expand=expand, tight=tight, lead=lead)
    notes = _unique_origins(
        [
            SourceNote(
                origin=_clip(note.origin, 80),
                proved=_clip(note.proved, 180),
                when=_when(note.when),
                edge_id=note.edge_id,
            )
            for note in raw.sources
            if not note.edge_id or note.edge_id in edge_ids
        ]
    )
    if not notes:
        notes = fallback_sources(brief)
    bridges = _ground_bridges(brief, raw.bridges) or _local_bridges(brief)
    flags = _ground_anomalies(brief, raw.anomalies)
    return GraphFusion(
        place_read=_clip(raw.place_read, 260),
        trails=trails,
        model=raw.model,
        plan=plan,
        sources_read=_clip(raw.sources_read, 240) or _default_sources_read(brief),
        sources=notes[:4],
        gaps=_ground_gaps(brief, raw.gaps) or _local_gaps(brief),
        bridges=bridges,
        thoughts=_ground_thoughts(brief, raw.thoughts) or _local_thoughts(brief, bridges, flags),
        anomalies=flags,
        anomalies_judged=True,
    )


def _local_gaps(brief: Brief) -> list[GraphGap]:
    return [
        GraphGap(module_id=module.id, why=_clip(module.summary, 160))
        for module in brief.modules
        if module.status in {"uncovered", "empty"}
    ]


def _local_bridges(brief: Brief) -> list[GraphBridge]:
    entities = {entity.id: entity for entity in brief.graph.entities}
    by_key: dict[str, dict[str, GraphEdge]] = {}
    for edge in brief.graph.edges:
        entity = entities.get(edge.entity_id)
        if entity is None:
            continue
        by_key.setdefault(entity.key, {}).setdefault(edge.capability, edge)
    bridges: list[GraphBridge] = []
    for caps in by_key.values():
        items = list(caps.items())
        if len(items) < 2:
            continue
        for index, (cap_a, edge_a) in enumerate(items):
            for cap_b, edge_b in items[index + 1 :]:
                if edge_a.entity_id == edge_b.entity_id:
                    continue
                bridges.append(
                    GraphBridge(
                        from_id=edge_a.entity_id,
                        to_id=edge_b.entity_id,
                        why=(
                            f"Same name on {cap_a.replace('_', ' ')} "
                            f"and {cap_b.replace('_', ' ')}."
                        ),
                        confidence=min(edge_a.confidence, edge_b.confidence),
                        edge_ids=[edge_a.id, edge_b.id],
                    )
                )
    return bridges[:3]


def _ground_gaps(brief: Brief, raw: list[GraphGap]) -> list[GraphGap]:
    status = {module.id: module.status for module in brief.modules}
    gaps: list[GraphGap] = []
    seen: set[str] = set()
    for gap in raw:
        if gap.module_id in seen or status.get(gap.module_id) not in {"uncovered", "empty"}:
            continue
        seen.add(gap.module_id)
        gaps.append(GraphGap(module_id=gap.module_id, why=_clip(gap.why, 160)))
    return gaps


def _ground_bridges(brief: Brief, raw: list[GraphBridge]) -> list[GraphBridge]:
    entity_ids = {entity.id for entity in brief.graph.entities}
    keys = {entity.id: entity.key for entity in brief.graph.entities}
    edges = {edge.id: edge for edge in brief.graph.edges}
    bridges: list[GraphBridge] = []
    seen: set[tuple[str, str]] = set()
    for bridge in raw:
        pair = (min(bridge.from_id, bridge.to_id), max(bridge.from_id, bridge.to_id))
        if (
            pair in seen
            or bridge.from_id not in entity_ids
            or bridge.to_id not in entity_ids
            or bridge.from_id == bridge.to_id
        ):
            continue
        cited = [edges[edge_id] for edge_id in bridge.edge_ids if edge_id in edges]
        if not cited:
            continue
        ends = {bridge.from_id, bridge.to_id}
        same_key = keys[bridge.from_id] == keys[bridge.to_id]
        linked = any({edge.from_id, edge.entity_id} == ends for edge in cited)
        if not same_key and not linked:
            continue
        seen.add(pair)
        bridges.append(
            GraphBridge(
                from_id=bridge.from_id,
                to_id=bridge.to_id,
                why=_clip(bridge.why, 140),
                confidence=bridge.confidence,
                edge_ids=[edge.id for edge in cited],
            )
        )
    return bridges[:3]


def _local_thoughts(
    brief: Brief,
    bridges: list[GraphBridge] | None = None,
    flags: list[str] | None = None,
) -> list[GraphThought]:
    thoughts = [
        GraphThought(
            kind="link",
            line=bridge.why,
            from_id=bridge.from_id,
            to_id=bridge.to_id,
            edge_ids=bridge.edge_ids,
        )
        for bridge in (bridges if bridges is not None else _local_bridges(brief))
    ]
    if _has_nearby(brief) and _has_occupant(brief):
        occupant = next((module.id for module in brief.modules if module.id == "business_activity"), "")
        thoughts.append(
            GraphThought(
                kind="link",
                line="Nearby incidents are street context, not who operated here.",
                from_id="neighborhood",
                also_ids=[occupant] if occupant else [],
            )
        )
    for flag in flags if flags is not None else candidate_anomalies(brief):
        thoughts.append(
            GraphThought(kind="watch", line=flag, from_id=_watch_anchor(brief, flag))
        )
    return thoughts[:4]


def _ground_thoughts(brief: Brief, raw: list[GraphThought]) -> list[GraphThought]:
    entity_ids = {entity.id for entity in brief.graph.entities}
    allowed = entity_ids | {brief.graph.place_id} | {module.id for module in brief.modules}
    keys = {entity.id: entity.key for entity in brief.graph.entities}
    edges = {edge.id: edge for edge in brief.graph.edges}
    thoughts: list[GraphThought] = []
    seen: set[tuple[str, str, str]] = set()
    for thought in raw:
        ends = (thought.kind, thought.from_id, thought.to_id)
        if thought.from_id not in allowed or ends in seen:
            continue
        if thought.to_id and thought.to_id not in allowed:
            continue
        cited = [edges[edge_id] for edge_id in thought.edge_ids if edge_id in edges]
        if thought.kind == "link" and thought.to_id:
            if (
                thought.from_id not in entity_ids
                or thought.to_id not in entity_ids
                or thought.from_id == thought.to_id
                or _is_crime_occupant(brief, thought.from_id, thought.to_id)
            ):
                continue
            same_key = keys[thought.from_id] == keys[thought.to_id]
            pair = {thought.from_id, thought.to_id}
            linked = any({edge.from_id, edge.entity_id} == pair for edge in cited)
            if not cited or (not same_key and not linked):
                continue
        seen.add(ends)
        thoughts.append(
            GraphThought(
                kind=thought.kind,
                line=_clip(thought.line, 220),
                from_id=thought.from_id,
                to_id=thought.to_id if thought.kind == "link" else "",
                also_ids=_ground_also(brief, thought, allowed),
                edge_ids=[edge.id for edge in cited],
            )
        )
    return thoughts[:4]


def _fill_thought_links(
    brief: Brief,
    thoughts: list[GraphThought],
    bridges: list[GraphBridge],
    flags: list[str],
) -> list[GraphThought]:
    local = {(item.kind, item.from_id, item.to_id): item for item in _local_thoughts(brief, bridges, flags)}
    filled: list[GraphThought] = []
    for thought in thoughts:
        match = local.get((thought.kind, thought.from_id, thought.to_id))
        if match and match.also_ids and not thought.also_ids:
            filled.append(thought.model_copy(update={"also_ids": match.also_ids}))
        else:
            filled.append(thought)
    return filled


def _ground_also(brief: Brief, thought: GraphThought, allowed: set[str]) -> list[str]:
    entity_ids = {entity.id for entity in brief.graph.entities}
    extra: list[str] = []
    for item in thought.also_ids:
        if item not in allowed or item in {thought.from_id, thought.to_id} or item in extra:
            continue
        if item in entity_ids and (
            (thought.from_id in entity_ids and _is_crime_occupant(brief, thought.from_id, item))
            or (thought.to_id in entity_ids and _is_crime_occupant(brief, thought.to_id, item))
        ):
            continue
        extra.append(item)
    return extra[:3]


def _has_nearby(brief: Brief) -> bool:
    return any(edge.capability == "neighborhood" for edge in brief.graph.edges)


def _has_occupant(brief: Brief) -> bool:
    occupant = {"person", "business", "contractor"}
    return any(entity.kind in occupant for entity in brief.graph.entities)


def _watch_anchor(brief: Brief, flag: str) -> str:
    low = flag.lower()
    for entity in brief.graph.entities:
        if entity.label and entity.label.lower() in low:
            return entity.id
    return brief.graph.place_id


def _is_crime_occupant(brief: Brief, left: str, right: str) -> bool:
    kinds = {entity.id: entity.kind for entity in brief.graph.entities}
    caps = {edge.entity_id: edge.capability for edge in brief.graph.edges}
    near = kinds.get(left) == "context" or kinds.get(right) == "context"
    occupant = {kinds.get(left), kinds.get(right)} & {"person", "business", "contractor"}
    if not (near and occupant):
        return False
    return "neighborhood" in {caps.get(left), caps.get(right)}


def _ground_anomalies(brief: Brief, raw: list[str]) -> list[str]:
    candidates = candidate_anomalies(brief)
    if not raw:
        return []
    names = [entity.label.lower() for entity in brief.graph.entities if entity.label]
    kept: list[str] = []
    for flag in raw:
        text = _clip(flag, 160)
        low = text.lower()
        cited = any(low in item.lower() or item.lower() in low for item in candidates)
        sharp = ("revok", "expir", "stop work", "violation", "burglar", "theft", "robber")
        named = any(name in low for name in names) and any(token in low for token in sharp)
        if cited or named:
            kept.append(text)
    return kept[:3] if kept else candidates[:3]


def fallback_sources(brief: Brief) -> list[SourceNote]:
    notes: list[SourceNote] = []
    seen: set[str] = set()
    for edge in brief.graph.edges:
        origin = edge.origin or edge.source
        if origin in seen:
            continue
        seen.add(origin)
        notes.append(
            SourceNote(
                origin=origin,
                proved=edge.summary,
                when=str(edge.observed_at.year),
                edge_id=edge.id,
            )
        )
    return notes


def _unique_origins(notes: list[SourceNote]) -> list[SourceNote]:
    seen: set[str] = set()
    unique: list[SourceNote] = []
    for note in notes:
        if note.origin in seen:
            continue
        seen.add(note.origin)
        unique.append(note)
    return unique


def _when(value: str) -> str:
    text = _clip(value, 24)
    if len(text) >= 4 and text[:4].isdigit() and (len(text) == 4 or text[4] in "-/"):
        return text[:4]
    return text


def _default_sources_read(brief: Brief) -> str:
    if brief.graph.edges:
        return "These public records produced the graph. Nothing here is inferred."
    return "No covering source produced a record for this place yet."


def worth_fusing(brief: Brief) -> bool:
    if brief.graph.edges:
        return True
    return any(module.status == "answered" for module in brief.modules)


def _facts(brief: Brief) -> dict[str, Any]:
    nearby = [edge for edge in brief.graph.edges if edge.capability == "neighborhood"]
    rest = [edge for edge in brief.graph.edges if edge.capability != "neighborhood"]
    leftover = max(0, 12 - len(nearby))
    recent = nearby + sorted(rest, key=lambda edge: edge.observed_at, reverse=True)[:leftover]
    used = {edge.entity_id for edge in recent}
    graphed = {edge.source for edge in brief.graph.edges}
    extras = [
        {
            "source": signal.source,
            "summary": signal.summary,
            "when": signal.observed_at.isoformat(),
        }
        for category in (
            brief.physical_condition,
            brief.regulatory_standing,
            brief.operational_activity,
            brief.environmental_context,
        )
        for signal in category.signals
        if signal.source not in graphed
    ]
    return {
        "address": brief.address,
        "place_class": brief.place_class,
        "place_class_label": brief.place_class_label,
        "assumed": brief.place_class_assumed,
        "reasons": brief.place_class_reasons,
        "template": [
            {
                "id": module.id,
                "title": module.title,
                "status": module.status,
                "cover": (
                    "on_file"
                    if module.status == "answered"
                    else "empty" if module.status == "empty" else "unwired"
                ),
                "summary": module.summary,
            }
            for module in brief.modules
        ],
        "entities": [
            {"id": entity.id, "kind": entity.kind, "label": entity.label}
            for entity in brief.graph.entities
            if entity.id in used
        ],
        "edges": [
            {
                "id": edge.id,
                "rel": edge.rel,
                "entity_id": edge.entity_id,
                "capability": edge.capability,
                "source": edge.origin or edge.source,
                "when": edge.observed_at.isoformat(),
                "summary": edge.summary,
            }
            for edge in recent
        ],
        "anomaly_candidates": candidate_anomalies(brief),
        **({"other_signals": extras} if extras else {}),
    }


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = _FENCE.sub("", text.strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object")
    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("JSON was not an object")
    return payload


def _clip(value: str, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


_token: tuple[str, float] | None = None


def _access_token() -> str:
    global _token
    now = time.time()
    if _token is not None and _token[1] - 60 > now:
        return _token[0]

    import google.auth
    import urllib3
    from google.auth.transport.urllib3 import Request

    credentials, _project = google.auth.default(
        scopes=("https://www.googleapis.com/auth/cloud-platform",)
    )
    if not credentials.valid:
        credentials.refresh(Request(urllib3.PoolManager()))  # type: ignore[no-untyped-call]
    token = credentials.token
    if not isinstance(token, str) or not token:
        raise RuntimeError("ADC did not return a token")
    expiry = getattr(credentials, "expiry", None)
    until = expiry.timestamp() if expiry is not None else now + 3000
    _token = (token, until)
    return token


_SYSTEM = """Write JSON copy that sits on graph nodes. Fuse only the given entities and edges.
Do not invent people, firms, or work. Neighborhood counts are nearby incidents, not occupants.
Copy is short and specific: no address echo, no type counts, no inventory.
place_read: two sentences about the pin.
Trail headline: one sentence for that trail node.
Beat line: one sentence of the fact; do not lead with the entity name.
Keys: place_read, trails, plan, sources_read, sources, gaps, bridges, thoughts, anomalies.
Trail: module_id, headline, beats[{edge_id, when, line}]. Use existing ids only.
plan.expand = answered trails to open. plan.tight = empty trails. plan.lead = strongest trail.
gaps: uncovered/empty trails only {module_id, why}. One sentence: unwired vs source ran empty.
bridges: only existing entity ids that share a name or a cited edge.
{from_id, to_id, why, confidence, edge_ids}. Max three. No crime-to-occupant links.
thoughts: up to four {kind, line, from_id, to_id, also_ids, edge_ids}.
kind=link sits between from_id and to_id. also_ids are extra existing ids that reading also touches.
kind=watch is a judged anomaly on an existing id.
Use existing entity, module, or place ids only. line is the thought, not a new record.
No crime-to-occupant links. Do not invent ends.
anomalies: judge anomaly_candidates. Keep only what is still unusual given later records.
Expired-and-replaced is not an anomaly. [] if nothing is sharp. Do not invent.
sources_read = one sentence. sources = up to four notes {origin, proved, when, edge_id}."""
