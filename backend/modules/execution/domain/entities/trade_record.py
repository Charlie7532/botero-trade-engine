from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional

@dataclass
class MarketSnapshot:
    """Estado completo del mercado al momento de una decisión."""
    timestamp: str
    # Precio
    price: float
    daily_change_pct: float
    distance_from_20sma_pct: float
    distance_from_52w_high_pct: float
    # Volumen
    volume: float
    relative_volume: float
    volume_trend: str  # accumulation, distribution, neutral
    # Técnicos
    atr: float
    atr_pct: float
    rsi_14: float
    macd_signal: str  # bullish, bearish, neutral
    bollinger_position: str  # upper, middle, lower
    # Macro
    vix: float
    spy_daily_change_pct: float
    yield_spread_10y_13w: float
    # Breadth
    s5th_pct: float  # % stocks sobre 200MA
    s5tw_pct: float  # % stocks sobre 20MA
    fear_greed_index: float
    # Sector
    sector: str
    sector_breadth_pct: float
    sector_vs_spy_rs: float
    tide_wave_status: str  # WITH_TIDE, AGAINST_TIDE, etc.


@dataclass
class TradeJournalEntry:
    """Registro completo de un trade, de principio a fin."""
    # ─── IDENTIDAD ───
    trade_id: str
    ticker: str
    direction: str  # LONG, SHORT
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    
    # ─── PRE-TRADE: ¿Por qué entramos? ───
    entry_thesis: str = ""  # Tesis en texto libre
    alpha_score: float = 0.0
    qualifier_grade: str = ""
    qualifier_edge_score: float = 0.0
    optimal_model: str = ""  # lstm, xgboost
    lstm_probability: float = 0.0
    xgb_probability: float = 0.0
    
    # Señales que motivaron la entrada
    rs_vs_spy: float = 0.0
    rs_vs_sector: float = 0.0
    insider_signal: str = ""  # strong_buy, buy, neutral, caution
    insider_detail: str = ""
    earnings_safe: bool = True
    earnings_days: int = -1
    sector_alignment: str = ""  # WITH_TIDE, AGAINST_TIDE
    capitulation_level: int = 0
    
    # ─── MARKET SNAPSHOT AL ENTRAR ───
    entry_snapshot: Optional[dict] = None
    
    # ─── EXECUTION ───
    entry_price: float = 0.0
    entry_time: str = ""
    entry_shares: float = 0.0
    entry_notional: float = 0.0
    entry_kelly_pct: float = 0.0
    entry_portfolio_pct: float = 0.0
    entry_state: str = "PROBING"  # PROBING, SCALING_IN
    entry_order_id: str = ""
    entry_fill_price: float = 0.0
    entry_slippage: float = 0.0  # entry_fill_price - entry_price
    
    # ─── TRAILING STOP CONFIG ───
    trailing_type: str = "adaptive"  # adaptive, fixed, atr
    trailing_atr_mult: float = 3.0
    trailing_fixed_pct: float = 0.10
    initial_stop_price: float = 0.0
    current_stop_price: float = 0.0
    
    # ─── EVOLUTION (actualizado durante el trade) ───
    highest_price: float = 0.0
    lowest_price: float = 0.0
    max_favorable_excursion_pct: float = 0.0  # MFE: Máximo a favor
    max_adverse_excursion_pct: float = 0.0    # MAE: Máximo en contra
    bars_held: int = 0
    scaling_events: list = field(default_factory=list)  # [{type, price, time}]
    stop_adjustments: list = field(default_factory=list)
    
    # ─── EXIT ───
    exit_price: float = 0.0
    exit_time: str = ""
    exit_reason: str = ""  # STOP_HIT, RS_DECAY, ROTATION, TAKE_PROFIT, MANUAL
    exit_order_id: str = ""
    exit_fill_price: float = 0.0
    exit_slippage: float = 0.0
    exit_snapshot: Optional[dict] = None
    
    # ─── POST-TRADE RESULTS ───
    pnl_dollars: float = 0.0
    pnl_pct: float = 0.0
    pnl_r_multiple: float = 0.0  # PnL en términos de riesgo inicial
    was_winner: bool = False
    
    # ─── ANALYSIS ───
    what_went_right: str = ""
    what_went_wrong: str = ""
    lesson_learned: str = ""
    pattern_tags: list = field(default_factory=list)  # ['breakout', 'contrarian', 'mean_reversion']
    grade: str = ""  # A, B, C, D, F (calidad de la ejecución, no solo resultado)
    
    # ─── META ───
    status: str = "OPEN"  # OPEN, CLOSED, CANCELLED
    strategy_bucket: str = "CORE"  # CORE, TACTICAL, UNCLASSIFIED
    
    # ─── V2: Entry Intelligence Context ───
    # Full EntryIntelligenceReport captured for ML and post-mortem analysis.
    # Contains ~40 variables: VIX, Gamma Regime, Wyckoff State, Whale Flow,
    # Phase, R:R, dimensions confirming, Put Wall, Call Wall, etc.
    entry_intelligence: Optional[dict] = None
