"""
StateSnapshot — Temporal Context for Regime Classifications
==============================================================
Pure domain entity. Frozen dataclass — no business logic, no thresholds.

Threshold-based decisions (is_fresh, is_aging, is_exhausted) belong in
domain rules where each gate applies its own calibrated values.

Evidence Status: VALIDATED — pattern from TickerProfile, ChannelSnapshot.
Clean Architecture: Domain layer. Zero infrastructure dependencies.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class StateSnapshot:
    """Temporal context for a regime/phase/state classification.

    Attributes:
        key: Structured identifier. Format: {classifier}:{department}:{scope}
             Examples: "vol:quality:MARKET", "cascade:MARKET", "vol:quality:AAPL"
        current_state: Active regime label (e.g. "ELEVATED", "STRIKE", "BEAR")
        previous_state: Prior regime label (None on first-ever state)
        entered_at: Timestamp when this state began
        closed_at: None if currently active, timestamp when superseded
        duration_bars: Pre-computed daily bar count in current state.
                       Daemon-maintained (incremented daily), NOT computed
                       dynamically from timestamps. Avoids backtest clock bug.
        trigger_event: Human-readable cause (e.g. "VIX_ZSCORE=2.3")
        metadata: Extensible context (e.g. sensor values at transition)
    """
    key: str
    current_state: str
    previous_state: Optional[str]
    entered_at: datetime
    closed_at: Optional[datetime]
    duration_bars: int
    trigger_event: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
