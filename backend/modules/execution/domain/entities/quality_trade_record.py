"""
Quality Trade Record — Druckenmiller/Hohn Department
======================================================
Structural value positions (18-24 months).
Tracks: Thesis integrity, moat type, ROIC/margin trajectory,
surveillance audit trail, IRR, dividends.
No mechanical stops — exits via THESIS_DEATH or REDUCE_ZONE only.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QualityTradeRecord:
    """Trade record para el departamento QUALITY (Druckenmiller/Hohn)."""

    # ─── IDENTIDAD ───
    trade_id: str
    ticker: str
    direction: str  # LONG
    created_at: str = ""
    status: str = "OPEN"
    strategy_bucket: str = "QUALITY"
    sector: str = "UNKNOWN"

    # ─── ENTRY ───
    entry_price: float = 0.0
    entry_time: str = ""
    entry_shares: float = 0.0
    entry_notional: float = 0.0
    entry_order_id: str = ""
    entry_fill_price: float = 0.0
    entry_slippage: float = 0.0

    # ─── TESIS FUNDAMENTAL (Hohn: tollkeeper moat) ───
    entry_thesis: str = ""
    moat_type: str = ""  # network_effects, switching_costs, intangible_assets, cost_advantage
    thesis_alive: bool = True
    thesis_death_flag: bool = False
    thesis_death_reason: str = ""

    # ─── FUNDAMENTALES AL ENTRAR (Munger: ROIC > WACC) ───
    entry_roic: float = 0.0
    entry_operating_margin: float = 0.0
    entry_gf_value: float = 0.0  # GuruFocus intrinsic value

    # ─── ZONA DE REDUCCIÓN (Druckenmiller: parcial en valuación extrema) ───
    reduce_zone: float = 0.0
    scaling_events: list = field(default_factory=list)  # [{type: "ADD"|"REDUCE", price, date, reason}]

    # ─── SURVEILLANCE HISTORY — trail de auditorías del moat ───
    surveillance_log: list = field(default_factory=list)  # [{date, margin_ttm, capex_ratio, verdict}]

    # ─── PRE-TRADE SIGNALS ───
    alpha_score: float = 0.0
    qualifier_grade: str = ""
    rs_vs_spy: float = 0.0
    insider_signal: str = ""
    sector_alignment: str = ""
    entry_kelly_pct: float = 0.0
    entry_portfolio_pct: float = 0.0

    # ─── SNAPSHOTS ───
    entry_snapshot: Optional[dict] = None
    exit_snapshot: Optional[dict] = None
    entry_intelligence: Optional[dict] = None

    # ─── EVOLUTION ───
    highest_price: float = 0.0
    lowest_price: float = 0.0

    # ─── TOTAL RETURN (dividendo + apreciación) ───
    dividends_collected: float = 0.0
    irr: float = 0.0  # Internal Rate of Return

    # ─── EXIT — solo 2 razones válidas ───
    exit_price: float = 0.0
    exit_time: str = ""
    exit_reason: str = ""  # THESIS_DEATH, REDUCE_ZONE_REACHED
    exit_order_id: str = ""
    exit_fill_price: float = 0.0
    exit_slippage: float = 0.0

    # ─── POST-TRADE RESULTS ───
    pnl_dollars: float = 0.0
    pnl_pct: float = 0.0
    was_winner: bool = False

    # ─── POST-MORTEM FUNDAMENTAL ───
    what_went_right: str = ""
    what_went_wrong: str = ""
    lesson_learned: str = ""
