"""
SystemicPulse — Domain Entity for Unified Hierarchical Signals (HSA)
======================================================================
Holds the consolidated state across all 3 scopes of market intelligence:
  - Level 1: Market Scope ([MKT_] prefix) — Systemic & Sentiment Macro
  - Level 2: Sector Scope ([SEC_] prefix) — Sector Rotation Regimes & Breadth
  - Level 3: Asset Scope  ([AST_] prefix) — Single Ticker Execution Timing

Pure domain entity — zero infrastructure dependencies.
Follows Clean Architecture rules.
"""
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Dict, Any, Optional


@dataclass(frozen=True)
class SystemicPulse:
    """Consolidated Hierarchical Signal Snapshot."""

    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    # ── Level 1: MARKET SCOPE [MKT_] ──────────────────────────
    mkt_sentiment_state: str = "MKT_SES_3_NEUTRAL"   # MKT_SES_1_EUPHORIA ... MKT_SES_5_PANIC
    mkt_volatility_state: str = "MKT_VOL_STABLE"     # MKT_VOL_STABLE/STRIKE/HARVEST/RETREAT
    mkt_convergence_direction: str = "MKT_NEUTRAL"  # MKT_RISK_ON/NEUTRAL/RISK_OFF
    mkt_fg_score: float = 50.0                        # Raw 0-100 score

    # ── Level 2: SECTOR SCOPE [SEC_] ──────────────────────────
    sec_rotation_regime: str = "SEC_HEALTHY_BULL"    # SEC_HEALTHY_BULL, SEC_SYSTEMIC_CRASH, etc.
    sec_legacy_regime: str = "MERCADO_SANO"          # Legacy Spanish string for 100% backward compat
    sec_target_weights: Dict[str, float] = field(default_factory=dict)
    sec_divergent_leadership: bool = False

    # ── Level 3: ASSET SCOPE [AST_] (Optional per ticker) ─────
    ast_ticker: Optional[str] = None
    ast_signal: str = "AST_WATCH"                     # AST_ACCUMULATE, AST_BUY_DIP, AST_TAKE_PROFIT, AST_REDUCE
    ast_conviction: float = 0.0
    ast_reasoning: str = ""

    # Metadata for diagnostic logging
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize snapshot for logging or persistence."""
        return {
            "timestamp": self.timestamp,
            "mkt_sentiment_state": self.mkt_sentiment_state,
            "mkt_volatility_state": self.mkt_volatility_state,
            "mkt_convergence_direction": self.mkt_convergence_direction,
            "mkt_fg_score": self.mkt_fg_score,
            "sec_rotation_regime": self.sec_rotation_regime,
            "sec_legacy_regime": self.sec_legacy_regime,
            "sec_target_weights": self.sec_target_weights,
            "sec_divergent_leadership": self.sec_divergent_leadership,
            "ast_ticker": self.ast_ticker,
            "ast_signal": self.ast_signal,
            "ast_conviction": self.ast_conviction,
            "ast_reasoning": self.ast_reasoning,
            "metadata": self.metadata,
        }
