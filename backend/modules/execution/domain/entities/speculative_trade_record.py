"""
Speculative Trade Record — Seykota Department
===============================================
Tactical microstructure trades (2-5 days).
Tracks: ATR trailing stops, MFE/MAE, R-multiple, pgvector Memory Guard.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SpeculativeTradeRecord:
    """Trade record para el departamento SPECULATIVE (Seykota)."""

    # ─── IDENTIDAD ───
    trade_id: str
    ticker: str
    direction: str  # LONG, SHORT
    created_at: str = ""
    status: str = "OPEN"
    strategy_bucket: str = "SPECULATIVE"
    sector: str = "UNKNOWN"

    # ─── ENTRY ───
    entry_price: float = 0.0
    entry_time: str = ""
    entry_shares: float = 0.0
    entry_notional: float = 0.0
    entry_order_id: str = ""
    entry_fill_price: float = 0.0
    entry_slippage: float = 0.0
    entry_state: str = "PROBING"

    # ─── PRE-TRADE SIGNALS ───
    alpha_score: float = 0.0
    qualifier_grade: str = ""
    qualifier_edge_score: float = 0.0
    optimal_model: str = ""
    lstm_probability: float = 0.0
    xgb_probability: float = 0.0
    rs_vs_spy: float = 0.0
    rs_vs_sector: float = 0.0
    insider_signal: str = ""
    insider_detail: str = ""
    earnings_safe: bool = True
    earnings_days: int = -1
    sector_alignment: str = ""
    capitulation_level: int = 0
    entry_kelly_pct: float = 0.0
    entry_portfolio_pct: float = 0.0

    # ─── STOPS MECÁNICOS (Seykota: cortar pérdidas sin excepción) ───
    trailing_type: str = "adaptive"
    trailing_atr_mult: float = 3.0
    trailing_fixed_pct: float = 0.10
    initial_stop_price: float = 0.0
    current_stop_price: float = 0.0
    stop_adjustments: list = field(default_factory=list)

    # ─── MFE/MAE — Crítico para calibración de stops ───
    highest_price: float = 0.0
    lowest_price: float = 0.0
    max_favorable_excursion_pct: float = 0.0
    max_adverse_excursion_pct: float = 0.0
    bars_held: int = 0
    scaling_events: list = field(default_factory=list)

    # ─── PATTERN RECOGNITION — microestructura ───
    pattern_tags: list = field(default_factory=list)
    entry_intelligence: Optional[dict] = None  # Full 40-variable snapshot

    # ─── SNAPSHOTS ───
    entry_snapshot: Optional[dict] = None
    exit_snapshot: Optional[dict] = None

    # ─── R-MULTIPLE — la métrica que importa ───
    pnl_r_multiple: float = 0.0

    # ─── EXIT ───
    exit_price: float = 0.0
    exit_time: str = ""
    exit_reason: str = ""  # STOP_HIT, MA20_REVERSION, RS_DECAY, DISTRIBUTION, TIMEOUT
    exit_order_id: str = ""
    exit_fill_price: float = 0.0
    exit_slippage: float = 0.0

    # ─── POST-TRADE RESULTS ───
    pnl_dollars: float = 0.0
    pnl_pct: float = 0.0
    was_winner: bool = False

    # ─── pgvector Memory Guard (9D embedding) ───
    entry_vector: Optional[list] = None

    # ─── POST-MORTEM TÁCTICO ───
    what_went_right: str = ""
    what_went_wrong: str = ""
    lesson_learned: str = ""
    grade: str = ""  # A-F (calidad de ejecución, no solo resultado)
