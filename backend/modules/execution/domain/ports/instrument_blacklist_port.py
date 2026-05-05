"""
Instrument Blacklist Port — Interface for ticker blacklisting.

Used by SurveillanceLoop to blacklist tickers after THESIS_DEATH (4Q cooldown)
and by EntryHub to block re-entry into blacklisted instruments.
"""
from abc import ABC, abstractmethod


class InstrumentBlacklistPort(ABC):
    """Interface for department-scoped instrument blacklisting."""

    @abstractmethod
    def blacklist(
        self, ticker: str, department: str, reason: str, quarters: int = 4
    ) -> None:
        """Blacklist a ticker for N quarters in the given department."""
        ...

    @abstractmethod
    def is_blacklisted(self, ticker: str, department: str) -> bool:
        """Check if a ticker is currently blacklisted for a department."""
        ...

    @abstractmethod
    def get_blacklist(self, department: str) -> list[dict]:
        """Return all currently active blacklisted instruments for a department."""
        ...
