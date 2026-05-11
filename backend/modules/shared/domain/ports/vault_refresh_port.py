"""
Vault Refresh Port — Domain Interface
=========================================
Modules call this when they detect stale or missing data in the vault.
The request goes into a queue — the module NEVER fetches data from
external sources directly.

Implementor: VaultRefreshAdapter (infrastructure)
Consumer: VaultProvider drain loop (daemon/API)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class RefreshRequest:
    """A request for the vault to refresh specific data."""
    ticker: str
    category: str  # 'ohlcv', 'fundamental', 'flow', 'options', 'breadth', 'macro'
    priority: str = "normal"  # 'urgent', 'normal', 'low'
    requested_by: str = "unknown"


@dataclass
class RefreshStatus:
    """Status of a refresh request."""
    request_id: int
    ticker: str
    category: str
    status: str  # 'pending', 'processing', 'done', 'failed'
    requested_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class VaultRefreshPort(ABC):
    """Port for requesting data refresh from the vault.

    Modules call this when they detect stale or missing data.
    The request goes into a queue — the module NEVER fetches
    data from external sources directly.

    Categories:
        ohlcv       — OHLCV bars for stocks/ETFs
        fundamental — GuruFocus fundamentals
        flow        — Unusual Whales / Finnhub flow data
        options     — Options chains (yfinance)
        breadth     — S5TH / S5TW / S5FI recalculation
        macro       — FRED, market indices, CBOE
    """

    @abstractmethod
    def request_refresh(self, request: RefreshRequest) -> int:
        """Enqueue a refresh request. Returns request_id."""

    @abstractmethod
    def check_freshness(
        self, ticker: str, category: str, max_age_hours: int = 24,
    ) -> bool:
        """Check if data for ticker/category was updated within max_age_hours."""

    @abstractmethod
    def pending_requests(self, limit: int = 50) -> list[RefreshStatus]:
        """Get pending requests ordered by priority then time."""
""",
<parameter name="Description">Domain port for vault refresh requests. Modules use this to signal that data is stale without breaking the vault-first rule."
