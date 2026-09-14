"""Tests for station_profiles.py — classify_tier() and signal_router().

Covers:
1. classify_tier: All 4 tiers with boundary conditions
2. signal_router: Orthogonal dimensions (weight vs alert), no cliff effect
3. StationProfile: All 11 stations have valid profiles
4. Backward compatibility: signal_router produces same composite_weight as old reliability_factor
"""
import pytest

from backend.modules.entry_decision.domain.rules.station_profiles import (
    classify_tier,
    signal_router,
    get_station_profile,
    STATION_PROFILES,
)


# ── 1. classify_tier ─────────────────────────────────────────────────────

class TestClassifyTier:
    def test_event_tier(self):
        """N < 10 is always EVENT regardless of D1."""
        assert classify_tier(3, 5) == "EVENT"
        assert classify_tier(1, 0) == "EVENT"
        assert classify_tier(9, 2) == "EVENT"
        assert classify_tier(0, 3) == "EVENT"

    def test_transitional_tier(self):
        """10 <= N < 30 is always TRANSITIONAL regardless of D1."""
        assert classify_tier(10, 5) == "TRANSITIONAL"
        assert classify_tier(12, 4) == "TRANSITIONAL"
        assert classify_tier(29, 2) == "TRANSITIONAL"
        assert classify_tier(15, 0) == "TRANSITIONAL"

    def test_confirmed_tier(self):
        """N >= 30 with extreme D1 (0, 1, 4, 5) is CONFIRMED."""
        assert classify_tier(50, 5) == "CONFIRMED"
        assert classify_tier(30, 4) == "CONFIRMED"
        assert classify_tier(100, 1) == "CONFIRMED"
        assert classify_tier(374, 0) == "CONFIRMED"

    def test_baseline_tier(self):
        """N >= 30 with central D1 (2, 3) is BASELINE."""
        assert classify_tier(50, 2) == "BASELINE"
        assert classify_tier(30, 3) == "BASELINE"
        assert classify_tier(1960, 2) == "BASELINE"

    def test_boundary_n10(self):
        """N=9 is EVENT, N=10 is TRANSITIONAL — the boundary is exact."""
        assert classify_tier(9, 5) == "EVENT"
        assert classify_tier(10, 5) == "TRANSITIONAL"

    def test_boundary_n30(self):
        """N=29 is TRANSITIONAL, N=30 depends on D1."""
        assert classify_tier(29, 5) == "TRANSITIONAL"
        assert classify_tier(30, 5) == "CONFIRMED"
        assert classify_tier(30, 2) == "BASELINE"


# ── 2. signal_router ─────────────────────────────────────────────────────

class TestSignalRouter:
    def test_backward_compat_confirmed_baseline(self):
        """CONFIRMED/BASELINE must produce composite_weight identical to old reliability_factor."""
        # Old: reliability_factor(50) == 1.0
        r = signal_router(50, 2, "vix")
        assert r["composite_weight"] == 1.0
        assert r["tier"] == "BASELINE"

        r = signal_router(100, 5, "vix")
        assert r["composite_weight"] == 1.0
        assert r["tier"] == "CONFIRMED"

    def test_backward_compat_transitional(self):
        """TRANSITIONAL must produce composite_weight = 0.5 (same as old reliability_factor)."""
        r = signal_router(15, 4, "vix")
        assert r["composite_weight"] == 0.5
        assert r["tier"] == "TRANSITIONAL"

    def test_backward_compat_event(self):
        """EVENT must produce composite_weight = 0.0 (same as old reliability_factor)."""
        r = signal_router(3, 5, "vix")
        assert r["composite_weight"] == 0.0
        assert r["tier"] == "EVENT"

    def test_no_cliff_effect(self):
        """N=9→N=10 transition: both have CRITICAL alert when D1=5.
        The cliff is ONLY in composite_weight (0.0 → 0.5), NOT in alert_priority."""
        r9 = signal_router(9, 5, "vix", sigma_depth_d1=4.5)
        r10 = signal_router(10, 5, "vix", sigma_depth_d1=4.5)

        # Both CRITICAL (D1=5 is extreme)
        assert r9["alert_priority"] == "CRITICAL"
        assert r10["alert_priority"] == "CRITICAL"

        # Weight transitions smoothly
        assert r9["composite_weight"] == 0.0
        assert r10["composite_weight"] == 0.5

        # Both are alerted (EVENT via alert_only, TRANSITIONAL via alert_and_composite)
        assert r9["alert_channel"] == "alert_only"
        assert r10["alert_channel"] == "alert_and_composite"

    def test_event_extreme_not_silenced(self):
        """EVENT with extreme D1 goes to alert_only — NOT silenced like before."""
        r = signal_router(3, 5, "vix", sigma_depth_d1=6.0)
        assert r["composite_weight"] == 0.0     # Can't do stats with 3 samples
        assert r["alert_priority"] == "CRITICAL"  # BUT it's a crisis alert
        assert r["alert_channel"] == "alert_only"  # Routed to alerts

    def test_event_central_no_alert(self):
        """EVENT with central D1 (bin 2 or 3) — no alert, just low composite weight."""
        r = signal_router(5, 2, "vix")
        assert r["composite_weight"] == 0.0
        assert r["alert_priority"] == "NONE"
        assert r["alert_channel"] == "composite_only"

    def test_overflow_triggers_critical(self):
        """Sigma depth >= 3.0 triggers CRITICAL regardless of D1 bin."""
        r = signal_router(50, 2, "vix", sigma_depth_d1=3.5)
        assert r["alert_priority"] == "CRITICAL"
        assert r["alert_channel"] == "alert_and_composite"

    def test_baseline_no_alert(self):
        """BASELINE (N>=30, D1 central) produces no alerts."""
        r = signal_router(1960, 2, "vix")
        assert r["alert_priority"] == "NONE"
        assert r["alert_channel"] == "composite_only"
        assert r["composite_weight"] == 1.0

    def test_confirmed_moderate_alert(self):
        """CONFIRMED with D1=4 (alert zone, not extreme) produces MODERATE."""
        r = signal_router(50, 4, "vix")
        assert r["alert_priority"] == "MODERATE"

    def test_transitional_alert_bins_high(self):
        """TRANSITIONAL with D1=4 (alert zone) produces HIGH."""
        r = signal_router(15, 4, "vix")
        assert r["alert_priority"] == "HIGH"

    def test_kinematic_anomaly_d2_extreme(self):
        """EVENT with central D1 but extreme D2 triggers MODERATE (kinematic anomaly)."""
        r = signal_router(5, 2, "pcr", d2_bin=0)
        assert r["alert_priority"] == "MODERATE"
        assert r["alert_channel"] == "alert_only"

    def test_kinematic_anomaly_d3_extreme(self):
        """EVENT with central D1 but extreme D3 triggers MODERATE."""
        r = signal_router(7, 3, "skew", d2_bin=2, d3_bin=4)
        assert r["alert_priority"] == "MODERATE"
        assert r["alert_channel"] == "alert_only"

    def test_kinematic_anomaly_confirmed_gets_composite(self):
        """CONFIRMED (N>=30) with kinematic anomaly gets alert_and_composite."""
        r = signal_router(50, 2, "fg", d2_bin=4, d3_bin=2)
        assert r["alert_priority"] == "MODERATE"
        assert r["composite_weight"] == 1.0
        assert r["alert_channel"] == "alert_and_composite"

    def test_kinematic_no_anomaly_central_d2d3(self):
        """Central D1 + central D2/D3 = no anomaly, no alert."""
        r = signal_router(5, 2, "vix", d2_bin=2, d3_bin=2)
        assert r["alert_priority"] == "NONE"
        assert r["alert_channel"] == "composite_only"

    def test_kinematic_not_triggered_on_extreme_d1(self):
        """Extreme D1 already produces CRITICAL — kinematic is irrelevant."""
        r = signal_router(5, 5, "vix", d2_bin=0, d3_bin=4)
        assert r["alert_priority"] == "CRITICAL"  # D1 dominates

    def test_backward_compat_no_d2d3(self):
        """Without D2/D3 args (d2=-1, d3=-1), behavior identical to before."""
        r = signal_router(5, 2, "vix")
        assert r["alert_priority"] == "NONE"  # -1 not in (0, 4)
        assert r["alert_channel"] == "composite_only"


# ── 3. Station Profiles ─────────────────────────────────────────────────

class TestStationProfiles:
    def test_all_11_stations_exist(self):
        """All 11 METAR stations must have profiles."""
        expected = {"vix", "vvix", "bsi", "fg", "pcr", "skew", "credit",
                    "yield_curve", "rotation", "sv5_turbulence", "dxy"}
        assert set(STATION_PROFILES.keys()) == expected

    def test_polarity_consistency(self):
        """Polarity must match STATIONS_HIGH_BEARISH/LOW_BEARISH in compositor."""
        high_bearish = {"vix", "vvix", "pcr", "sv5_turbulence", "skew", "dxy"}
        for code, profile in STATION_PROFILES.items():
            if code in high_bearish:
                assert profile.polarity == "NORMAL", f"{code} should be NORMAL (high=bearish)"
            elif code == "yield_curve":
                assert profile.polarity == "TRANSITIONAL_MACRO"
            else:
                assert profile.polarity == "INVERTED", f"{code} should be INVERTED (low=bearish)"

    def test_dsr_grades(self):
        """DSR grades must match intelligence file data."""
        grade_a = {"vix", "bsi", "fg", "credit", "yield_curve"}
        for code, profile in STATION_PROFILES.items():
            if code in grade_a:
                assert profile.dsr_grade == "A", f"{code} should be Grade A"
            else:
                assert profile.dsr_grade == "B", f"{code} should be Grade B"

    def test_get_station_profile(self):
        """get_station_profile handles case insensitivity and missing stations."""
        assert get_station_profile("VIX") is not None
        assert get_station_profile("vix") is not None
        assert get_station_profile("nonexistent") is None
