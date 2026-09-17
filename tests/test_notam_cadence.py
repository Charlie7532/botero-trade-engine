"""
Unit tests for NOTAM Publication Cadence & Schedule Tolerance
"""
import pytest
import pandas as pd
from datetime import date
from backend.modules.entry_decision.domain.services.notam_incident_service import (
    compute_station_staleness,
    MONITORED_NOTAM_STATIONS,
)


def test_eod_station_intraday_tolerance():
    """EOD stations (CBOE_PCR, VVIX, SKEW) should not be stale on T if T-1 is present before 18:00 ET."""
    today = date.today()
    # Previous business day
    import pandas as pd
    prev_bdays = pd.bdate_range(end=today, periods=2)
    yesterday = prev_bdays[0].date() if len(prev_bdays) >= 2 else today

    # For an EOD station, having yesterday's bar on day T is valid
    lag, is_stale = compute_station_staleness(
        station="CBOE_PCR",
        latest_date=yesterday,
        ref_date=today,
        cadence="EOD",
        as_of_date=None,
    )
    assert not is_stale
    assert lag == 0


def test_t_minus_1_fed_tolerance():
    """FRED T-1 stations (DFII10, DGS10) should not be stale on T if T-2 is present."""
    today = date.today()
    import pandas as pd
    prev_bdays = pd.bdate_range(end=today, periods=3)
    two_bdays_ago = prev_bdays[0].date() if len(prev_bdays) >= 3 else today

    lag, is_stale = compute_station_staleness(
        station="DGS10",
        latest_date=two_bdays_ago,
        ref_date=today,
        cadence="T_MINUS_1_FED",
        as_of_date=None,
    )
    assert not is_stale
    assert lag == 0


def test_true_outdated_detection():
    """If data is older than expected window, it must be detected as stale."""
    today = date(2026, 9, 16)
    old_date = date(2026, 9, 1) # 2 weeks ago

    lag, is_stale = compute_station_staleness(
        station="CBOE_PCR",
        latest_date=old_date,
        ref_date=today,
        cadence="EOD",
        as_of_date=None,
    )
    assert is_stale
    assert lag > 1


def test_all_monitored_stations_cadence_safety():
    """All monitored stations must have defined behavior without exception."""
    today = date(2026, 9, 16)
    for st in MONITORED_NOTAM_STATIONS:
        lag, is_stale = compute_station_staleness(
            station=st,
            latest_date=today,
            ref_date=today,
            cadence="INTRADAY",
            as_of_date=None,
        )
        assert lag == 0
        assert not is_stale
