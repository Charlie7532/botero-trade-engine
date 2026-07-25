"""
Swing Decision DTO — Output of the SwingGate.

Consumed by the CIO Orchestrator, Quality Orchestrator,
and potentially the execution layer.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SwingDecision:
    """Result of SwingGate evaluation for a single ticker."""
    ticker: str
    action_code: str = "STK_HOLD_STABLE"  # Universal Macro Taxonomy: STK_ACCUMULATE_STRUCTURAL, STK_BUY_DIP_TACTICAL, etc.
    wave_action_code: str = "WAVE_NO_EDGE"  # Universal Micro Wave Taxonomy: WAVE_EXHAUSTION_BOTTOM, WAVE_APPROACHING_BOTTOM, etc.
    urgency_level: str = "PASSIVE"  # FIX Tag 61/848: LOW, HIGH, PASSIVE, NORMAL, IMMEDIATE
    scope_level: str = "STK"  # STK, SEC, MKT
    conviction: float = 0.0  # 0.0-1.0 for ACCUMULATE, 0.0-0.5 for TRIM
    reasoning: str = ""


    @property
    def action(self) -> str:
        """Backward-compatible action string dynamically derived from Universal action_code."""
        if self.action_code in ("STK_ACCUMULATE_STRUCTURAL", "STK_BUY_DIP_TACTICAL", "STK_ACCUMULATE_PASSIVE"):
            return "ACCUMULATE"
        if self.action_code in ("STK_TRIM_TACTICAL", "STK_DISTRIBUTE_DECAY"):
            return "TRIM"
        return "HOLD"



    # Context captured at decision time
    sigma_position: float = 0.0
    fear_level: int = 2  # 0-5
    fear_label: str = "NEUTRAL"
    tide_slope: float = 0.0
    wave_slope: float = 0.0
    vol_regime: str = "NORMAL"

    # ML head probabilities at decision time (8 heads)
    ml_scores: dict[str, float] = field(default_factory=dict)

    # Alerts (non-blocking observations)
    alerts: list[str] = field(default_factory=list)
