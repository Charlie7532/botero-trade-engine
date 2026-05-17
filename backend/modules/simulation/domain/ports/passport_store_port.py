"""
Passport Store Port — Interface for Signal Passport persistence.

Separate from MLDataPort to keep concerns clean:
  - MLDataPort: raw ML feature/label pairs (ml_features, ml_labels)
  - PassportStorePort: enriched departmental reliability passports
"""
import abc
from typing import Optional

from backend.modules.simulation.domain.entities.signal_passport import SignalPassport


class PassportStorePort(abc.ABC):
    """Interface for persisting and loading Signal Reliability Passports."""

    @abc.abstractmethod
    def save_passport(self, passport: SignalPassport) -> None:
        """Upsert a passport. Key: (ticker, department, signal_name)."""
        ...

    @abc.abstractmethod
    def load_passport(
        self,
        ticker: str,
        department: str,
        signal_name: str,
    ) -> Optional[SignalPassport]:
        """Load a single passport. Returns None if not found."""
        ...

    @abc.abstractmethod
    def load_passports_for_ticker(
        self,
        ticker: str,
        department: str,
    ) -> list[SignalPassport]:
        """Load all passports for a ticker × department, sorted by reliability_score desc."""
        ...

    @abc.abstractmethod
    def load_viable_passports(
        self,
        department: str,
    ) -> list[SignalPassport]:
        """Load all viable passports for a department across all tickers."""
        ...
