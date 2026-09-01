from datetime import UTC, datetime, timedelta

from backend.fetch import LocationInput
from backend.place import RefreshInterval, get_registered_ingesters, is_refresh_due, source_covers


def test_geocode_runs_first_and_never_refreshes() -> None:
    first_registration = get_registered_ingesters()[0]

    assert first_registration.source == "geocode"
    assert first_registration.refresh_interval == RefreshInterval.NEVER


def test_business_licenses_run_after_permits_and_refresh_weekly() -> None:
    registrations = get_registered_ingesters()

    assert [registration.source for registration in registrations[:3]] == [
        "geocode",
        "permits",
        "biz_licenses",
    ]
    assert registrations[2].refresh_interval == RefreshInterval.WEEKLY


def test_crime_nearby_registers_after_licenses_and_refreshes_weekly() -> None:
    registrations = {
        registration.source: registration for registration in get_registered_ingesters()
    }

    assert registrations["crime_nearby"].refresh_interval == RefreshInterval.WEEKLY
    assert [registration.source for registration in get_registered_ingesters()[:3]] == [
        "geocode",
        "permits",
        "biz_licenses",
    ]


def test_source_covers_crime_only_inside_san_francisco() -> None:
    sf = LocationInput(
        address="501 OFARRELL ST, SAN FRANCISCO, CA, 94102",
        latitude=37.78573,
        longitude=-122.41303,
    )
    chicago = LocationInput(
        address="123 MAIN ST, CHICAGO, IL, 60601",
        latitude=41.8781,
        longitude=-87.6298,
    )
    assert source_covers("crime_nearby", sf) is True
    assert source_covers("crime_nearby", chicago) is False
    assert source_covers("geocode", sf) is False


def test_refresh_is_due_when_never_ingested() -> None:
    assert is_refresh_due(RefreshInterval.WEEKLY, None) is True


def test_never_interval_is_not_due_after_first_refresh() -> None:
    refreshed_at = datetime(2026, 1, 1, tzinfo=UTC)

    assert is_refresh_due(RefreshInterval.NEVER, refreshed_at) is False


def test_weekly_interval_is_due_after_seven_days() -> None:
    now = datetime(2026, 1, 15, tzinfo=UTC)
    fresh = now - timedelta(days=6)
    stale = now - timedelta(days=7)

    assert is_refresh_due(RefreshInterval.WEEKLY, fresh, now=now) is False
    assert is_refresh_due(RefreshInterval.WEEKLY, stale, now=now) is True
