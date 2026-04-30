"""
Trade Journal Port — Interface for trade persistence.

Domain Use Cases depend on this ABC, never on concrete storage (MongoDB, Postgres, etc.).
Implementations: MongoTradeJournalAdapter (infrastructure/)
"""
from abc import ABC, abstractmethod
from typing import Optional

from backend.modules.execution.domain.entities.trade_record import TradeJournalEntry


class TradeJournalPort(ABC):
    """Interface for trade journal persistence."""

    @abstractmethod
    def open_trade(self, entry: TradeJournalEntry) -> str:
        """Register a new trade entry. Returns trade_id."""
        ...

    @abstractmethod
    def close_trade(self, entry: TradeJournalEntry) -> None:
        """Update a trade entry with exit data."""
        ...

    @abstractmethod
    def get_open_trades(self) -> list[dict]:
        """Return all currently open trades."""
        ...

    @abstractmethod
    def get_trade_full_data(self, trade_id: str) -> Optional[dict]:
        """Return the complete document for a trade by ID."""
        ...

    @abstractmethod
    def get_performance_summary(self) -> dict:
        """Return performance summary of all closed trades."""
        ...

    @abstractmethod
    def get_pattern_stats(self) -> list[dict]:
        """Return pattern statistics for learning."""
        ...

    @abstractmethod
    def get_exit_reason_stats(self) -> list[dict]:
        """Return statistics grouped by exit reason."""
        ...

    @abstractmethod
    def find_similar_trades(self, vector: list[float], limit: int = 5) -> list[dict]:
        """Find historically similar trades via vector search."""
        ...
