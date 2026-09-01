from datetime import UTC, datetime

from backend.brief import SignalRead, refine_anomalies


def test_expired_license_is_quiet_when_a_later_active_one_exists() -> None:
    flags = refine_anomalies(
        [
            _license("CAFE LUNA", "Retail Food", "EXP", True),
            _license("CAFE LUNA", "Retail Food", "AAI", False),
        ]
    )
    assert flags == []


def test_expired_license_flags_when_nothing_replaced_it() -> None:
    flags = refine_anomalies([_license("CAFE LUNA", "Retail Food", "EXP", True)])
    assert flags == ["Expired retail food for CAFE LUNA, with no later active license."]


def test_revoked_license_is_kept() -> None:
    flags = refine_anomalies([_license("CAFE LUNA", "Retail Food", "REV", True)])
    assert flags == ["Revoked retail food for CAFE LUNA."]


def test_stop_work_permit_is_kept_and_high_value_is_not() -> None:
    flags = refine_anomalies(
        [
            SignalRead(
                source="permits",
                signal_type="activity",
                observed_at=datetime(2026, 1, 1, tzinfo=UTC),
                value={"permit_type": "Building", "status": "Issued", "valuation": 900000},
                summary="A building permit was issued.",
                is_anomaly=False,
                confidence=1.0,
            ),
            SignalRead(
                source="permits",
                signal_type="anomaly",
                observed_at=datetime(2026, 2, 1, tzinfo=UTC),
                value={"permit_type": "Building", "status": "Stop Work"},
                summary="A building permit was issued with status stop work.",
                is_anomaly=True,
                confidence=1.0,
            ),
        ]
    )
    assert flags == ["Building permit marked stop work."]


def test_crime_flags_only_when_one_type_dominates_a_large_set() -> None:
    quiet = refine_anomalies([_crime(total=8, burglary=5)])
    sharp = refine_anomalies([_crime(total=20, burglary=12)])
    assert quiet == []
    assert sharp == ["12 of 20 nearby incidents in 12 months were burglary."]


def _license(name: str, license_type: str, status: str, anomaly: bool) -> SignalRead:
    return SignalRead(
        source="biz_licenses",
        signal_type="anomaly" if anomaly else "activity",
        observed_at=datetime(2026, 1, 15, tzinfo=UTC),
        value={
            "legal_name": name,
            "license_type": license_type,
            "license_status": status,
        },
        summary=f"{name} {status}",
        is_anomaly=anomaly,
        confidence=1.0,
    )


def _crime(*, total: int, burglary: int) -> SignalRead:
    return SignalRead(
        source="crime_nearby",
        signal_type="trend",
        observed_at=datetime(2026, 8, 31, tzinfo=UTC),
        value={
            "total_incidents": total,
            "burglary": burglary,
            "vehicle": max(0, total - burglary),
            "robbery": 0,
            "vandalism": 0,
        },
        summary="Crime nearby.",
        is_anomaly=False,
        confidence=1.0,
    )
