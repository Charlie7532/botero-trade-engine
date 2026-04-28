"""
Signal Port — Modular Signal Generator Interface
===================================================
Each intelligence module (Kalman, BOS, RSI, Flow, etc.) implements
this interface to be independently testable by the Oracle and
composable by the StrategyComposer.

Implementors: signal_adapters.py (Phase 2) — 7 thin wrappers
"""
from abc import ABC, abstractmethod

import pandas as pd


class SignalPort(ABC):
    """
    Interface for a standalone signal generator.

    Each implementation wraps an existing intelligence module and
    produces a simple signal column that the Oracle can evaluate
    in isolation to measure individual alpha ceilings.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique signal identifier (e.g., 'kalman_wyckoff', 'bos_choch')."""

    @abstractmethod
    def generate(self, ohlc: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
        """
        Generate signals from OHLCV data.

        Args:
            ohlc: DataFrame with canonical columns (open, high, low, close, volume)
                  and DatetimeIndex UTC.
            context: Optional dict with extra data (flow features, macro, etc.)

        Returns:
            DataFrame with at minimum a 'signal' column:
              1 = long, -1 = short, 0 = flat/no signal.
            May include additional columns like 'confidence' (0-1).
        """

    @abstractmethod
    def required_context(self) -> list[str]:
        """
        List of context keys this signal needs beyond OHLCV.
        Returns empty list if only price data is needed.

        Examples: ['uw_flow_features', 'vix'], ['smc_structure']
        """
