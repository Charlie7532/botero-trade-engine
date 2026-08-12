"""
Unit Tests for BSILookupAdapter (Breadth Shock Index Intelligence)
===================================================================
Verifies that bsi_lookup queries bsi_fact_store.json with 100% precision
and returns BSIStateGuidance for S5TW magnitude and 72h kinematic shock velocity.
"""
import pytest
from backend.modules.entry_decision.domain.rules.bsi_lookup import bsi_lookup, BSIStateGuidance


def test_bsi_lookup_valid_state():
    guidance = bsi_lookup.lookup_bsi_guidance(val=55.0, d3_speed=0.0)
    assert guidance is not None
    assert isinstance(guidance, BSIStateGuidance)
    assert guidance.bsi_bin in [
        'BREADTH_WASHED_OUT', 'OVERSOLD_BREADTH', 'NEUTRAL_LOW_BREADTH',
        'NEUTRAL_HIGH_BREADTH', 'EXPANSIVE_BREADTH', 'HYPER_EXPANSIVE_BREADTH'
    ]
    assert guidance.velocity_vector in [
        'FAST_CRUSH_3D', 'DECELERATING_DOWN_3D', 'STABLE_CONTINUATION_3D',
        'ACCELERATING_UP_3D', 'FAST_SPIKE_3D'
    ]

    vec = guidance.to_vector()
    assert "p_bull" in vec
    assert len(vec["p_bull"]) == 3
    assert len(vec["ev_net"]) == 3
    assert len(vec["e_days"]) == 3
    assert vec["primary_p_bull"] == guidance.zz50.p_bull


def test_bsi_lookup_washed_out_breadth():
    # Extreme oversold S5TW < 11.0%
    guidance = bsi_lookup.lookup_bsi_guidance(val=8.0, d3_speed=-35.0)
    assert guidance is not None
    assert guidance.bsi_bin == "BREADTH_WASHED_OUT"
    assert guidance.velocity_vector == "FAST_CRUSH_3D"


def test_bsi_lookup_hyper_expansive_shock():
    # Extreme expansive S5TW > 89.7% with positive shock
    guidance = bsi_lookup.lookup_bsi_guidance(val=92.0, d3_speed=35.0)
    assert guidance is not None
    assert guidance.bsi_bin == "HYPER_EXPANSIVE_BREADTH"
    assert guidance.velocity_vector == "FAST_SPIKE_3D"
