"""
Trading State Port — Operational State Access
================================================
Abstract interface for reading/writing operational trading state
that lives in the Payload CMS schema (PostgreSQL).

Read path: Direct SQL to payload.* (fast, bulk operations)
Write path: REST API to Payload (preserves lifecycle hooks)

Implementor: PostgresTradingState
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class InstrumentRecord:
    """Instrument from the Payload instruments collection."""
    id: int
    ticker: str
    name: str
    sector: str
    instrument_type: str


class TradingStatePort(ABC):
    """Port for operational trading state from Payload CMS."""

    # ── Reads (high-volume, bulk — direct SQL) ───────────

    @abstractmethod
    def get_instrument_universe(self) -> list[InstrumentRecord]:
        """Load all active instruments. ~528 rows."""

    @abstractmethod
    def get_active_regime(self) -> Optional[dict]:
        """Get the current active market regime phase."""

    @abstractmethod
    def get_calibration_profiles(self, category: str) -> list[dict]:
        """Load active calibration profiles for a category."""

    # ── Writes (low-volume — REST API for lifecycle hooks) ─

    @abstractmethod
    def save_calibration_profile(self, profile: dict) -> str:
        """Save calibration profile via REST. Returns document ID."""

    @abstractmethod
    def save_screening_results(self, results: list[dict]) -> int:
        """Save screening results via REST. Returns count saved."""

    @abstractmethod
    def save_trade_snapshot(self, snapshot: dict) -> str:
        """Save trade snapshot via REST. Returns document ID."""
