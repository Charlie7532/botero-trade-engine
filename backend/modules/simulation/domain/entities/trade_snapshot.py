"""
Trade Snapshot — Immutable Pre-Trade Context Record
=====================================================
Captures the complete state of indicators, market structure, flow,
macro context, and signal evaluations at the exact moment of trade
entry. This is the forensic record used by TradeAutopsy and
IndicatorAnalyzer for feedback loops and ML retraining.

Persistence: vault/snapshots/{yyyy-mm}/{id}.json — IMMUTABLE, never modified.
"""
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional
import uuid


@dataclass
class MarketStructureSnapshot:
    """SMC (Smart Money Concepts) state at entry."""
    swing_trend: str = "UNKNOWN"          # UPTREND, DOWNTREND, RANGING
    bos_direction: str = "NONE"           # BULLISH, BEARISH, NONE
    bos_bars_ago: int = 999               # How recent was the BOS
    choch_detected: bool = False          # Change of Character present
    choch_direction: str = "NONE"         # BULLISH, BEARISH
    nearest_ob_price: float = 0.0         # Nearest Order Block level
    nearest_ob_type: str = "NONE"         # BULLISH, BEARISH
    fvg_active: bool = False              # Fair Value Gap present
    fvg_direction: str = "NONE"           # BULLISH, BEARISH
    liquidity_swept: bool = False         # Recent liquidity sweep detected


@dataclass
class SignalSnapshot:
    """Individual signal evaluation at entry."""
    name: str                # Signal module name
    value: int = 0           # Signal output: 1=long, -1=short, 0=flat
    confidence: float = 0.0  # Signal-specific confidence (0-1)
    weight: float = 0.0      # Weight from StrategyProfile
    contribution: float = 0.0  # value * weight (actual contribution to composite)


@dataclass
class TradeSnapshot:
    """
    Complete immutable context at trade entry.

    This captures EVERYTHING the system knew when the trade was taken,
    enabling:
    - Post-mortem analysis (what did the indicators say?)
    - Indicator precision ranking (which signals predicted correctly?)
    - ML retraining with exact historical context
    """
    # ── Identity ────────────────────────────────────────────
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ticker: str = ""
    category: str = ""        # InvestmentCategory.value
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    # ── Entry Intelligence Report (40+ indicators) ─────────
    entry_report: dict = field(default_factory=dict)  # EntryIntelligenceReport.to_dict()

    # ── Market Structure (SMC) ────────────────────────────
    structure: MarketStructureSnapshot = field(default_factory=MarketStructureSnapshot)

    # ── Signal Evaluations ────────────────────────────────
    signals: list[SignalSnapshot] = field(default_factory=list)
    composite_score: float = 0.0       # Final weighted combination
    composite_method: str = ""         # "weighted_vote", "unanimous", "majority"

    # ── Oracle & ML Gates ─────────────────────────────────
    oracle_ceiling_sharpe: float = 0.0   # Alpha ceiling from Oracle
    ml_confidence: float = 0.0           # ML model confidence score
    ml_model_used: str = ""              # "xgboost", "lstm", "ensemble"

    # ── Macro Context ─────────────────────────────────────
    vix: float = 0.0
    vix_regime: str = "UNKNOWN"          # FEAR, COMPLACENT, NORMAL
    yield_spread: float = 0.0
    yield_curve_inverted: bool = False
    macro_regime: str = "UNKNOWN"        # EXPANSION, CONTRACTION, etc.
    spy_signal: str = "NEUTRAL"          # SPY MacroGate signal
    sentiment_regime: str = "NEUTRAL"    # BULL, NEUTRAL, BEAR

    # ── Flow Context ──────────────────────────────────────
    flow_score: float = 0.0
    flow_persistence_grade: str = "UNKNOWN"
    sweep_count: int = 0
    darkpool_premium: float = 0.0

    # ── Fundamental Context ───────────────────────────────
    qgarp_score: float = 0.0
    piotroski_f_score: int = 0
    insider_conviction: float = 0.0

    # ── Strategy Profile Used ─────────────────────────────
    profile_calibrated_at: Optional[str] = None
    profile_geometry: dict = field(default_factory=dict)
    adaptive_params: dict = field(default_factory=dict)

    # ── Pre-Trade Gate Decision ───────────────────────────
    gate_approved: bool = False
    gate_reason: str = ""
    gate_conviction: float = 0.0   # 0-1 overall conviction

    # ── Trade Outcome (filled post-trade by TradeAutopsy) ─
    outcome_pnl_pct: Optional[float] = None
    outcome_was_winner: Optional[bool] = None
    outcome_exit_reason: Optional[str] = None
    outcome_mfe_pct: Optional[float] = None
    outcome_mae_pct: Optional[float] = None

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)
