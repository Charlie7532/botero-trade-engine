"""
Market Data Port — Interface for market data providers used by entry decisions.

The EntryIntelligenceHub depends on this ABC, never on concrete fetchers.
Implementations: MarketDataFetcher (infrastructure/)
"""
from abc import ABC, abstractmethod

import pandas as pd


class EntryMarketDataPort(ABC):
    """Interface for fetching price data needed by entry evaluation."""

    @abstractmethod
    def fetch_prices(self, ticker: str, period: str = "3mo") -> pd.DataFrame:
        """
        Fetch historical OHLCV data for a ticker.

        Returns:
            DataFrame with Open, High, Low, Close, Volume columns.
        """
        ...

    @abstractmethod
    def fetch_vix(self) -> float:
        """Fetch the current VIX level."""
        ...

    @abstractmethod
    def calc_rs_vs_spy(self, prices: pd.DataFrame) -> float:
        """Calculate relative strength vs SPY."""
        ...
