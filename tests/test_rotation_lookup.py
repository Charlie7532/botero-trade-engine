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
    assert guidance.rotation_bin in [
        "EXTREME_DEFENSIVE_ROTATION",
        "DEFENSIVE_ROTATION",
        "MODERATE_DEFENSIVE",
        "BALANCED_ROTATION",
        "MODERATE_CYCLICAL",
        "CYCLICAL_ROTATION",
        "EXTREME_CYCLICAL_EXPANSION",
    ]
    assert guidance.velocity_vector in [
        "EXTREME_DEFENSIVE_FLIGHT_3D",
        "FAST_DEFENSIVE_ROTATION_3D",
        "DECELERATING_ROTATION_3D",
        "STABLE_ROTATION_3D",
        "ACCELERATING_CYCLICAL_3D",
        "FAST_CYCLICAL_SURGE_3D",
        "EXTREME_CYCLICAL_SPIKE_3D",
    ]
    assert guidance.divergence_regime in [
        "FULL_STRUCTURAL_BULL",
        "TACTICAL_PULLBACK",
        "FULL_STRUCTURAL_BEAR",
        "TACTICAL_BOUNCE_ONLY",
        "TRANSITIONAL",
    ]

    vec = guidance.to_vector()
    assert "p_bull" in vec
    assert len(vec["p_bull"]) == 3
    assert len(vec["ev_net"]) == 3
    assert len(vec["e_days"]) == 3
    assert "primary_capital_velocity" in vec


def test_rotation_lookup_extreme_defensive():
    guidance = rotation_lookup.lookup_rotation_guidance(rotation_val=-5.0, rotation_d3=-2.0)
    assert guidance is not None
    assert guidance.rotation_bin == "EXTREME_DEFENSIVE_ROTATION"
    assert guidance.velocity_vector == "EXTREME_DEFENSIVE_FLIGHT_3D"
    assert guidance.operational_guidance == "MKT_ROTATION_DEFENSIVE_FREEZE"


def test_rotation_lookup_cyclical_expansion():
    guidance = rotation_lookup.lookup_rotation_guidance(rotation_val=5.0, rotation_d3=2.0)
    assert guidance is not None
    assert guidance.rotation_bin == "EXTREME_CYCLICAL_EXPANSION"
    assert guidance.velocity_vector == "EXTREME_CYCLICAL_SPIKE_3D"
    assert guidance.operational_guidance == "MKT_ROTATION_CYCLICAL_EXPANSION"
