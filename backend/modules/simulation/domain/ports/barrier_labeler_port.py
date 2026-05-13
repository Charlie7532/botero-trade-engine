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
    return_pct: float      # Actual return achieved (net of slippage + costs)
    bars_held: int         # Bars until barrier was hit
    hit_barrier: str       # "profit", "loss", "time"
    entry_time: pd.Timestamp = None
    exit_time: pd.Timestamp = None
    entry_price: float = 0.0  # Actual fill price (VAEP-adjusted)

    # ── Forensic fields (Seykota/Dalio: learn from every trade) ──
    max_adverse_excursion_pct: float = 0.0    # Deepest drawdown DURING trade
    max_favorable_excursion_pct: float = 0.0  # Highest unrealized profit DURING trade
    post_exit_max_pct: float = 0.0            # Max price move AFTER exit (what we missed)
    post_exit_hit_target: bool = False         # Did price eventually hit original TP after exit?
    post_exit_bars_to_target: int = 0          # Bars from exit to when TP would have been hit
    stop_was_sweep: bool = False               # Stop bar close > entry (liquidity sweep, not real selling)


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
        entry_delay_bars: int = 1,
        slippage_factor: float = 0.08,
        round_trip_cost_bps: float = 10.0,
    ) -> list[BarrierLabel]:
        """
        Apply Triple Barrier with realistic execution modeling.

        Args:
            ohlc: Canonical OHLCV DataFrame.
            entries: Boolean Series marking signal bars.
            profit_mult: ATR multiplier for take-profit barrier.
            loss_mult: ATR multiplier for stop-loss barrier.
            max_bars: Maximum bars before time exit.
            vol_lookback: ATR lookback window.
            entry_delay_bars: Bars of latency between signal and fill.
            slippage_factor: Fraction of ATR as volatility-adjusted slippage.
            round_trip_cost_bps: Spread + commission deducted from return.

        Returns:
            List of BarrierLabel results, one per entry.
        """

