"""
Strategy Profile — Investment Category Taxonomy & Signal Composition
=====================================================================
Defines the dual-regime architecture (QUALITY/SPECULATIVE) with sub-categories,
Oracle geometry per category, and polymorphic signal composition recipes.

Each StrategyProfile stores ML-discovered weights per signal, enabling
the same modules to produce different strategies via different recipes.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class InvestmentCategory(str, Enum):
    """Dual-regime taxonomy: QUALITY (80%) + SPECULATIVE (20%)."""
    # QUALITY — Hohn & Munger: patience, conviction, fundamental moats
    QUALITY_VALUE = "QUALITY_VALUE"
    QUALITY_GROWTH = "QUALITY_GROWTH"
    QUALITY_DIVIDEND = "QUALITY_DIVIDEND"

    # SPECULATIVE — Eifert & PTJ: speed, asymmetry, microstructure
    SPECULATIVE_SPRING = "SPECULATIVE_SPRING"
    SPECULATIVE_MOMENTUM = "SPECULATIVE_MOMENTUM"
    SPECULATIVE_GAMMA = "SPECULATIVE_GAMMA"
    SPECULATIVE_BREAKOUT = "SPECULATIVE_BREAKOUT"

    @property
    def bucket(self) -> str:
        return "QUALITY" if self.value.startswith("QUALITY") else "SPECULATIVE"

    @property
    def is_quality(self) -> bool:
        return self.bucket == "QUALITY"


@dataclass
class OracleGeometry:
    """Triple Barrier geometry for Oracle Alpha Ceiling evaluation."""
    profit_mult: float    # ATR multiplier for take-profit
    loss_mult: float      # ATR multiplier for stop-loss
    max_bars: int         # Maximum bars before time exit
    vol_lookback: int = 20  # ATR lookback window


# Default Oracle geometries per category
ORACLE_GEOMETRY: dict[InvestmentCategory, OracleGeometry] = {
    # QUALITY: wider barriers, more patience (Hohn & Munger)
    InvestmentCategory.QUALITY_VALUE:    OracleGeometry(profit_mult=3.0, loss_mult=1.0, max_bars=60),
    InvestmentCategory.QUALITY_GROWTH:   OracleGeometry(profit_mult=2.5, loss_mult=1.0, max_bars=45),
    InvestmentCategory.QUALITY_DIVIDEND: OracleGeometry(profit_mult=2.0, loss_mult=0.8, max_bars=90),
    # SPECULATIVE: tighter barriers, faster execution (Eifert & PTJ)
    InvestmentCategory.SPECULATIVE_SPRING:   OracleGeometry(profit_mult=2.0, loss_mult=1.0, max_bars=15),
    InvestmentCategory.SPECULATIVE_MOMENTUM: OracleGeometry(profit_mult=1.5, loss_mult=1.0, max_bars=10),
    InvestmentCategory.SPECULATIVE_GAMMA:    OracleGeometry(profit_mult=1.5, loss_mult=1.5, max_bars=8),
    InvestmentCategory.SPECULATIVE_BREAKOUT: OracleGeometry(profit_mult=2.5, loss_mult=1.0, max_bars=20),
}


@dataclass
class SignalConfig:
    """Configuration for a single signal module within a strategy recipe."""
    name: str                  # Signal identifier (e.g., "kalman_wyckoff")
    weight: float = 0.0       # ML-discovered importance (0.0 - 1.0)
    threshold: float = 0.5    # Minimum confidence to activate
    enabled: bool = True       # Category may disable irrelevant signals
    ceiling_sharpe: float = 0.0  # Oracle ceiling for this signal alone


@dataclass
class GatingCriteria:
    """Minimum performance thresholds for Walk-Forward validation."""
    min_sharpe: float = 0.8
    max_drawdown: float = -20.0
    min_win_rate: float = 45.0
    min_profit_factor: float = 1.3
    min_trades_total: int = 15


@dataclass
class StrategyProfile:
    """
    Complete strategy specification for a ticker × category pair.

    This is the central artifact produced by StrategyCalibrator and consumed
    by the WalkForwardBacktester, StrategyComposer, and PreTradeGate.
    """
    ticker: str
    category: InvestmentCategory
    sector: str = "UNKNOWN"
    timeframe: str = "1d"

    # Oracle geometry (may be customized from defaults during calibration)
    geometry: OracleGeometry = field(default_factory=lambda: OracleGeometry(2.0, 1.0, 30))

    # Walk-Forward gating criteria
    gating: GatingCriteria = field(default_factory=GatingCriteria)

    # Signal composition recipe — ML-discovered weights per module
    signals: list[SignalConfig] = field(default_factory=list)
    composite_method: str = "weighted_vote"  # "weighted_vote" | "unanimous" | "majority"
    min_signals_required: int = 2            # Minimum active signals to enter

    # Adaptive parameters (discovered by calibrator, replaces hardcoded thresholds)
    adaptive_params: dict = field(default_factory=dict)

    # SMC Structure requirements per category
    structure_rules: dict = field(default_factory=dict)

    # Calibration metadata
    calibrated_at: Optional[str] = None
    calibration_sharpe: float = 0.0
    calibration_trades: int = 0
    data_start: Optional[str] = None
    data_end: Optional[str] = None

    @property
    def bucket(self) -> str:
        return self.category.bucket

    @property
    def enabled_signals(self) -> list[SignalConfig]:
        return [s for s in self.signals if s.enabled]

    @property
    def total_weight(self) -> float:
        return sum(s.weight for s in self.enabled_signals)
