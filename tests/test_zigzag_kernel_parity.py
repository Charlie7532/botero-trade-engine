"""
ZigZag Canonical Kernel Parity Test
===================================
Validates that the unified domain kernel in `zigzag_core.py` strictly satisfies F2.2:
  - Mode 'points' (close confirmation) reproduces SPY engine.zigzag_points (868/300/136) at 100.0%.
  - Mode 'legs' (extreme touch confirmation) reproduces canonical market.zigzag_legs (1584/454/184).
  - Causal timestamp integrity: start_timestamp <= end_timestamp <= confirmed_at_timestamp.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import timezone

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.rules.zigzag_core import (
    compute_zigzag_points,
    compute_zigzag_legs,
    compute_zigzag,
)


@pytest.fixture(scope="module")
def spy_bars():
    store = TimescaleDataStore()
    df = store.load_bars("SPY", "1d")
    assert df is not None and not df.empty, "Failed to load SPY bars from Neon Vault"
    return df.sort_index()


def test_zigzag_points_parity_spy(spy_bars):
    """Mode 'points' must reproduce exactly 868 (zz25), 300 (zz50), 136 (zz75) pivots on SPY."""
    high = spy_bars["high"].values.astype(float)
    low = spy_bars["low"].values.astype(float)
    close = spy_bars["close"].values.astype(float)

    pts_25 = compute_zigzag_points(high, low, close, min_pct=0.025)
    pts_50 = compute_zigzag_points(high, low, close, min_pct=0.050)
    pts_75 = compute_zigzag_points(high, low, close, min_pct=0.075)

    assert len(pts_25) == 868, f"Expected 868 zz25 points, got {len(pts_25)}"
    assert len(pts_50) == 300, f"Expected 300 zz50 points, got {len(pts_50)}"
    assert len(pts_75) == 136, f"Expected 136 zz75 points, got {len(pts_75)}"


def test_zigzag_legs_canonical_counts_and_causality(spy_bars):
    """Mode 'legs' must produce exactly 1584 (zz25), 454 (zz50), 184 (zz75) legs and preserve causality."""
    dates = pd.to_datetime(spy_bars.index, utc=True)
    opens = spy_bars["open"].values.astype(float)
    highs = spy_bars["high"].values.astype(float)
    lows = spy_bars["low"].values.astype(float)
    closes = spy_bars["close"].values.astype(float)

    expected_counts = {"zz25": 1584, "zz50": 454, "zz75": 184}
    thresholds = {"zz25": 0.025, "zz50": 0.050, "zz75": 0.075}

    for scale, thres in thresholds.items():
        legs = compute_zigzag_legs(
            dates=dates,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            scale_name=scale,
            min_pct=thres,
            ticker="SPY",
        )
        assert len(legs) == expected_counts[scale], f"Scale {scale}: expected {expected_counts[scale]} legs, got {len(legs)}"

        # Strict causality check
        for leg in legs:
            start_ts = pd.to_datetime(leg["start_timestamp"], utc=True)
            end_ts = pd.to_datetime(leg["end_timestamp"], utc=True)
            conf_ts = pd.to_datetime(leg["confirmed_at_timestamp"], utc=True)

            assert start_ts <= end_ts, f"Temporal inversion: start {start_ts} > end {end_ts}"
            assert end_ts <= conf_ts, f"Look-ahead detected: end {end_ts} > confirmed_at {conf_ts}"


def test_zigzag_dispatcher_modes(spy_bars):
    """Unified dispatcher compute_zigzag must correctly handle 'points' and 'legs' modes."""
    pts = compute_zigzag(spy_bars, deviation_pct=0.05, mode="points")
    assert isinstance(pts, list)
    assert len(pts) == 300
    assert len(pts[0]) == 3  # (idx, type, price)

    legs = compute_zigzag(spy_bars, deviation_pct=0.05, mode="legs", ticker="SPY")
    assert isinstance(legs, list)
    assert len(legs) == 454
    assert isinstance(legs[0], dict)
    assert "confirmed_at_timestamp" in legs[0]
