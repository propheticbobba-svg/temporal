from __future__ import annotations

from collections.abc import Sequence

from .graph import _first_number, _first_text, normalize_entity_key
from .models import Brief, SignalRead

LICENSE_REVOKED = frozenset({"REV", "RVO", "REA"})
PERMIT_BREAKS = frozenset({"stop work", "violation", "revoked"})
CRIME_SLICES_FOR_FLAGS = (
    ("burglary", "burglary"),
    ("vehicle", "vehicle theft"),
    ("robbery", "robbery"),
    ("vandalism", "vandalism"),
)


def refine_anomalies(signals: Sequence[SignalRead]) -> list[str]:
    flags: list[str] = []
    flags.extend(_license_anomalies(signals))
    flags.extend(_permit_anomalies(signals))
    flags.extend(_crime_anomalies(signals))
    return flags[:3]


def candidate_anomalies(brief: Brief) -> list[str]:
    return refine_anomalies(_signals_from_brief(brief))
def _license_anomalies(signals: Sequence[SignalRead]) -> list[str]:
    groups: dict[str, list[SignalRead]] = {}
    for signal in signals:
        if signal.source != "biz_licenses":
            continue
        name = _first_text(signal.value, "doing_business_as", "legal_name") or "a business"
        kind = (_first_text(signal.value, "license_type") or "license").lower()
        groups.setdefault(f"{normalize_entity_key(name)}|{kind}", []).append(signal)

    flags: list[str] = []
    for group in groups.values():
        name = _first_text(group[0].value, "doing_business_as", "legal_name") or "a business"
        kind = (_first_text(group[0].value, "license_type") or "license").lower()
        statuses = {_license_status(signal) for signal in group}
        live = any(not signal.is_anomaly for signal in group)
        if statuses & LICENSE_REVOKED:
            flags.append(f"Revoked {kind} for {name}.")
        elif any(signal.is_anomaly for signal in group) and not live:
            flags.append(f"Expired {kind} for {name}, with no later active license.")
    return flags


def _permit_anomalies(signals: Sequence[SignalRead]) -> list[str]:
    flags: list[str] = []
    seen: set[str] = set()
    for signal in signals:
        if signal.source != "permits":
            continue
        status = (_first_text(signal.value, "status") or "").lower()
        if status not in PERMIT_BREAKS:
            continue
        permit = (_first_text(signal.value, "permit_type") or "permit").lower()
        line = f"{permit.capitalize()} permit marked {status}."
        if line in seen:
            continue
        seen.add(line)
        flags.append(line)
    return flags


def _crime_anomalies(signals: Sequence[SignalRead]) -> list[str]:
    for signal in signals:
        if signal.source != "crime_nearby":
            continue
        total = _first_number(signal.value, "total_incidents") or 0
        if total < 15:
            return []
        ranked = sorted(
            (
                (label, _first_number(signal.value, key) or 0)
                for key, label in CRIME_SLICES_FOR_FLAGS
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        label, count = ranked[0]
        if count >= 7 and count * 100 >= total * 45:
            return [f"{count} of {total} nearby incidents in 12 months were {label}."]
    return []


def _license_status(signal: SignalRead) -> str:
    return (_first_text(signal.value, "license_status") or "").upper()


def _signals_from_brief(brief: Brief) -> list[SignalRead]:
    signals: list[SignalRead] = []
    seen: set[tuple[str, str, str]] = set()
    for group in (
        brief.physical_condition.signals,
        brief.regulatory_standing.signals,
        brief.operational_activity.signals,
        brief.environmental_context.signals,
    ):
        for signal in group:
            key = (signal.source, signal.summary, signal.observed_at.isoformat())
            if key in seen:
                continue
            seen.add(key)
            signals.append(signal)
    return signals
