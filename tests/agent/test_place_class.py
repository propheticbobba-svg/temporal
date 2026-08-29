from datetime import UTC, datetime

from agent.place_class import classify_place
from agent.schema import SignalRead


def test_apt_address_votes_residential() -> None:
    result = classify_place("100 Main St Apt 4, Chicago, IL, 60601")

    assert result.place_class == "residential"
    assert result.assumed is False


def test_suitland_does_not_count_as_suite() -> None:
    result = classify_place("4600 SILVER HILL RD, SUITLAND, MD, 20746")

    assert result.place_class == "residential"
    assert result.assumed is True
    assert result.scores["commercial"] == 0.0


def test_warehouse_address_is_industrial() -> None:
    result = classify_place("800 Warehouse Way, Los Angeles, CA, 90021")

    assert result.place_class == "industrial"
    assert result.assumed is False


def test_business_license_makes_a_plain_address_commercial() -> None:
    result = classify_place(
        "123 MAIN ST, CHICAGO, IL, 60601",
        [_signal("biz_licenses", {"legal_name": "CAFE LUNA", "license_type": "Retail Food"})],
    )

    assert result.place_class == "commercial"
    assert result.assumed is False


def test_warehouse_license_beats_a_plain_street() -> None:
    result = classify_place(
        "200 Industrial St, Los Angeles, CA, 90021",
        [
            _signal(
                "biz_licenses",
                {
                    "legal_name": "HARBOR FREIGHT DEPOT",
                    "license_type": "Warehouse",
                },
            )
        ],
    )

    assert result.place_class == "industrial"


def test_repeated_license_votes_collapse_to_one_reason() -> None:
    licenses = [
        _signal("biz_licenses", {"legal_name": f"SHOP {index}", "license_type": "Retail"})
        for index in range(10)
    ]
    result = classify_place("123 MAIN ST, CHICAGO, IL, 60601", licenses)

    assert result.place_class == "commercial"
    assert result.reasons == ["10 business licenses are on file."]
    assert result.reasons.count("A business license is on file.") == 0


def test_dwelling_and_shop_together_are_mixed() -> None:
    result = classify_place(
        "12 Condo Lane Apt 2",
        [_signal("biz_licenses", {"legal_name": "CORNER SHOP", "license_type": "Retail"})],
    )

    assert result.place_class == "mixed"


def _signal(source: str, value: dict[str, str]) -> SignalRead:
    return SignalRead(
        source=source,
        signal_type="activity",
        observed_at=datetime(2026, 1, 15, tzinfo=UTC),
        value=value,
        summary="A record is on file.",
        is_anomaly=False,
        confidence=1.0,
    )
