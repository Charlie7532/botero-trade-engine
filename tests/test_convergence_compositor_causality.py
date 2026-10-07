"""
Tests for ConvergenceCompositor Causality & as_of_date Enforcement
===================================================================
Verifies:
1. as_of_date parsing normalizes string dates to end-of-day UTC.
2. Injected ZigzagLegPort strictly receives causal as_of_dt.
3. Legs confirmed in the future (e.g. 2021-09-20) are NOT visible when evaluating as_of_date='2021-09-17'.
4. Channel 4 cascade conviction evaluates causally without look-ahead bias.
"""
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

from backend.modules.entry_decision.domain.services.convergence_compositor import (
    ConvergenceCompositor,
    _parse_as_of_dt,
)
from backend.modules.shared.domain.entities.zigzag_leg import ZigzagLeg
from backend.modules.shared.domain.ports.zigzag_leg_port import ZigzagLegPort


class MockZigzagLegRepository(ZigzagLegPort):
    def __init__(self, legs: List[ZigzagLeg]):
        self.legs = legs
        self.last_query_as_of = None

    def get_confirmed_legs(
        self,
        ticker: str,
        scale: str = "zz25",
        as_of_date: Optional[datetime] = None,
    ) -> List[ZigzagLeg]:
        self.last_query_as_of = as_of_date
        if as_of_date is None:
            return list(self.legs)
        return [l for l in self.legs if l.confirmed_at_timestamp <= as_of_date]

    def get_latest_confirmed_leg(
        self,
        ticker: str,
        scale: str = "zz25",
        as_of_date: Optional[datetime] = None,
    ) -> Optional[ZigzagLeg]:
        legs = self.get_confirmed_legs(ticker, scale, as_of_date)
        return legs[-1] if legs else None


def test_parse_as_of_dt_formats():
    """Validates date normalization to end-of-day UTC."""
    # YYYY-MM-DD
    dt = _parse_as_of_dt("2021-09-17")
    assert dt is not None
    assert dt.year == 2021 and dt.month == 9 and dt.day == 17
    assert dt.hour == 23 and dt.minute == 59 and dt.second == 59 and dt.microsecond == 999999
    assert dt.tzinfo == timezone.utc

    # Datetime object naive
    dt_naive = datetime(2021, 9, 17, 12, 0, 0)
    dt_res = _parse_as_of_dt(dt_naive)
    assert dt_res.tzinfo == timezone.utc

    # None
    assert _parse_as_of_dt(None) is None


def test_compositor_causality_prevents_future_leg_leak():
    """A leg confirmed on 2021-09-20 must not be visible on 2021-09-17."""
    leg_past = ZigzagLeg(
        ticker="SPY",
        scale="zz25",
        leg_id="SPY_zz25_1",
        start_timestamp=datetime(2021, 9, 1, tzinfo=timezone.utc),
        start_type="MIN",
        start_price=440.0,
        end_timestamp=datetime(2021, 9, 10, tzinfo=timezone.utc),
        end_type="MAX",
        end_price=450.0,
        confirmed_at_timestamp=datetime(2021, 9, 15, 16, 0, 0, tzinfo=timezone.utc),
        prev_leg_return=0.035,
        prev_leg_duration=9,
    )
    leg_future = ZigzagLeg(
        ticker="SPY",
        scale="zz25",
        leg_id="SPY_zz25_2",
        start_timestamp=datetime(2021, 9, 10, tzinfo=timezone.utc),
        start_type="MAX",
        start_price=450.0,
        end_timestamp=datetime(2021, 9, 16, tzinfo=timezone.utc),
        end_type="MIN",
        end_price=442.0,
        confirmed_at_timestamp=datetime(2021, 9, 20, 16, 0, 0, tzinfo=timezone.utc),
        prev_leg_return=-0.042,
        prev_leg_duration=6,
    )

    mock_repo = MockZigzagLegRepository([leg_past, leg_future])
    compositor = ConvergenceCompositor(leg_repo=mock_repo)

    # Mock station fetching to isolate Channel 4 testing
    dummy_metar = MagicMock()
    dummy_metar.to_dict.return_value = {
        "n_samples": 100,
        "state_key": "MKT_VIX_D1_0__D2_2__D3_2",
        "d1_bin": 0,
        "vote": 1,
        "timing": {},
    }

    with patch.object(compositor, "_fetch_station", return_value=("vix", dummy_metar.to_dict(), None)):
        # Run causality check at 2021-09-17
        report = compositor.compute(as_of_date="2021-09-17")

        # Must have queried with 2021-09-17 23:59:59.999999 UTC
        assert mock_repo.last_query_as_of == datetime(2021, 9, 17, 23, 59, 59, 999999, tzinfo=timezone.utc)

        # Verified causal state: only leg_past was visible (prev_leg_return=0.035, pivot_type="MIN")
        # If leg_future had leaked, prev_leg_return would be -0.042 and pivot_type would be "MAX"
        assert report.pivot_type == "MIN"
        assert report.domino_magnitude == pytest.approx(0.035)

        # Re-run after confirmation on 2021-09-21
        report_future = compositor.compute(as_of_date="2021-09-21")
        assert report_future.pivot_type == "MAX"
        assert report_future.domino_magnitude == pytest.approx(0.042)


def test_real_repo_causal_query():
    """Verify ZigzagLegRepository against Neon Vault respects as_of_date causal bounds."""
    try:
        from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
        from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
        store = TimescaleDataStore()
        repo = ZigzagLegRepository(store)
    except Exception as e:
        pytest.skip(f"Neon Vault unavailable: {e}")

    cutoff = datetime(2021, 9, 17, 23, 59, 59, 999999, tzinfo=timezone.utc)
    legs = repo.get_confirmed_legs("SPY", "zz25", as_of_date=cutoff)
    if not legs:
        pytest.skip("No SPY zz25 legs in database")

    for leg in legs:
        assert leg.confirmed_at_timestamp <= cutoff, f"Leg {leg.leg_id} leaked: confirmed at {leg.confirmed_at_timestamp} > {cutoff}"


