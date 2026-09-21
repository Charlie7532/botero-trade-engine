"""
Tests for TAF composite divergence regime synthesis.
Verifies _derive_composite_divergence_regime() correctly synthesizes
11 per-station divergence_regime values into a market verdict.
"""
import pytest
from backend.modules.entry_decision.domain.services.taf_service import (
    TafCone,
    compute_composite_taf,
    _derive_composite_divergence_regime,
)


def _make_cone(station: str, divergence_regime: str, ev_accel: float = 0.0) -> TafCone:
    """Helper to create a minimal TafCone with the fields under test."""
    return TafCone(
        station=station,
        state_key="2__2__2",
        p_bull_zz25=0.5, p_bull_zz50=0.5, p_bull_zz75=0.5,
        ev_net_zz25=0.0, ev_net_zz50=0.0, ev_net_zz75=0.0,
        e_ret_max_zz25=0.01, e_ret_max_zz50=0.02, e_ret_max_zz75=0.03,
        e_ret_min_zz25=-0.01, e_ret_min_zz50=-0.02, e_ret_min_zz75=-0.03,
        e_days_zz25=1.0, e_days_zz50=3.0, e_days_zz75=5.0,
        cone_asymmetry=1.0,
        cone_slope=1.0,
        convergence_score=0.0,
        ev_acceleration=ev_accel,
        divergence_regime=divergence_regime,
    )


class TestDeriveCompositeDivergenceRegime:
    """Tests for _derive_composite_divergence_regime()."""

    def test_empty_cones_returns_equilibrium(self):
        assert _derive_composite_divergence_regime([]) == "EQUILIBRIUM"

    def test_majority_bull_returns_convergent_expansion(self):
        """When >= 40% of stations are FULL_CONVERGENT_BULL."""
        cones = [
            _make_cone("vix", "FULL_CONVERGENT_BULL"),
            _make_cone("vvix", "FULL_CONVERGENT_BULL"),
            _make_cone("pcr", "FULL_CONVERGENT_BULL"),
            _make_cone("fg", "FULL_CONVERGENT_BULL"),
            _make_cone("bsi", "FULL_CONVERGENT_BULL"),
            _make_cone("credit", "MIXED_HORIZON_TRANSITION"),
            _make_cone("yield_curve", "STRUCTURAL_BULL_PULLBACK"),
            _make_cone("rotation", "NEUTRAL"),
            _make_cone("skew", "NEUTRAL"),
            _make_cone("sv5_turbulence", "NEUTRAL"),
        ]
        assert _derive_composite_divergence_regime(cones) == "CONVERGENT_MOMENTUM_EXPANSION"

    def test_majority_bear_returns_contraction_exhaustion(self):
        """When >= 40% of stations are FULL_CONVERGENT_BEAR."""
        cones = [
            _make_cone("vix", "FULL_CONVERGENT_BEAR"),
            _make_cone("vvix", "FULL_CONVERGENT_BEAR"),
            _make_cone("pcr", "FULL_CONVERGENT_BEAR"),
            _make_cone("fg", "FULL_CONVERGENT_BEAR"),
            _make_cone("bsi", "FULL_CONVERGENT_BEAR"),
            _make_cone("credit", "MIXED_HORIZON_TRANSITION"),
            _make_cone("yield_curve", "NEUTRAL"),
            _make_cone("rotation", "NEUTRAL"),
            _make_cone("skew", "NEUTRAL"),
            _make_cone("sv5_turbulence", "NEUTRAL"),
        ]
        assert _derive_composite_divergence_regime(cones) == "CONVERGENT_CONTRACTION_EXHAUSTION"

    def test_bull_plus_pullback_returns_structural_dip(self):
        """When bull + pullback >= 40% and pullback > 0."""
        cones = [
            _make_cone("vix", "FULL_CONVERGENT_BULL"),
            _make_cone("vvix", "STRUCTURAL_BULL_PULLBACK"),
            _make_cone("pcr", "STRUCTURAL_BULL_PULLBACK"),
            _make_cone("fg", "FULL_CONVERGENT_BULL"),
            _make_cone("bsi", "MIXED_HORIZON_TRANSITION"),
            _make_cone("credit", "MIXED_HORIZON_TRANSITION"),
            _make_cone("yield_curve", "NEUTRAL"),
            _make_cone("rotation", "NEUTRAL"),
            _make_cone("skew", "NEUTRAL"),
            _make_cone("sv5_turbulence", "NEUTRAL"),
        ]
        assert _derive_composite_divergence_regime(cones) == "STRUCTURAL_BULL_TACTICAL_DIP"

    def test_bear_plus_rebound_returns_tactical_bounce(self):
        """When bear + rebound >= 40% and rebound > 0."""
        cones = [
            _make_cone("vix", "FULL_CONVERGENT_BEAR"),
            _make_cone("vvix", "TACTICAL_REBOUND_IN_BEAR"),
            _make_cone("pcr", "TACTICAL_REBOUND_IN_BEAR"),
            _make_cone("fg", "FULL_CONVERGENT_BEAR"),
            _make_cone("bsi", "MIXED_HORIZON_TRANSITION"),
            _make_cone("credit", "MIXED_HORIZON_TRANSITION"),
            _make_cone("yield_curve", "NEUTRAL"),
            _make_cone("rotation", "NEUTRAL"),
            _make_cone("skew", "NEUTRAL"),
            _make_cone("sv5_turbulence", "NEUTRAL"),
        ]
        assert _derive_composite_divergence_regime(cones) == "STRUCTURAL_BEAR_TACTICAL_BOUNCE"

    def test_no_majority_small_ev_returns_equilibrium(self):
        """When no regime dominates and |ev_accel| < 0.005."""
        cones = [
            _make_cone("vix", "MIXED_HORIZON_TRANSITION", ev_accel=0.001),
            _make_cone("vvix", "MIXED_HORIZON_TRANSITION", ev_accel=-0.001),
            _make_cone("pcr", "NEUTRAL", ev_accel=0.002),
            _make_cone("fg", "NEUTRAL", ev_accel=-0.002),
            _make_cone("bsi", "MIXED_HORIZON_TRANSITION", ev_accel=0.0),
        ]
        assert _derive_composite_divergence_regime(cones) == "EQUILIBRIUM"

    def test_no_majority_positive_ev_returns_bull_dip(self):
        """When no regime dominates but ev_accel > 0.005."""
        cones = [
            _make_cone("vix", "MIXED_HORIZON_TRANSITION", ev_accel=0.01),
            _make_cone("vvix", "NEUTRAL", ev_accel=0.02),
            _make_cone("pcr", "NEUTRAL", ev_accel=0.015),
        ]
        assert _derive_composite_divergence_regime(cones) == "STRUCTURAL_BULL_TACTICAL_DIP"

    def test_no_majority_negative_ev_returns_bear_bounce(self):
        """When no regime dominates but ev_accel < -0.005."""
        cones = [
            _make_cone("vix", "MIXED_HORIZON_TRANSITION", ev_accel=-0.01),
            _make_cone("vvix", "NEUTRAL", ev_accel=-0.02),
            _make_cone("pcr", "NEUTRAL", ev_accel=-0.015),
        ]
        assert _derive_composite_divergence_regime(cones) == "STRUCTURAL_BEAR_TACTICAL_BOUNCE"


class TestComputeCompositeTafIncludesRegime:
    """Verify compute_composite_taf() includes composite_divergence_regime in output."""

    def test_empty_cones_has_equilibrium(self):
        result = compute_composite_taf([])
        assert result["composite_divergence_regime"] == "EQUILIBRIUM"

    def test_bull_cones_has_expansion(self):
        cones = [_make_cone(f"s{i}", "FULL_CONVERGENT_BULL") for i in range(5)]
        result = compute_composite_taf(cones)
        assert result["composite_divergence_regime"] == "CONVERGENT_MOMENTUM_EXPANSION"
        assert "composite_ev_acceleration" in result
        assert "station_cones" in result

    def test_mixed_cones_has_equilibrium(self):
        cones = [
            _make_cone("a", "MIXED_HORIZON_TRANSITION", ev_accel=0.001),
            _make_cone("b", "NEUTRAL", ev_accel=-0.001),
        ]
        result = compute_composite_taf(cones)
        assert result["composite_divergence_regime"] == "EQUILIBRIUM"
