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
    assert len(adapter.edges_d1) == 5
    assert len(adapter._data) > 0


def test_pcr_guidance_lookup_valid():
    """Verify guidance lookup for standard PCR values and velocity vectors."""
    guidance = pcr_lookup.lookup_pcr_guidance(pcr_val=0.85, pcr_d3=-0.10)
    assert guidance is not None
    assert isinstance(guidance, PCRStateGuidance)
    assert guidance.pcr_bin in ['CALL_EUPHORIA', 'BULLISH_PCR', 'NEUTRAL_PCR', 'ELEVATED_PUTS', 'BEARISH_PCR', 'EXTREME_PUT_PANIC']
    assert guidance.velocity_vector in ["FAST_CRUSH_3D", "DECELERATING_DOWN_3D", "STABLE_CONTINUATION_3D", "ACCELERATING_UP_3D", "FAST_SPIKE_3D"]


def test_pcr_vector_export():
    """Verify vector extraction for API contracts."""
    guidance = pcr_lookup.lookup_pcr_guidance(pcr_val=0.85, pcr_d3=-0.10)
    vec = guidance.to_vector()
    assert "primary_p_bull" in vec
    assert "primary_ev_net" in vec
    assert "primary_capital_velocity" in vec
    assert vec["primary_capital_velocity"] == vec["ev_per_day"]["zz50"]
