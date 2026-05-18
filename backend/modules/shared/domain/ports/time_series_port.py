"""
Time-Series Port — OHLCV, Macro, MCP Snapshots
=================================================
Abstract interface for time-series data operations.
Replaces HistoricalDataPort with a cleaner separation:
- Time-series data (OHLCV, macro, MCP) → this port
- Trading state (instruments, regimes) → TradingStatePort

Implementor: TimescaleDataStore
"""
from abc import ABC, abstractmethod
from datetime import date
from typing import Optional, Any

import pandas as pd


class TimeSeriesPort(ABC):
    """Port for all time-series data operations."""

    # ── OHLCV Bars ────────────────────────────────────────

    @abstractmethod
    def save_bars(self, ticker: str, tf: str, df: pd.DataFrame) -> None:
        """Append-only save of OHLCV data. Deduplicates by (ticker, timeframe, time)."""

    @abstractmethod
    def load_bars(
        self, ticker: str, tf: str,
        start: Optional[date] = None, end: Optional[date] = None,
    ) -> pd.DataFrame:
        """Load OHLCV bars, optionally filtered by date range."""

    @abstractmethod
    def bars_last_date(self, ticker: str, tf: str) -> Optional[date]:
        """Return the last available date for incremental downloads."""

    # ── Macro Data (DEPRECATED — use save_bars/load_bars per Rule 14) ──

    @abstractmethod
    def save_macro(self, name: str, df: pd.DataFrame) -> None:
        """DEPRECATED: Use save_bars() with INDICATOR ticker instead. Will be removed."""

    @abstractmethod
    def load_macro(self, name: str) -> Optional[pd.DataFrame]:
        """DEPRECATED: Use load_bars() with INDICATOR ticker instead. Will be removed."""

    # ── MCP Snapshots ─────────────────────────────────────

    @abstractmethod
    def save_mcp_snapshot(self, category: str, ticker: str, data: Any) -> None:
        """Save raw MCP data as JSONB. Timestamp auto-set to NOW()."""

    @abstractmethod
    def load_mcp_snapshot(self, category: str, ticker: str, dt: str) -> Optional[Any]:
        """Load single MCP snapshot for a specific date."""

    @abstractmethod
    def load_mcp_latest(self, category: str, ticker: str) -> Optional[Any]:
        """Load the most recent MCP snapshot regardless of date."""

    @abstractmethod
    def load_mcp_range(
        self, category: str, ticker: str,
        start: str, end: str,
    ) -> list[tuple[str, Any]]:
        """Load MCP snapshots for a date range. Returns [(date_str, data), ...]."""
