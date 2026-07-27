"""
Unit tests for Quality Entry Gate — Rule 20 Action Taxonomy Compliance
========================================================================
Validates that:
  1. All decisions emit 4-dimensional action codes (STK_*) and FIX urgency tags.
  2. CRISIS regime triggers STK_BLOCK_CRISIS.
  3. Holding duration >= 10 days triggers STK_EXIT_TIME_STOP.
  4. Oversold + EXHAUSTING + High R:R triggers STK_BUY_DIP_TACTICAL.
  5. High P_bull + Megatrend triggers STK_ACCUMULATE_STRUCTURAL.
  6. High P_techo_75 or negative EV triggers STK_DISTRIBUTE_DECAY.
"""
import pytest
from backend.modules.quality_swing.domain.rules.rc_multiscale_ev_lookup import (
    MultiscaleEVKinematicSignal,
)
from backend.modules.quality_swing.domain.rules.quality_entry_gate import (
    evaluate_quality_entry_gate,
)


def test_crisis_veto():
    decision = evaluate_quality_entry_gate(
        multiscale_signal=None,
        vol_regime_label="CRISIS",
    )
    assert decision.action_code == "STK_BLOCK_CRISIS"
    assert decision.urgency_tag == "URGENCY_EMERGENCY"
    assert decision.conviction_weight == 0.0


def test_time_stop_barrier():
    decision = evaluate_quality_entry_gate(
        multiscale_signal=None,
        vol_regime_label="NORMAL",
        holding_days=10,
    )
    assert decision.action_code == "STK_EXIT_TIME_STOP"
    assert decision.urgency_tag == "URGENCY_NORMAL"
    assert decision.conviction_weight == 0.0


def test_tactical_dip_buy():
    sig = MultiscaleEVKinematicSignal(
        p_bull=0.55,
        p_bull_raw=0.55,
        p_piso_25=0.55,
        p_piso_50=0.08,
        p_piso_75=0.02,
        p_techo_25=0.02,
        p_techo_50=0.01,
        p_techo_75=0.0,
        ev_net=0.012,
        sharpe=0.45,
        e_ret_max=0.35,
        e_ret_min=-0.02,
        e_ret_max_25=0.05,
        e_ret_min_25=-0.02,
        ev_net_25=0.012,
        e_ret_max_50=0.08,
        e_ret_min_50=-0.02,
        ev_net_50=0.015,
        e_ret_max_75=0.12,
        e_ret_min_75=-0.02,
        ev_net_75=0.018,
        rr_asymmetry=17.5,
        n_samples=134,
        fallback_level="S1",
        lookup_key="T+++|C+++|W--|<<|<<|<<#EXHAUSTING",
        kinematic_trajectory="EXHAUSTING",
    )
    
    decision = evaluate_quality_entry_gate(
        multiscale_signal=sig,
        vol_regime_label="NORMAL",
        sector="Technology",
        is_tollkeeper=True,
    )
    assert decision.action_code == "STK_BUY_DIP_TACTICAL"
    assert decision.urgency_tag in ["URGENCY_HIGH", "URGENCY_NORMAL"]
    assert decision.conviction_weight > 0.5
    assert decision.rr_asymmetry == 17.5


def test_structural_accumulation():
    sig = MultiscaleEVKinematicSignal(
        p_bull=0.78,
        p_bull_raw=0.78,
        p_piso_25=0.78,
        p_piso_50=0.12,
        p_piso_75=0.04,
        p_techo_25=0.01,
        p_techo_50=0.0,
        p_techo_75=0.0,
        ev_net=0.025,
        sharpe=0.85,
        e_ret_max=0.15,
        e_ret_min=-0.01,
        e_ret_max_25=0.04,
        e_ret_min_25=-0.01,
        ev_net_25=0.025,
        e_ret_max_50=0.08,
        e_ret_min_50=-0.01,
        ev_net_50=0.028,
        e_ret_max_75=0.15,
        e_ret_min_75=-0.01,
        ev_net_75=0.032,
        rr_asymmetry=15.0,
        n_samples=500,
        fallback_level="S1",
        lookup_key="T+++|C+++|W+|~|~|~#STABLE",
        kinematic_trajectory="STABLE",
    )

    decision = evaluate_quality_entry_gate(
        multiscale_signal=sig,
        vol_regime_label="NORMAL",
        is_tollkeeper=True,
    )
    assert decision.action_code == "STK_ACCUMULATE_STRUCTURAL"
    assert decision.urgency_tag == "URGENCY_HIGH"
    assert decision.conviction_weight >= 0.85


def test_distribution_decay():
    sig = MultiscaleEVKinematicSignal(
        p_bull=0.30,
        p_bull_raw=0.30,
        p_piso_25=0.30,
        p_piso_50=0.01,
        p_piso_75=0.0,
        p_techo_25=0.25,
        p_techo_50=0.18,
        p_techo_75=0.16,
        ev_net=-0.020,
        sharpe=-0.35,
        e_ret_max=0.02,
        e_ret_min=-0.06,
        e_ret_max_25=0.02,
        e_ret_min_25=-0.04,
        ev_net_25=-0.020,
        e_ret_max_50=0.02,
        e_ret_min_50=-0.05,
        ev_net_50=-0.022,
        e_ret_max_75=0.02,
        e_ret_min_75=-0.06,
        ev_net_75=-0.025,
        rr_asymmetry=0.33,
        n_samples=200,
        fallback_level="S1",
        lookup_key="T---|C---|W+++|~|>>|>>#ABSORBING",
        kinematic_trajectory="ABSORBING",
    )

    decision = evaluate_quality_entry_gate(
        multiscale_signal=sig,
        vol_regime_label="NORMAL",
    )
    assert decision.action_code == "STK_DISTRIBUTE_DECAY"
    assert decision.urgency_tag == "URGENCY_NORMAL"
    assert decision.conviction_weight == 0.0
