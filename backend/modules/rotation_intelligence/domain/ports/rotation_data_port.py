"""
Rotation Data Port — Interface for fetching ETF price/volume data.

Implementations: YahooRotationAdapter (infrastructure/)
"""
from abc import ABC, abstractmethod


class RotationDataPort(ABC):
    """Interface for fetching ETF price and volume data for rotation analysis."""

    @abstractmethod
    def fetch_etf_data(
        self, symbols: list[str], period: str = "3mo"
    ) -> dict[str, dict]:
        """
        Fetch price/volume history for a list of ETFs.

        Args:
            symbols: List of ETF tickers, e.g. ["XLK", "XLE", "SPY"]
            period: Lookback period, e.g. "3mo", "6mo"

        Returns:
            Dict keyed by symbol, each containing:
            {
                "prices": [float, ...],     # Daily close prices, oldest first
                "volumes": [float, ...],    # Daily volumes
                "current": float,           # Latest close
            }
        """
        ...

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Whether this data source is currently available."""
        ...
