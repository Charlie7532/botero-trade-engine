"""
Instrument Repository Port — Interface for instrument and calibration persistence.

Implementations:
    - PayloadInstrumentsAdapter (infrastructure/payload_instruments_adapter.py)

All CRUD operations go through Payload CMS REST API → PostgreSQL.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class InstrumentRecord:
    """Domain-level instrument representation."""
    id: Optional[str] = None
    ticker: str = ""
    name: str = ""
    instrument_type: str = "stock"
    gics_sector: str = ""
    universe: str = "sp500"
    is_active: bool = True
    last_fundamentals: Optional[dict] = None
    fundamentals_updated_at: Optional[datetime] = None
    next_earnings_date: Optional[datetime] = None


@dataclass
class RegimePhaseRecord:
    """Domain-level regime phase representation."""
    id: Optional[str] = None
    instrument_id: str = ""
    level: str = "market"  # market | sector | instrument
    phase: str = "accumulation"  # accumulation | markup | distribution | markdown
    detected_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    trigger_signal: str = ""
    vix_at_detection: float = 0.0
    breadth_at_detection: float = 0.0


@dataclass
class CalibrationRecord:
    """Domain-level calibration profile representation."""
    id: Optional[str] = None
    instrument_id: str = ""
    category: str = "core_hohn"
    market_regime_id: Optional[str] = None
    sector_regime_id: Optional[str] = None
    instrument_regime_id: Optional[str] = None
    signals: list = None
    composite_sharpe: float = 0.0
    win_rate: float = 0.0
    status: str = "active"
    warm_start_from_id: Optional[str] = None
    warm_start_delta: Optional[dict] = None

    def __post_init__(self):
        if self.signals is None:
            self.signals = []


class InstrumentRepoPort(ABC):
    """Port for instrument and lifecycle persistence via Payload REST API."""

    # ─── Instruments ─────────────────────────────────────────
    @abstractmethod
    def get_instrument(self, ticker: str) -> Optional[InstrumentRecord]:
        """Get instrument by ticker."""
        ...

    @abstractmethod
    def upsert_instrument(self, record: InstrumentRecord) -> InstrumentRecord:
        """Create or update an instrument."""
        ...

    @abstractmethod
    def list_instruments(self, universe: str = None, active_only: bool = True) -> list[InstrumentRecord]:
        """List instruments, optionally filtered by universe."""
        ...

    # ─── Regime Phases ──────────────────────────────────────
    @abstractmethod
    def get_active_regime(self, instrument_id: str, level: str) -> Optional[RegimePhaseRecord]:
        """Get the currently active regime phase for an instrument at a given level."""
        ...

    @abstractmethod
    def create_regime_phase(self, record: RegimePhaseRecord) -> RegimePhaseRecord:
        """Create a new regime phase (also closes the previous one)."""
        ...

    @abstractmethod
    def close_regime_phase(self, phase_id: str, closed_at: datetime) -> None:
        """Close a regime phase by setting closedAt and calculating duration."""
        ...

    # ─── Calibration Profiles ───────────────────────────────
    @abstractmethod
    def get_active_calibration(self, instrument_id: str, category: str) -> Optional[CalibrationRecord]:
        """Get active calibration for an instrument and category."""
        ...

    @abstractmethod
    def create_calibration(self, record: CalibrationRecord) -> CalibrationRecord:
        """Create a new calibration profile."""
        ...

    @abstractmethod
    def invalidate_calibrations(
        self, instrument_id: str, invalidated_by_regime_id: str
    ) -> int:
        """Invalidate all active calibrations for an instrument. Returns count invalidated."""
        ...

    @abstractmethod
    def find_historical_calibration(
        self, instrument_id: str, market_phase: str, sector_phase: str
    ) -> Optional[CalibrationRecord]:
        """
        Find the best historical calibration for warm-start.

        Looks for previous calibrations trained under similar regime conditions
        (same market phase + sector phase combo).
        """
        ...
