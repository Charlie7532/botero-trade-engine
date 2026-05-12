"""
Barrier Labeler Port — Triple Barrier Abstraction
====================================================
Decouples Oracle backtesting from the concrete TripleBarrierLabeler
implementation (which will live in infrastructure in Phase 3).

Implementor: triple_barrier_adapter.py (Phase 2)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass
class BarrierLabel:
    """Result of labeling a single entry point."""
    label: int             # 1=profit hit, -1=loss hit, 0=time exit
    return_pct: float      # Actual return achieved
    bars_held: int         # Bars until barrier was hit
    hit_barrier: str       # "profit", "loss", "time"
    entry_time: pd.Timestamp = None
    exit_time: pd.Timestamp = None


class BarrierLabelerPort(ABC):
    """Port for Triple Barrier labeling used by Oracle Backtester."""

    @abstractmethod
    def label_entries(
        self,
        ohlc: pd.DataFrame,
        entries: pd.Series,
        profit_mult: float,
        loss_mult: float,
        max_bars: int,
        vol_lookback: int = 20,
    ) -> list[BarrierLabel]:
        """
        Apply Triple Barrier to each entry point.

        Args:
            ohlc: Canonical OHLCV DataFrame.
            entries: Boolean Series marking entry bars.
            profit_mult: ATR multiplier for take-profit barrier.
            loss_mult: ATR multiplier for stop-loss barrier.
            max_bars: Maximum bars before time exit.
            vol_lookback: ATR lookback window.

        Returns:
            List of BarrierLabel results, one per entry.
        """
