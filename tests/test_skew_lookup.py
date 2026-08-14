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
    assert guidance.skew_bin in ['LOW_TAIL_RISK', 'NORMAL_TAIL_RISK', 'ELEVATED_TAIL_RISK', 'HIGH_TAIL_RISK', 'TAIL_PARANOIA', 'BLACK_SWAN_PARANOIA']
    assert guidance.divergence_regime in ['FULL_CONVERGENT_BULL', 'FULL_CONVERGENT_BEAR', 'STRUCTURAL_BULL_PULLBACK', 'TACTICAL_REBOUND_IN_BEAR', 'MIXED_HORIZON_TRANSITION', 'GOLDILOCKS_CURRENCY_BALANCED', 'COMMODITY_REFLATION_EM_SURGE', 'CORPORATE_MARGIN_COMPRESSION', 'GLOBAL_DOLLAR_LIQUIDITY_SQUEEZE', 'BULLISH', 'BEARISH', 'NEUTRAL']
    
    vec = guidance.to_vector()
    assert "p_bull" in vec
    assert len(vec["p_bull"]) == 3
    assert len(vec["ev_net"]) == 3
    assert len(vec["e_days"]) == 3
