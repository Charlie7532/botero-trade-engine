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

    @abstractmethod
    def get_financial_statements(self, ticker: str, period_type: str = "annual") -> dict:
        """Fetch Income + Balance + Cash Flow statements."""
        ...

    @abstractmethod
    def get_growth_profile(self, ticker: str) -> dict:
        """Fetch CAGR growth rates (1/3/5/10yr)."""
        ...

    @abstractmethod
    def get_operating_kpis(self, ticker: str) -> dict:
        """Fetch SaaS/Operating metrics (ARPU, NRR, etc)."""
        ...

    @abstractmethod
    def get_segment_breakdown(self, ticker: str) -> dict:
        """Fetch revenue by business segment and geography."""
        ...

    @abstractmethod
    def get_wacc(self, ticker: str) -> float:
        """Fetch Weighted Average Cost of Capital."""
        ...

    @abstractmethod
    def get_full_qgarp(self, ticker: str) -> dict:
        """Fetch complete QGARP with Rule #1 valuations + moat areas."""
        ...

    @abstractmethod
    def get_warning_signs(self, ticker: str) -> dict:
        """Fetch good signs + warning signs (from summary company_data)."""
        ...
