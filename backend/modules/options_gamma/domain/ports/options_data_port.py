"""
Options Data Port — Interface for options chain data providers.

The domain Use Cases depend on this ABC, never on concrete adapters.
Implementations: YFinanceOptionsAdapter (infrastructure/)
"""
from abc import ABC, abstractmethod
from typing import Optional


class OptionsDataPort(ABC):
    """Interface for accessing options chain data."""

    @abstractmethod
    def get_options_chain(self, symbol: str, expiration: Optional[str] = None) -> dict:
        """
        Fetch the full options chain for a symbol.

        Returns:
            dict with 'calls' and 'puts' DataFrames/lists.
        """
        ...

    @abstractmethod
    def get_expirations(self, symbol: str) -> list[str]:
        """Get available expiration dates for the symbol."""
        ...

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        """Get the current market price for the underlying."""
        ...
