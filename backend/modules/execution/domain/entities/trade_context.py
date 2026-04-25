from enum import Enum
from dataclasses import dataclass

class PositionState(Enum):
    FLAT = 0         # Sin posición
    PROBING = 1      # Sonda inicial inyectada
    SCALING_IN = 2   # Posición Core inyectada por confirmación
    SCALING_OUT = 3  # Distribución parcial de ganancias

@dataclass
class TradeContext:
    ticker: str
    current_price: float
    lstm_probability: float
    target_kelly_pct: float
    current_state: PositionState = PositionState.FLAT
    average_entry: float = 0.0
    current_exposure_pct: float = 0.0
