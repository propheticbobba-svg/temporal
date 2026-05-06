from jobs.scheduler import RefreshInterval, get_registered_ingesters


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
