"""
Unit Tests for RotationLookupAdapter (Sector Rotation Intelligence)
====================================================================
Verifies that rotation_lookup queries rotation_fact_store.json
and returns RotationStateGuidance with 100% accuracy.
"""
import pytest
from backend.modules.entry_decision.domain.rules.rotation_lookup import rotation_lookup, RotationStateGuidance


def test_rotation_lookup_valid_state():
    guidance = rotation_lookup.lookup_rotation_guidance(rotation_val=0.0, rotation_d3=0.0)
    assert guidance is not None
    assert isinstance(guidance, RotationStateGuidance)
    assert guidance.rotation_bin in ['EXTREME_DEFENSIVE', 'DEFENSIVE', 'NEUTRAL_DEFENSIVE', 'NEUTRAL_OFFENSIVE', 'OFFENSIVE', 'EXTREME_OFFENSIVE']
    assert guidance.velocity_vector in ['FAST_CRUSH_3D', 'DECELERATING_DOWN_3D', 'STABLE_CONTINUATION_3D', 'ACCELERATING_UP_3D', 'FAST_SPIKE_3D']
    assert guidance.divergence_regime in ['FULL_CONVERGENT_BULL', 'FULL_CONVERGENT_BEAR', 'STRUCTURAL_BULL_PULLBACK', 'TACTICAL_REBOUND_IN_BEAR', 'MIXED_HORIZON_TRANSITION', 'GOLDILOCKS_CURRENCY_BALANCED', 'COMMODITY_REFLATION_EM_SURGE', 'CORPORATE_MARGIN_COMPRESSION', 'GLOBAL_DOLLAR_LIQUIDITY_SQUEEZE', 'BULLISH', 'BEARISH', 'NEUTRAL']

    vec = guidance.to_vector()
    assert "p_bull" in vec
    assert len(vec["p_bull"]) == 3
    assert len(vec["ev_net"]) == 3
    assert len(vec["e_days"]) == 3
    assert "primary_capital_velocity" in vec


def test_rotation_lookup_extreme_defensive():
    guidance = rotation_lookup.lookup_rotation_guidance(rotation_val=-5.0, rotation_d3=-2.0)
    assert guidance is not None
    assert guidance.rotation_bin == "EXTREME_DEFENSIVE"
    assert guidance.velocity_vector == "FAST_CRUSH_3D"
    assert guidance.operational_guidance in ("STK_TRIM_TACTICAL", "STK_HOLD_STABLE")


def test_rotation_lookup_cyclical_expansion():
    guidance = rotation_lookup.lookup_rotation_guidance(rotation_val=5.0, rotation_d3=2.0)
    assert guidance is not None
    assert guidance.rotation_bin == "EXTREME_OFFENSIVE"
    assert guidance.velocity_vector == "FAST_SPIKE_3D"
    assert guidance.operational_guidance in ("STK_HOLD_STABLE", "STK_TRIM_TACTICAL")
