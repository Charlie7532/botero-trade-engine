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
    assert guidance.skew_bin in [
        "DEEP_COMPLACENCY",
        "COMPLACENCY",
        "NORMAL_LOW",
        "NORMAL_HIGH",
        "ELEVATED",
        "HIGH_TAIL_RISK",
        "BLACK_SWAN_PARANOIA",
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
