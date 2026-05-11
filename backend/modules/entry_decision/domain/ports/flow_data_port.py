"""
Flow Data Port — Interface for whale/institutional flow data providers.

The EntryIntelligenceHub depends on this ABC for parsing UW flow data.
Implementations: UnusualWhalesIntelligence (flow_intelligence/infrastructure/)
"""
from abc import ABC, abstractmethod


class FlowDataPort(ABC):
    """Interface for parsing institutional flow data."""

    @abstractmethod
    def parse_spy_macro_gate(self, spy_ticks: list[dict]) -> object:
        """Parse SPY tick data into a macro gate signal."""
        ...

    @abstractmethod
    def parse_market_tide(self, tide_data: list[dict]) -> object:
        """Parse market tide data into a directional signal."""
        ...

    @abstractmethod
    def parse_flow_alerts(self, ticker: str, flow_alerts: list[dict]) -> object:
        """Parse flow alerts for a specific ticker."""
        ...

    @abstractmethod
    def parse_market_sentiment(self, flow_alerts: list[dict]) -> object:
        """Parse overall market sentiment from flow data."""
        ...

    @abstractmethod
    def get_macro_gate(self) -> object:
        """Get SPY macro gate signal from the Vault."""
        ...

    @abstractmethod
    def get_market_tide(self) -> object:
        """Get market tide signal from the Vault."""
        ...

    @abstractmethod
    def get_flow_signal(self, ticker: str) -> object:
        """Get flow signal for a ticker from the Vault."""
        ...

    @abstractmethod
    def get_market_sentiment(self) -> object:
        """Get market sentiment signal from the Vault."""
        ...
