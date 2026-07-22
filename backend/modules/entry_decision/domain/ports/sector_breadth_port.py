"""
Sector Breadth Data Port — Interface for sector breadth (S5) data.

The QualityEntryGate depends on this ABC, never on concrete fetchers.
Implementation: VaultSectorBreadthAdapter (infrastructure/)
"""
from abc import ABC, abstractmethod
from typing import Optional


class SectorBreadthDataPort(ABC):
    """Interface for reading sector breadth (S5) data from the Vault."""

    @abstractmethod
    def get_sector_for_ticker(self, ticker: str) -> Optional[str]:
        """
        Returns sector ETF symbol (e.g. 'XLK') for a given ticker.
        Returns None if ticker's sector is unknown.
        """
        ...

    @abstractmethod
    def get_s5_fi_value(self, sector_etf: str) -> Optional[float]:
        """Returns latest S5_FI (% above 50-DMA) for a sector ETF."""
        ...

    @abstractmethod
    def get_s5_th_value(self, sector_etf: str) -> Optional[float]:
        """Returns latest S5_TH (% above 200-DMA) for a sector ETF."""
        ...

    @abstractmethod
    def get_s5_tw_value(self, sector_etf: str) -> Optional[float]:
        """Returns latest S5_TW (% above 20-DMA) for a sector ETF."""
        ...

    @abstractmethod
    def get_s5_tw_prev_value(self, sector_etf: str) -> Optional[float]:
        """Returns previous day's S5_TW (% above 20-DMA) for a sector ETF."""
        ...


    @abstractmethod
    def get_market_s5_fi(self) -> Optional[float]:
        """Returns latest S5FI for the overall market (SPY)."""
        ...

    @abstractmethod
    def get_s5_fi_history(self, ticker: str, lookback: int = 10) -> list[float]:
        """
        Returns last N daily close values of S5_FI for RoC calculation.
        ticker can be a sector breadth ticker (S5_XLK_FI) or 'S5FI' for market.
        Returns empty list if data unavailable.
        """
        ...

    @abstractmethod
    def is_etf_above_ma200(self, sector_etf: str) -> bool:
        """Returns True if the sector ETF price is above its 200-DMA."""
        ...

    @abstractmethod
    def get_sector_tier(self, sector_etf: str) -> int:
        """
        Returns tier for S5 threshold calibration.
        1 = Defensive (XLP, XLV, XLU, XLRE, XLB) — tighter thresholds
        2 = Mixed (XLE, XLF, XLC)
        3 = Cyclical (XLK, XLY, XLI) — wider thresholds
        """
        ...

    # ── S5V (Volume Breadth) ────────────────────────────────

    @abstractmethod
    def get_sv5_fi_value(self, sector_etf: str) -> Optional[float]:
        """Returns latest SV5_FI (% with vol above 50-DMA) for a sector ETF."""
        ...

    @abstractmethod
    def get_sv5_th_value(self, sector_etf: str) -> Optional[float]:
        """Returns latest SV5_TH (% with vol above 200-DMA) for a sector ETF."""
        ...

    @abstractmethod
    def get_sv5_tw_value(self, sector_etf: str) -> Optional[float]:
        """Returns latest SV5_TW (% with vol above 20-DMA) for a sector ETF."""
        ...

    @abstractmethod
    def get_sv5_tw_prev_value(self, sector_etf: str) -> Optional[float]:
        """Returns previous day's SV5_TW for direction detection."""
        ...

    @abstractmethod
    def get_market_sv5_fi(self) -> Optional[float]:
        """Returns latest SV5_FI for the overall market (SPY)."""
        ...

    # ── Multi-scale history (for velocity / acceleration) ───

    @abstractmethod
    def get_s5_history_by_scale(
        self, sector_etf: str, scale: str, lookback: int = 25,
    ) -> list[float]:
        """
        Returns last N daily close values of S5 for a given scale.
        scale: 'structural' | 'intermediate' | 'tactical'.
        Returns empty list if data unavailable.
        """
        ...

