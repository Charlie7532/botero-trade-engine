"""
Trade Journal Port — Interface for trade persistence.

Domain Use Cases depend on this ABC, never on concrete storage.
Each department (QUALITY / SPECULATIVE) receives its own instance
scoped to its own table via the JournalRegistry pattern.

Implementations: PostgresTradeJournalAdapter (infrastructure/)
"""
from abc import ABC, abstractmethod
from typing import Any, Optional


class TradeJournalPort(ABC):
    """Interface for trade journal persistence (department-scoped).

    Accepts TradeJournalEntry, SpeculativeTradeRecord, or QualityTradeRecord
    via duck typing (Any) to satisfy Liskov Substitution Principle.
    """

    @abstractmethod
    def open_trade(self, entry: Any) -> str:
        """Register a new trade entry. Returns trade_id."""
        ...

    @abstractmethod
    def close_trade(self, entry: Any) -> None:
        """Update a trade entry with exit data."""
        ...

    @abstractmethod
    def update_trade(self, trade_id: str, fields: dict) -> None:
        """Partial update of trade fields.

        Used by SurveillanceLoop for thesis_death_flag signaling
        and by forensics for post-mortem annotations.
        """
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
