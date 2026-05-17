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
    action: str = "HOLD"  # ACCUMULATE, TRIM, HOLD
    conviction: float = 0.0  # 0.0-1.0 for ACCUMULATE, 0.0-0.5 for TRIM
    reasoning: str = ""

    # Context captured at decision time
    sigma_position: float = 0.0
    fear_level: int = 2  # 0-5
    fear_label: str = "NEUTRAL"
    tide_slope: float = 0.0
    wave_slope: float = 0.0
    vol_regime: str = "NORMAL"

    # Alerts (non-blocking observations)
    alerts: list[str] = field(default_factory=list)
