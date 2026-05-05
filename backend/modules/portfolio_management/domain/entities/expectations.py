from dataclasses import dataclass, field

@dataclass
class ImpliedExpectations:
    """
    Representa el resultado del Reverse DCF (Expectations Engine).
    Compara el crecimiento implícito en el precio con el crecimiento real histórico.
    """
    ticker: str
    current_price: float
    market_implied_growth_rate: float
    historical_growth_rate: float
    growth_gap: float  # historical - implied
    assessment: str    # "PRICED_FOR_PERFECTION", "PRICED_FOR_FAILURE", "FAIRLY_PRICED"
    raw_data: dict = field(default_factory=dict)
