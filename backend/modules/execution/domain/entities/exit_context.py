from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class TradeState:
    """Estado actual de la operación."""
    ticker: str
    entry_price: float
    highest_price: float
    current_stop: float
    bars_held: int
    entry_rs: float = 1.0
    
@dataclass
class MarketContext:
    """Contexto actual del mercado para la toma de decisión."""
    current_price: float
    current_atr: float
    ma20: float
    rs_vs_spy: float
    wyckoff_state: str = "UNKNOWN"
    put_wall: float = 0.0
    vix_current: float = 17.0
    flow_persistence_grade: str = "UNKNOWN"
    max_bars: int = 30
    freeze_stops: bool = False
    freeze_start_time: Optional[datetime] = None

@dataclass
class ExitDecision:
    """Decisión de salida."""
    should_exit: bool
    reason: str = ""
    urgency: str = "none"  # "high", "medium", "none"
    new_stop_price: float = 0.0
