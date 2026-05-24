"""
TickerProfilePort — Domain Port for Per-Ticker Calibrated Profiles
=====================================================================
ABC defining the contract for storing/loading TickerProfile data.
Consumed by SwingGate, Unified Pre-Trainer, and RSIIntelligence.

Clean Architecture: Domain layer. No infrastructure dependencies.
"""
import abc
from typing import Optional

from backend.modules.shared.domain.entities.ticker_profile import TickerProfile


class TickerProfilePort(abc.ABC):
    """Port for persisting and querying per-ticker calibrated profiles."""

    @abc.abstractmethod
    def load_profile(self, ticker: str) -> Optional[TickerProfile]:
        """Load the calibrated profile for a ticker.

        Returns None if no profile has been trained for this ticker.
        """
        ...

    @abc.abstractmethod
    def save_profile(self, profile: TickerProfile) -> None:
        """Save or update a ticker's calibrated profile."""
        ...

    @abc.abstractmethod
    def load_all_profiles(self) -> list[TickerProfile]:
        """Load all trained profiles. Used by batch operations."""
        ...

    @abc.abstractmethod
    def delete_profile(self, ticker: str) -> bool:
        """Delete a profile. Returns True if existed."""
        ...
