"""
Historical Data Port — Vault Access Interface
================================================
Abstract interface for reading/writing OHLCV data, raw MCP JSON,
harmonized features, strategy profiles, and trade snapshots.

Implementor: ParquetDataStore (Phase 2)
"""
from abc import ABC, abstractmethod
from datetime import date
from typing import Optional, Any

import pandas as pd


class HistoricalDataPort(ABC):
    """Port for all vault data operations."""

    # ── OHLCV Bars (Parquet) ──────────────────────────────

    @abstractmethod
    def save_bars(self, ticker: str, tf: str, df: pd.DataFrame) -> None:
        """Append-only save of OHLCV data. Deduplicates by timestamp."""

    @abstractmethod
    def load_bars(
        self, ticker: str, tf: str,
        start: Optional[date] = None, end: Optional[date] = None,
    ) -> pd.DataFrame:
        """Load OHLCV bars, optionally filtered by date range."""

    @abstractmethod
    def bars_last_date(self, ticker: str, tf: str) -> Optional[date]:
        """Return the last available date for incremental downloads."""

    # ── Raw MCP JSON (UW, GuruFocus, etc.) ────────────────

    @abstractmethod
    def vault_json(self, category: str, key: str, dt: str, data: Any) -> None:
        """
        Save raw JSON to vault. Immutable: if file exists, skip.
        Example: vault_json("flow/alerts", "NVDA", "2026-04-28", alerts_list)
        """

    @abstractmethod
    def load_json(self, category: str, key: str, dt: str) -> Optional[Any]:
        """Load a single JSON file from the vault."""

    @abstractmethod
    def load_json_range(
        self, category: str, key: str,
        start: str, end: str,
    ) -> list[tuple[str, Any]]:
        """Load JSON files for a date range. Returns [(date, data), ...]."""

    # ── Harmonized Features (Parquet) ─────────────────────

    @abstractmethod
    def save_features(self, ticker: str, feature_set: str, df: pd.DataFrame) -> None:
        """Save harmonized feature DataFrame. Overwrites (regenerable from raw)."""

    @abstractmethod
    def load_features(self, ticker: str, feature_set: str) -> Optional[pd.DataFrame]:
        """Load harmonized features. Returns None if not yet generated."""

    # ── Strategy Profiles ─────────────────────────────────

    @abstractmethod
    def save_profile(self, profile: Any) -> None:
        """Save StrategyProfile. Archives previous version."""

    @abstractmethod
    def load_profile(self, category: str, ticker: str) -> Optional[Any]:
        """Load latest StrategyProfile for category × ticker."""

    # ── Trade Snapshots ───────────────────────────────────

    @abstractmethod
    def save_snapshot(self, snapshot: Any) -> None:
        """Save TradeSnapshot. Immutable: append-only."""

    @abstractmethod
    def load_snapshots(
        self, ticker: Optional[str] = None,
        category: Optional[str] = None,
        start: Optional[str] = None, end: Optional[str] = None,
    ) -> list[Any]:
        """Query trade snapshots by ticker, category, and/or date range."""
