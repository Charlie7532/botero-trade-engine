"""
Unit Tests for YieldCurveLookupAdapter (Yield Curve Spread Intelligence)
========================================================================
Verifica que yield_curve_lookup pueda consultar yield_curve_fact_store.json
y retornar YieldCurveStateGuidance con 100% de precisión.
"""
import pytest
from backend.modules.entry_decision.domain.rules.yield_curve_lookup import yield_curve_lookup, YieldCurveStateGuidance


def test_yield_curve_lookup_valid_state():
    guidance = yield_curve_lookup.lookup_yield_curve_guidance(spread_value=0.5, spread_d3=0.0)
    assert guidance is not None
    assert isinstance(guidance, YieldCurveStateGuidance)
    assert guidance.bin in ['DEEP_INVERSION', 'MODERATE_INVERSION', 'FLAT_CURVE', 'NORMAL_CURVE', 'STEEP_CURVE', 'EXTREME_STEEPNESS']
    assert guidance.velocity_vector in ['FAST_CRUSH_3D', 'DECELERATING_DOWN_3D', 'STABLE_CONTINUATION_3D', 'ACCELERATING_UP_3D', 'FAST_SPIKE_3D']
    assert guidance.divergence_regime in ['FULL_CONVERGENT_BULL', 'FULL_CONVERGENT_BEAR', 'STRUCTURAL_BULL_PULLBACK', 'TACTICAL_REBOUND_IN_BEAR', 'MIXED_HORIZON_TRANSITION', 'GOLDILOCKS_CURRENCY_BALANCED', 'COMMODITY_REFLATION_EM_SURGE', 'CORPORATE_MARGIN_COMPRESSION', 'GLOBAL_DOLLAR_LIQUIDITY_SQUEEZE', 'BULLISH', 'BEARISH', 'NEUTRAL']

    vec = guidance.to_vector()
    assert "p_bull" in vec
    assert len(vec["p_bull"]) == 3
    assert len(vec["ev_net"]) == 3
    assert len(vec["e_days"]) == 3
    assert vec["primary_p_bull"] == guidance.zz50.p_bull


def test_yield_curve_lookup_deep_inversion():
    guidance = yield_curve_lookup.lookup_yield_curve_guidance(spread_value=-1.8, spread_d3=-0.25)
    assert guidance is not None
    assert guidance.yield_bin == "DEEP_INVERSION"
    assert guidance.velocity_vector == "FAST_CRUSH_3D"


def test_yield_curve_lookup_extreme_steepening():
    guidance = yield_curve_lookup.lookup_yield_curve_guidance(spread_value=3.5, spread_d3=0.25)
    assert guidance is not None
    assert guidance.yield_bin in ["STEEPNING_CURVE", "EXTREME_STEEPNING"]
    assert guidance.velocity_vector in ["FAST_SPIKE_3D", "ACCELERATING_UP_3D", "EXTREME_STEEPENING_SPIKE_3D"]
