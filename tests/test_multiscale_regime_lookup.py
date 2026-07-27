"""
Unit tests for Multiscale Kinematic Regime Event Lookup (López de Prado Triple Barrier Method)
=============================================================================================
Validates non-tautological kinematic cluster mapping, probabilistic soft mixture,
Shannon Entropy, Sector Sync Index (I_sync), and Falling Knife Veto.
"""
import pytest
from backend.modules.quality_swing.domain.rules.rc_multiscale_ev_lookup import (
    lookup_multiscale_regime_event,
    MultiscaleRegimeEvent,
)


def test_kin_accumulation_absorbing_event():
    event = lookup_multiscale_regime_event(
        tide_slope=-0.20,
        current_slope=-0.10,
        wave_slope=0.05,
        vwap_sigma_wave=-1.20,
        delta_svw=0.45,
        delta2_svw=0.15,
        state_duration=2,
    )
    assert isinstance(event, MultiscaleRegimeEvent)
    assert event.regime_code == "KIN_ACCUMULATION_ABSORBING"
    assert "KIN_ACCUMULATION_ABSORBING" in event.regime_probabilities_vector
    assert event.shannon_entropy > 0.0


def test_kin_steady_megatrend_event():
    event = lookup_multiscale_regime_event(
        tide_slope=0.25,
        current_slope=0.35,
        wave_slope=0.40,
        vwap_sigma_wave=0.50,
        delta_svw=0.0,
        delta2_svw=0.0,
        state_duration=12,
    )
    assert isinstance(event, MultiscaleRegimeEvent)
    assert event.regime_code == "KIN_STEADY_MEGATREND"


def test_falling_knife_veto():
    # Stock collapses individually (z=-2.5) while sector is stable (z=0.2) -> I_sync = 12.5 > 2.5
    event = lookup_multiscale_regime_event(
        tide_slope=-0.10,
        current_slope=-0.30,
        wave_slope=-0.40,
        vwap_sigma_wave=-1.50,
        delta_svw=-0.40,
        stock_zscore=-2.5,
        sector_zscore=0.2,
    )
    assert isinstance(event, MultiscaleRegimeEvent)
    assert event.is_falling_knife_veto is True
    assert event.p_bull == 0.0
    assert event.ev_net < 0.0
    assert event.sector_sync_index > 2.5


def test_lookup_pure_quantitative_vector():
    from backend.shared.domain.entities.probability_snapshot import ProbabilitySnapshot
    from backend.modules.quality_swing.domain.rules.rc_multiscale_ev_lookup import (
        lookup_pure_quantitative_vector,
    )

    vec = lookup_pure_quantitative_vector(
        tide_slope=0.15,
        current_slope=-0.10,
        wave_slope=-0.20,
        vwap_sigma_wave=-1.20,
        state_duration=3,
    )
    assert isinstance(vec, ProbabilitySnapshot)
    assert vec.p_take_profit >= 0.0
    assert vec.p_stop_loss >= 0.0
    assert vec.sample_size_n >= 0
    assert vec.certainty_score >= 0.0
    assert vec.current_state_duration == 3
    assert vec.duration_bin == "1-3d (Fresh)"
    assert vec.regime_inertia_prob >= 0.0
    assert isinstance(vec.most_likely_next_state, str)
    assert hasattr(vec, "state_key")
    assert not hasattr(vec, "action_code")  # Strictly measurement, zero action strings!
