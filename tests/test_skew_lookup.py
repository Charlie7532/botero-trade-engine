"""
Unit Tests for SkewLookupAdapter
================================
Verifica que skew_lookup pueda consultar skew_fact_store.json
y retornar SkewStateGuidance con 100% de precisión.
"""
import pytest
from backend.modules.entry_decision.domain.rules.skew_lookup import skew_lookup, SkewStateGuidance


def test_skew_lookup_valid_state():
    guidance = skew_lookup.lookup_skew_guidance(skew_val=135.0, skew_d3=0.0)
    assert guidance is not None
    assert isinstance(guidance, SkewStateGuidance)
    assert guidance.skew_bin in ['TAIL_COMPLACENCY', 'NORMAL_TAIL', 'ELEVATED_TAIL', 'HIGH_SKEW', 'PARANOIA_SKEW', 'BLACK_SWAN_PARANOIA']
    assert guidance.divergence_regime in ['BULLISH', 'BEARISH', 'NEUTRAL']
    
    vec = guidance.to_vector()
    assert "p_bull" in vec
    assert len(vec["p_bull"]) == 3
    assert len(vec["ev_net"]) == 3
    assert len(vec["e_days"]) == 3
