"""
Unit tests for CBOE Equity Put/Call Ratio (PCR) Fact Store & Pure Domain Lookup Adapter
"""
import pytest
from backend.modules.entry_decision.domain.rules.pcr_lookup import (
    pcr_lookup,
    PCRStateGuidance,
    PCRLookupAdapter
)


def test_pcr_fact_store_loading():
    """Verify that pcr_lookup adapter loads the Fact Store successfully."""
    adapter = PCRLookupAdapter()
    assert len(adapter.edges_d1) == 6
    assert len(adapter.pcr_speed_edges) == 6
    assert len(adapter.states) >= 40  # 45 empirical state permutations observed


def test_pcr_guidance_lookup_valid():
    """Verify guidance lookup for standard PCR values and velocity vectors."""
    guidance = pcr_lookup.lookup_pcr_guidance(pcr_val=0.85, pcr_d3=-0.10)
    assert guidance is not None
    assert isinstance(guidance, PCRStateGuidance)
    assert guidance.pcr_bin in ['CALL_EUPHORIA', 'BULLISH_BIAS', 'NEUTRAL_PCR', 'ELEVATED_PUTS', 'PANIC_PUTS', 'EXTREME_HEDGING']
    assert guidance.velocity_vector in ['FAST_CRUSH_3D', 'DECELERATING_DOWN_3D', 'STABLE_CONTINUATION_3D', 'ACCELERATING_UP_3D', 'FAST_SPIKE_3D']
    assert guidance.n > 0


def test_pcr_vector_export():
    """Verify that guidance to_vector() returns complete structured vector."""
    guidance = pcr_lookup.lookup_pcr_guidance(pcr_val=1.10, pcr_d3=0.20)
    assert guidance is not None
    vec = guidance.to_vector()

    assert "p_bull" in vec
    assert len(vec["p_bull"]) == 3
    assert "ev_net" in vec
    assert len(vec["ev_net"]) == 3
    assert "ev_per_day" in vec
    assert len(vec["ev_per_day"]) == 3
    assert "primary_capital_velocity" in vec
    assert vec["primary_capital_velocity"] == vec["ev_per_day"][1]
