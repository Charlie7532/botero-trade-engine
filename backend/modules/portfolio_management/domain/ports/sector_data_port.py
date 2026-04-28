"""
Sector Data Port — Interface for sector performance and breadth data.

Implementations:
    - SectorFlowEngine (infrastructure/sector_flow_adapter.py)
"""
from abc import ABC, abstractmethod


class SectorDataPort(ABC):
    """Port for sector-level market data."""

    @abstractmethod
    def get_sector_performance(self, mcp_response: dict = None) -> list[dict]:
        """
        Get multi-horizon performance for each GICS sector.

        Returns:
            List of dicts with sector name, 1D/1W/1M/3M/YTD/1Y returns,
            relative volume, and momentum score.
        """
        ...

    @abstractmethod
    def get_sector_breadth(self, mcp_response: dict = None) -> list[dict]:
        """
        Calculate breadth per sector: % of stocks above 50-DMA.

        Returns:
            List of dicts with sector, etf, total_stocks, above_50dma,
            pct_above_50dma, health, and trend.
        """
        ...

    @abstractmethod
    def get_flow_signal(self, etf: str, rel_vol: float, change_pct: float) -> str:
        """
        Classify institutional flow signal for an ETF.

        Returns one of:
            ACCUMULATION_ACTIVE, DISTRIBUTION, HIGH_VOL_CONSOLIDATION,
            WEAK_RALLY, QUIET_DECLINE, CONSOLIDATION
        """
        ...
