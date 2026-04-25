"""
Macro Data Port — Interface for macro-economic data providers.

Implementations: YFinanceMacroAdapter, FREDMacroAdapter (infrastructure/)
"""
from abc import ABC, abstractmethod


class MacroDataPort(ABC):
    """Interface for fetching macro-economic indicators."""

    @abstractmethod
    def fetch_vix(self) -> float:
        """Fetch the current VIX level."""
        ...

    @abstractmethod
    def fetch_yield_spread(self) -> float:
        """Fetch the yield curve spread (e.g., 10Y - 13W)."""
        ...
