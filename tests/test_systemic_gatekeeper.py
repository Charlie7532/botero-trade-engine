"""
Unit Tests for SystemicGatekeeper and SystemicPulse (HSA)
===========================================================
Validates signal prefix mapping, sentiment state SES 1-5 mapping,
and non-invasive macro veto rules.
"""
import pytest
from backend.modules.shared.domain.entities.systemic_pulse import SystemicPulse
from backend.modules.entry_decision.domain.rules.systemic_gatekeeper import (
    SystemicGatekeeper,
    map_fg_score_to_ses,
    ROTATION_REGIME_HOMOLOGATION,
)


class TestSystemicGatekeeper:
    """Test suite for SystemicGatekeeper non-invasive overlay."""

    def test_ses_mapping(self):
        """F&G score accurately maps to 5-level Sentiment State (SES 1-5)."""
        assert map_fg_score_to_ses(85.0) == "MKT_SES_1_EUPHORIA"
        assert map_fg_score_to_ses(70.0) == "MKT_SES_2_GREED"
        assert map_fg_score_to_ses(50.0) == "MKT_SES_3_NEUTRAL"
        assert map_fg_score_to_ses(25.0) == "MKT_SES_4_FEAR"
        assert map_fg_score_to_ses(10.0) == "MKT_SES_5_PANIC"

    def test_homologation_dictionary(self):
        """Legacy Spanish strings map to standardized SEC_ prefixes."""
        assert ROTATION_REGIME_HOMOLOGATION["CRASH_SISTEMICO"] == "SEC_SYSTEMIC_CRASH"
        assert ROTATION_REGIME_HOMOLOGATION["MERCADO_SANO"] == "SEC_HEALTHY_BULL"
        assert ROTATION_REGIME_HOMOLOGATION["PULLBACK_ALCISTA"] == "SEC_BULLISH_PULLBACK"

    def test_create_pulse_prefixes(self):
        """Pulse creation correctly applies MKT_, SEC_, and AST_ prefixes."""
        mh = {
            "fg_score": 15.0,
            "vol_regime_speculative": "STRIKE",
            "convergence_direction": "RISK_ON",
        }
        pulse = SystemicGatekeeper.create_pulse(
            market_health_dict=mh,
            rotation_mode="MERCADO_SANO",
            ast_ticker="AAPL",
            ast_signal="BUY_DIP",
            ast_conviction=0.85,
        )

        assert pulse.mkt_sentiment_state == "MKT_SES_5_PANIC"
        assert pulse.mkt_volatility_state == "MKT_VOL_STRIKE"
        assert pulse.sec_rotation_regime == "SEC_HEALTHY_BULL"
        assert pulse.sec_legacy_regime == "MERCADO_SANO"
        assert pulse.ast_signal == "AST_BUY_DIP"
        assert pulse.ast_ticker == "AAPL"

    def test_systemic_retreat_veto(self):
        """MKT_VOL_RETREAT forces hard block on Speculative and Quality Swing."""
        mh = {"vol_regime_speculative": "RETREAT", "fg_score": 10.0}
        pulse = SystemicGatekeeper.create_pulse(market_health_dict=mh, rotation_mode="NORMAL")

        verdict, scale, reason = SystemicGatekeeper.evaluate_overlay_veto(
            pulse, department="SPECULATIVE"
        )
        assert verdict == "BLOCK"
        assert scale == 0.0
        assert "Hard block" in reason

    def test_panic_catalyst_boosts_swing(self):
        """Panic sentiment (SES 5) acts as a conviction catalyst for Quality Swing accumulation."""
        mh = {"vol_regime_speculative": "STALK", "fg_score": 12.0}
        pulse = SystemicGatekeeper.create_pulse(
            market_health_dict=mh,
            rotation_mode="NORMAL",
            ast_signal="ACCUMULATE",
        )

        verdict, scale, reason = SystemicGatekeeper.evaluate_overlay_veto(
            pulse, department="QUALITY_SWING"
        )
        assert verdict == "ALLOW"
        assert scale == 1.5
        assert "MKT_CATALYST" in reason
