"""
Unit Tests for CreditLookupAdapter (Credit Stress Intelligence)
===============================================================
Verifica que credit_lookup pueda consultar credit_fact_store.json
y retornar CreditStateGuidance con 100% de precisión.
"""
import pytest
from backend.modules.entry_decision.domain.rules.credit_lookup import credit_lookup, CreditStateGuidance


def test_credit_lookup_valid_state():
    guidance = credit_lookup.lookup_credit_guidance(credit_ratio=0.58, credit_d3=0.0)
    assert guidance is not None
    assert isinstance(guidance, CreditStateGuidance)
    assert guidance.credit_bin in [
        "EXTREME_CREDIT_FREEZE",
        "CREDIT_STRESS_HIGH",
        "CREDIT_STRESS_MODERATE",
        "NEUTRAL_CREDIT",
        "HEALTHY_CREDIT",
        "EXPANSIVE_CREDIT",
        "MAX_CREDIT_EXPANSION",
    ]
    assert guidance.velocity_vector in [
        "EXTREME_CREDIT_CRASH_3D",
        "FAST_CREDIT_DETERIORATION_3D",
        "DECELERATING_CREDIT_3D",
        "STABLE_CREDIT_3D",
        "EXPANDING_CREDIT_3D",
        "FAST_CREDIT_RECOVERY_3D",
        "EXTREME_CREDIT_SURGE_3D",
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
    assert vec["primary_p_bull"] == guidance.zz50.p_bull


def test_credit_lookup_extreme_freeze():
    guidance = credit_lookup.lookup_credit_guidance(credit_ratio=0.35, credit_d3=-0.03)
    assert guidance is not None
    assert guidance.credit_bin == "EXTREME_CREDIT_FREEZE"
    assert guidance.velocity_vector == "EXTREME_CREDIT_CRASH_3D"


def test_credit_lookup_max_expansion():
    guidance = credit_lookup.lookup_credit_guidance(credit_ratio=0.98, credit_d3=0.03)
    assert guidance is not None
    assert guidance.credit_bin == "MAX_CREDIT_EXPANSION"
    assert guidance.velocity_vector == "EXTREME_CREDIT_SURGE_3D"
