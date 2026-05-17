"""
Swing Data Port — Interface for market data access.

Implementations live in quality_swing/infrastructure/.
"""
from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

import pandas as pd


class SwingDataPort(ABC):
    """Interface for fetching OHLCV data needed by SwingGate."""

    @abstractmethod
    def load_ohlc(
        self,
        ticker: str,
        timeframe: str = "1d",
        start: Optional[date] = None,
    ) -> Optional[pd.DataFrame]:
        """Load OHLCV bars for a ticker.

        Returns DataFrame with columns: open, high, low, close, volume.
        """
        ...

    @abstractmethod
    def load_vol_regime_label(self) -> str:
        """Load current volatility regime label for Quality department.

        Returns one of: NORMAL, COMPLACENT, ELEVATED, CRISIS.
        """
        ...
