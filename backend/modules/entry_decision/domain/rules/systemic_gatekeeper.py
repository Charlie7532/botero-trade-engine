"""
Systemic Gatekeeper — Non-Invasive HSA Overlay Adapter
======================================================
Wraps existing, optimized decision gates without modifying their internal logic.
Translates names to standardized MKT_, SEC_, and AST_ prefixes and enforces
top-down macro vetoes (Level 1 over Level 2/3).

Clean Architecture: Domain rule — pure Python, 0 infrastructure dependencies.
Follows AGENTS.md rules.
"""
from typing import Dict, Any, Tuple, Optional
from backend.modules.shared.domain.entities.systemic_pulse import SystemicPulse

# Translation mapping for backward compatibility (Legacy Spanish <-> Homologated English)
ROTATION_REGIME_HOMOLOGATION: Dict[str, str] = {
    "CRASH_SISTEMICO": "SEC_SYSTEMIC_CRASH",
    "DISTRIBUCION_PRE_CRASH": "SEC_PRE_CRASH_DISTRIBUTION",
    "PISO_GENERACIONAL": "SEC_GENERATIONAL_FLOOR",
    "RE_ACUMULACION_ALCISTA": "SEC_BULLISH_REACCUMULATION",
    "BEAR_RALLY": "SEC_BEAR_RALLY",
    "PULLBACK_ALCISTA": "SEC_BULLISH_PULLBACK",
    "MERCADO_SANO": "SEC_HEALTHY_BULL",
    "RECUPERACION": "SEC_ROTATIONAL_RECOVERY",
    "CAPITULACION_SECTORIAL": "SEC_SECTOR_CAPITULATION",
    "NORMAL": "SEC_NORMAL",
}


def map_fg_score_to_ses(fg_score: float) -> str:
    """Map F&G score (0-100) to 5-level Sentiment State (SES 1-5)."""
    if fg_score > 80.0:
        return "MKT_SES_1_EUPHORIA"
    elif fg_score >= 65.0:
        return "MKT_SES_2_GREED"
    elif fg_score >= 35.0:
        return "MKT_SES_3_NEUTRAL"
    elif fg_score >= 20.0:
        return "MKT_SES_4_FEAR"
    else:
        return "MKT_SES_5_PANIC"


class SystemicGatekeeper:
    """Non-Invasive Overlay Gatekeeper for Hierarchical Signals."""

    @staticmethod
    def create_pulse(
        market_health_dict: Optional[Dict[str, Any]] = None,
        rotation_mode: str = "NORMAL",
        target_weights: Optional[Dict[str, float]] = None,
        ast_ticker: Optional[str] = None,
        ast_signal: str = "WATCH",
        ast_conviction: float = 0.0,
        ast_reasoning: str = "",
    ) -> SystemicPulse:
        """Construct SystemicPulse from raw gate inputs with standardized prefixes."""
        mh = market_health_dict or {}

        fg_score = float(mh.get("fg_score", 50.0))
        ses_state = map_fg_score_to_ses(fg_score)

        spec_vol = str(mh.get("vol_regime_speculative", "STALK")).upper()
        vol_state = f"MKT_VOL_{spec_vol}"

        conv_dir = str(mh.get("convergence_direction", "NEUTRAL")).upper()
        mkt_conv = f"MKT_{conv_dir}"

        sec_homologated = ROTATION_REGIME_HOMOLOGATION.get(
            rotation_mode, f"SEC_{rotation_mode.upper()}"
        )

        ast_prefixed = f"AST_{ast_signal.upper()}" if not ast_signal.startswith("AST_") else ast_signal

        return SystemicPulse(
            mkt_sentiment_state=ses_state,
            mkt_volatility_state=vol_state,
            mkt_convergence_direction=mkt_conv,
            mkt_fg_score=fg_score,
            sec_rotation_regime=sec_homologated,
            sec_legacy_regime=rotation_mode,
            sec_target_weights=target_weights or {},
            sec_divergent_leadership=mh.get("narrow_market", False),
            ast_ticker=ast_ticker,
            ast_signal=ast_prefixed,
            ast_conviction=ast_conviction,
            ast_reasoning=ast_reasoning,
            metadata=mh,
        )

    @staticmethod
    def evaluate_overlay_veto(
        pulse: SystemicPulse,
        department: str = "QUALITY_SWING",
        ticker_sector: Optional[str] = None,
    ) -> Tuple[str, float, str]:
        """Evaluate top-down macro vetoes without modifying internal gate logic.

        Args:
            pulse: Standardized SystemicPulse instance.
            department: "QUALITY_SWING" | "SPECULATIVE" | "QUALITY_CORE".
            ticker_sector: Optional sector symbol (e.g. "XLK") for sector-stage checks.

        Returns:
            (verdict, sizing_modifier, reason) tuple.
            verdict: "ALLOW" | "BLOCK" | "REDUCE"
        """
        # 1. Level 1 Hard Veto: Volatility RETREAT / Systemic Crisis
        if pulse.mkt_volatility_state == "MKT_VOL_RETREAT" or pulse.sec_rotation_regime == "SEC_SYSTEMIC_CRASH":
            if department in ("SPECULATIVE", "QUALITY_SWING"):
                return "BLOCK", 0.0, f"MKT_VETO: Hard block under {pulse.mkt_volatility_state} / {pulse.sec_rotation_regime}"

        # 2. Mission Adaptability: Speculative Department
        if department == "SPECULATIVE":
            if pulse.mkt_sentiment_state == "MKT_SES_1_EUPHORIA":
                return "REDUCE", 0.5, "MKT_WARN: Speculative complacency warning under MKT_SES_1_EUPHORIA"
            return "ALLOW", 1.0, "MKT_OK: Speculative execution approved"

        # 3. Mission Adaptability: Quality Swing Department
        if department == "QUALITY_SWING":
            # Avoid Blind Spot A: Do NOT block swing accumulation in bullish pullbacks / bottoms
            # even if market health is in a general correction
            if pulse.ast_signal == "AST_ACCUMULATE":
                # Sentiment Panic (SES 5) acts as a conviction catalyst for Quality Moat accumulation
                if pulse.mkt_sentiment_state == "MKT_SES_5_PANIC":
                    return "ALLOW", 1.5, "MKT_CATALYST: Capitulation panic (SES 5) boosts Quality Swing accumulation"
                return "ALLOW", 1.0, "AST_OK: Quality Swing accumulation approved"

        return "ALLOW", 1.0, "MKT_OK: Normal execution"
