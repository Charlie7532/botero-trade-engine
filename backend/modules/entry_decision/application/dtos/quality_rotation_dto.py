"""
QUALITY ROTATION DTO — APPLICATION LAYER DTO
============================================
Clean Architecture: Application Layer (Data Transfer Objects)
Module: entry_decision / application / dtos

Data transfer objects representing Quality Department Entry & Rotation decisions,
adhering to Rule 20 (Universal Signal & Action Taxonomy Standard):
  - Scope: SEC_ (Sector), STK_ (Individual Stock), MKT_ (Market/Macro)
  - Action codes: STK_ACCUMULATE_STRUCTURAL, STK_BUY_DIP_TACTICAL, STK_HOLD_STABLE,
                  STK_TRIM_TACTICAL, STK_BLOCK_CRISIS, etc.
  - Urgency Tags: URGENCY_EMERGENCY, URGENCY_HIGH, URGENCY_NORMAL, URGENCY_LOW.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class QualityRotationDTO:
    """
    Structured outcome of Quality Entry Gate evaluation.
    Used by orchestrators, execution layers, and trade forensics.
    """
    mode: str
    target_weights: Dict[str, float] = field(default_factory=dict)
    ticker: Optional[str] = None
    action_code: str = "SEC_HOLD_STABLE"
    urgency: str = "URGENCY_NORMAL"
    final_verdict: str = "ALLOW"      # "ALLOW" | "BLOCK" | "STALK"
    final_reason: str = ""
    final_scale: float = 1.0
    state_snapshot: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "target_weights": self.target_weights,
            "ticker": self.ticker,
            "action_code": self.action_code,
            "urgency": self.urgency,
            "final_verdict": self.final_verdict,
            "final_reason": self.final_reason,
            "final_scale": self.final_scale,
            "state_snapshot": self.state_snapshot,
        }
