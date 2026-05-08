"""
IndicatorTrend — Macro Indicator with Temporal Context
=======================================================
Pure domain entity. Captures the state of any macro indicator
(VIX, VVIX, Fear & Greed, S5TH, S5TW, HYG, TLT, etc.)
with direction, trend, moving averages, and percentile context.

The VIX is not just "16.84" — it's "16.84, falling, -2.1 vs yesterday,
below MA20, percentile 35 in 90 days."
"""
from dataclasses import dataclass


@dataclass
class IndicatorTrend:
    """State of a macro indicator with full temporal context."""

    name: str                      # "VIX", "VVIX", "FEAR_GREED", "S5TH", "HYG"
    current: float                 # Latest value
    previous: float = 0.0          # Previous day value
    delta_1d: float = 0.0          # Change vs yesterday
    delta_5d: float = 0.0          # Change vs 5 days ago
    ma5: float = 0.0               # 5-day moving average
    ma20: float = 0.0              # 20-day moving average
    direction: str = "FLAT"        # "RISING", "FALLING", "FLAT"
    trend: str = "NEUTRAL"         # "BULLISH", "BEARISH", "NEUTRAL"
    days_of_trend: int = 0         # Consecutive days in same direction
    percentile_90d: float = 50.0   # Current value vs 90-day distribution (0-100)
