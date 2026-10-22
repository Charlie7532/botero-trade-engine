"""
QUALITY ENTRY GATE PORT — CLEAN ARCHITECTURE PORT
=================================================
Clean Architecture: Domain Layer (Ports)
Module: entry_decision / domain / ports

Formal abstract port defining the contract for Quality Entry & Rotation Gate:
  - Regime evaluation across S5/SV5 multi-scale breadth.
  - Sector portfolio weight calculation.
  - Single-ticker evaluation adapter for orchestrator consumption.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class QualityEntryGatePort(ABC):
    """
    Abstract Port for Quality Entry & Sector Rotation Gate.
    Enforces hexagonal boundary: use cases and orchestrators depend on this ABC.
    """

    @abstractmethod
    def evaluate_regime(
        self,
        th: float,
        fi: float,
        tw: float,
        v_th: float,
        v_fi: float,
        v_tw: float,
        sec_th: Dict[str, float],
        sec_fi: Dict[str, float],
        sec_tw: Dict[str, float],
        sec_v_tw: Optional[Dict[str, float]] = None,
        fi_velocity: float = 0.0,
        current_mode: str = "NORMAL",
        days_in_mode: int = 25,
        tw_prev: Optional[float] = None,
        fgbi: Optional[float] = None,
        vbi: Optional[float] = None,
        fgbi_peak_15d: Optional[float] = None,
        vix: Optional[float] = None,
        sv5_turbulence: Optional[float] = None,
        sv5_shock: Optional[float] = None,
    ) -> str:
        """Classify the current market regime from breadth and volume telemetry."""
        pass

    @abstractmethod
    def calculate_target_weights(
        self,
        mode: str,
        sec_th: Dict[str, float],
        sec_fi: Dict[str, float],
        sec_tw: Dict[str, float],
        avail_sectors: List[str],
        sec_v_fi: Optional[Dict[str, float]] = None,
        sec_v_tw: Optional[Dict[str, float]] = None,
        rs_roc_5d: Optional[Dict[str, float]] = None,
        sec_stage4: Optional[Dict[str, bool]] = None,
        rs_roc_50d: Optional[Dict[str, float]] = None,
        rs_roc_20d: Optional[Dict[str, float]] = None,
        s5cap_fi: Optional[Dict[str, float]] = None,
        sec_vbi: Optional[Dict[str, float]] = None,
        sv5_turbulence: Optional[float] = None,
        sv5_shock: Optional[float] = None,
        vix: Optional[float] = None,
    ) -> Dict[str, float]:
        """Calculate sector target weights based on active regime and sector conviction."""
        pass

    @abstractmethod
    def evaluate(self, ticker: str, **kwargs: Any) -> Any:
        """Evaluate a specific ticker for Quality Department admission."""
        pass
