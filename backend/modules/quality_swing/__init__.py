"""
Quality Swing — Druckenmiller's Tactical Timing on MOAT Positions
==================================================================
Optimizes accumulation/trimming timing on positions that Quality Core
already approved as tollkeepers. Uses regression channel statistics,
per-ticker fear/greed bias, and market context (breadth, vol regime)
to identify when price is statistically cheap or expensive.

Director: Druckenmiller
Mandate: "Swing around the core — accumulate in fear, trim in greed."
Horizon: Weeks to months.
"""

from backend.modules.quality_swing.domain.entities.swing_bias import TickerSentimentBias
from backend.modules.quality_swing.domain.rules.regression_channel import (
    linreg_channel,
    calc_vwap,
    sigma_position,
)
from backend.modules.quality_swing.domain.rules.fear_level import compute_ticker_fear_level

__all__ = [
    "TickerSentimentBias",
    "linreg_channel",
    "calc_vwap",
    "sigma_position",
    "compute_ticker_fear_level",
]
