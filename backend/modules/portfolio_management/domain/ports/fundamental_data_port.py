"""
Fundamental Data Port — Interface for fundamental analysis data providers.

Implementations: GuruFocusIntelligence, FinnhubIntelligence (infrastructure/)
"""
from abc import ABC, abstractmethod
from typing import Optional


class FundamentalDataPort(ABC):
    """Interface for fetching fundamental analysis data."""

    @abstractmethod
    def get_guru_analysis(self, ticker: str) -> dict:
        """
        Fetch guru/institutional analysis for a ticker.

        Returns:
            Dict with QGARP score, valuation metrics, guru positions.
        """
        ...

    @abstractmethod
    def get_insider_activity(self, ticker: str) -> dict:
        """
        Fetch insider buying/selling activity.

        Returns:
            Dict with insider transactions, net sentiment.
        """
        ...

    @abstractmethod
    def get_earnings_calendar(self, ticker: str) -> Optional[dict]:
        """
        Fetch upcoming earnings date and estimates.

        Returns:
            Dict with earnings date, EPS estimates, or None.
        """
        ...

    @abstractmethod
    def get_financial_summary(self, ticker: str) -> dict:
        """
        Fetch key financial metrics (P/E, revenue growth, margins, etc.)

        Returns:
            Dict with financial summary data.
        """
        ...
