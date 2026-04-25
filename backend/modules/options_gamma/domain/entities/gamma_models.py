from dataclasses import dataclass, field

@dataclass
class GammaRegime:
    """Resultado del análisis de régimen gamma."""
    regime: str = "UNKNOWN"         # PIN, DRIFT, SQUEEZE_UP, SQUEEZE_DOWN
    net_gex: float = 0.0            # Net Gamma Exposure en dólares
    call_gex: float = 0.0           # Call GEX (estabilizador)
    put_gex: float = 0.0            # Put GEX (desestabilizador)
    gamma_shares_per_dollar: int = 0  # Acciones de hedge por $1 de movimiento
    hedge_dollars_per_dollar: float = 0.0  # Dólares de hedge por $1
    flip_up: float = 0.0            # Precio donde GEX se vuelve negativo (arriba)
    flip_down: float = 0.0          # Precio donde GEX se vuelve negativo (abajo)
    call_wall: float = 0.0          # Strike con mayor call OI arriba del precio
    call_wall_oi: int = 0
    put_wall: float = 0.0           # Strike con mayor put OI debajo del precio
    put_wall_oi: int = 0
    pin_range_low: float = 0.0      # Rango esperado de pin (bajo)
    pin_range_high: float = 0.0     # Rango esperado de pin (alto)


@dataclass
class OpExType:
    """Tipo de expiración de opciones."""
    is_opex_day: bool = False
    opex_type: str = "NON_OPEX"     # QUAD_WITCHING, MONTHLY_OPEX, WEEKLY_OPEX, NON_OPEX
    is_am_session: bool = False      # True si estamos en 9:30-12:00 ET
    time_weight: float = 0.0         # 0.0-1.0, peso temporal del pin


@dataclass
class OptionsAnalysis:
    """Análisis completo de opciones para un ticker."""
    symbol: str = ""
    current_price: float = 0.0
    max_pain: float = 0.0
    max_pain_distance_pct: float = 0.0
    put_call_ratio: float = 0.0
    total_oi: int = 0
    # Gamma Regime
    gamma_regime: GammaRegime = field(default_factory=GammaRegime)
    # OpEx
    opex: OpExType = field(default_factory=OpExType)
    # Gravity Score (-1.0 a +1.0)
    gravity_score: float = 0.0       # >0 = pull UP, <0 = pull DOWN
    gravity_strength: float = 0.0    # 0-100, fuerza absoluta
    # Legacy compat
    mm_bias: str = "NEUTRAL"
    gex_positive: bool = True
    expiration: str = ""
    timestamp: str = ""
