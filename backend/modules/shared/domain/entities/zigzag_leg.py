import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ZigzagLeg:
    ticker: str
    scale: str
    leg_id: str
    start_timestamp: datetime
    start_type: str  # 'MIN' or 'MAX'
    start_price: float
    end_timestamp: datetime
    end_type: str  # 'MAX' or 'MIN'
    end_price: float
    confirmed_at_timestamp: datetime
    status: str = "CONFIRMED"
    prev_leg_return: Optional[float] = None      # Return of the previous leg (signed decimal)
    prev_leg_duration: Optional[int] = None       # Duration in days of the previous leg

    @property
    def duration_bars(self) -> int:
        d = (self.end_timestamp - self.start_timestamp).days
        return max(d, 1)

    @property
    def confirmation_lag_bars(self) -> int:
        d = (self.confirmed_at_timestamp - self.end_timestamp).days
        return max(d, 0)

    @property
    def theoretical_return_pct(self) -> float:
        return ((self.end_price / self.start_price) - 1.0) * 100.0

    @property
    def log_return(self) -> float:
        return math.log(self.end_price / self.start_price) * 100.0 if self.start_price > 0 else 0.0

    @property
    def daily_return_pct(self) -> float:
        return self.theoretical_return_pct / self.duration_bars

    def get_sigma_return(self, daily_std_pct: float) -> float:
        """
        Calcula el retorno normalizado en unidades de la volatilidad del activo (Sigmas σ).
        Formula: R_sigma = log_return / (daily_std_pct * sqrt(duration_bars))
        Homogeneiza activos de alta y baja volatilidad en la misma escala adimensional.
        """
        if daily_std_pct <= 0 or self.duration_bars <= 0:
            return 0.0
        return self.log_return / (daily_std_pct * math.sqrt(self.duration_bars))
