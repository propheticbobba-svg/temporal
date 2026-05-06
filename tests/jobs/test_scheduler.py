from jobs.scheduler import RefreshInterval, get_registered_ingesters


def test_geocode_runs_first_and_never_refreshes() -> None:
    first_registration = get_registered_ingesters()[0]

    assert first_registration.source == "geocode"
    assert first_registration.refresh_interval == RefreshInterval.NEVER
