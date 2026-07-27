"""
Unit tests for Multiscale Kinematic Real EV Lookup (López de Prado Methodology)
"""
import pytest
from backend.modules.quality_swing.domain.rules.rc_multiscale_ev_lookup import (
    lookup_multiscale_kinematic_ev,
    classify_kinematic_trajectory,
    MultiscaleEVKinematicSignal,
)


def test_classify_kinematic_trajectory():
    assert classify_kinematic_trajectory(0.45) == "ABSORBING"
    assert classify_kinematic_trajectory(-0.45) == "EXHAUSTING"
    assert classify_kinematic_trajectory(0.10) == "STABLE"


def test_lookup_multiscale_kinematic_ev_returns_valid_signal():
    sig = lookup_multiscale_kinematic_ev(
        tide_slope="T+++",
        current_slope="C+++",
        wave_slope="W+++",
        sigma_current="~",
        sigma_wave="~",
        vwap_sigma_wave="~",
        delta_svw=0.40,
    )
    assert sig is not None
    assert isinstance(sig, MultiscaleEVKinematicSignal)
    assert sig.n_samples > 0
    assert 0.0 <= sig.p_bull <= 1.0
    assert 0.0 <= sig.p_piso_25 <= 1.0
    assert 0.0 <= sig.p_techo_25 <= 1.0
    assert sig.fallback_level in ("S1_full", "S3_triad", "S0_global")
    assert sig.kinematic_trajectory == "ABSORBING"


def test_lookup_multiscale_kinematic_ev_fallback():
    sig = lookup_multiscale_kinematic_ev(
        tide_slope="T-",
        current_slope="C-",
        wave_slope="W-",
        sigma_current="<<",
        sigma_wave="<<",
        vwap_sigma_wave="<<",
        delta_svw=0.0,
    )
    assert sig is not None
    assert sig.p_bull >= 0.0
