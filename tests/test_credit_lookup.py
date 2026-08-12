"""
Unit Tests for CreditLookupAdapter (Credit Stress Intelligence)
===============================================================
Verifica que credit_lookup pueda consultar credit_fact_store.json
y retornar CreditStateGuidance con 100% de precisión.
"""
import pytest
from backend.modules.entry_decision.domain.rules.credit_lookup import credit_lookup, CreditStateGuidance


def test_credit_lookup_valid_state():
    guidance = credit_lookup.lookup_credit_guidance(credit_ratio=0.64, credit_d3=0.0)
    assert guidance is not None
    assert isinstance(guidance, CreditStateGuidance)
    assert guidance.credit_bin in ['CREDIT_CRISIS', 'CREDIT_STRESS', 'ELEVATED_CREDIT_STRESS', 'STABLE_CREDIT', 'CREDIT_EASE', 'DEEP_CREDIT_EASE']
    assert guidance.velocity_vector in ['FAST_CRUSH_3D', 'DECELERATING_DOWN_3D', 'STABLE_CONTINUATION_3D', 'ACCELERATING_UP_3D', 'FAST_SPIKE_3D']

    vec = guidance.to_vector()
    assert "p_bull" in vec
    assert len(vec["p_bull"]) == 3
    assert len(vec["ev_net"]) == 3
    assert len(vec["e_days"]) == 3
    assert vec["primary_p_bull"] == guidance.zz50.p_bull


def test_credit_lookup_extreme_freeze():
    guidance = credit_lookup.lookup_credit_guidance(credit_ratio=0.50, credit_d3=-0.02)
    assert guidance is not None
    assert guidance.credit_bin == "CREDIT_CRISIS"
    assert guidance.velocity_vector == "FAST_CRUSH_3D"


def test_credit_lookup_max_expansion():
    guidance = credit_lookup.lookup_credit_guidance(credit_ratio=0.75, credit_d3=0.02)
    assert guidance is not None
    assert guidance.credit_bin == "DEEP_CREDIT_EASE"
    assert guidance.velocity_vector == "FAST_SPIKE_3D"
