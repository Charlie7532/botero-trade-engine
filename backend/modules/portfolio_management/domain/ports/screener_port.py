"""
Screener Port — Interface for stock screening providers.

Implementations: FinvizIntelligence (infrastructure/)
"""
from abc import ABC, abstractmethod


class ScreenerPort(ABC):
    """Interface for stock screening services."""

    @abstractmethod
    def screen_tickers(self, filters: dict) -> list[dict]:
        """
        Screen tickers matching the given filter criteria.

        Args:
            filters: Dict of screening parameters (sector, market_cap, etc.)

        Returns:
            List of ticker dicts with screening data.
        """
        ...

    @abstractmethod
    def get_sector_performance(self) -> dict:
        """Get current sector performance data."""
        ...
