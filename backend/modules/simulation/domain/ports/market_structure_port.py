"""
Market Structure Port — SMC Analysis Abstraction
===================================================
Decouples simulation from the concrete smartmoneyconcepts library.
Provides BOS, CHoCH, Order Blocks, FVG, and liquidity sweep detection.

Implementor: smc_adapter.py (Phase 2)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass
class MarketStructureResult:
    """Complete SMC analysis output."""
    # Trend
    swing_trend: str = "UNKNOWN"        # UPTREND, DOWNTREND, RANGING

    # Break of Structure
    bos_detected: bool = False
    bos_direction: str = "NONE"         # BULLISH, BEARISH
    bos_bars_ago: int = 999             # Recency of last BOS

    # Change of Character
    choch_detected: bool = False
    choch_direction: str = "NONE"       # BULLISH, BEARISH

    # Order Blocks
    nearest_ob_price: float = 0.0
    nearest_ob_type: str = "NONE"       # BULLISH, BEARISH
    ob_distance_pct: float = 0.0        # Distance from current price

    # Fair Value Gaps
    fvg_active: bool = False
    fvg_direction: str = "NONE"         # BULLISH, BEARISH
    fvg_midpoint: float = 0.0

    # Liquidity
    liquidity_swept: bool = False       # Recent liquidity sweep
    liquidity_direction: str = "NONE"   # Which side was swept


class MarketStructurePort(ABC):
    """Port for Smart Money Concepts structural analysis."""

    @abstractmethod
    def analyze(self, ohlc: pd.DataFrame) -> MarketStructureResult:
        """
        Run full SMC analysis on OHLCV data.

        Args:
            ohlc: Canonical OHLCV DataFrame with DatetimeIndex UTC.
                  Minimum 50 bars for reliable detection.

        Returns:
            MarketStructureResult with all structural signals.
        """
