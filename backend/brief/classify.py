from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence

from pydantic import BaseModel, Field

from ..fetch import JsonObject
from ..place import PLACE_CLASS_LABELS, PlaceClass
from .models import SignalRead

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
