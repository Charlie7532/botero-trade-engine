"""
Price Analysis Module — Models (Value Objects)
"""
from dataclasses import dataclass


@dataclass
class EntryVerdict:
    """Veredicto del diagnóstico de timing para un ticker."""
    ticker: str
    phase: str = "UNKNOWN"           # CORRECTION, BREAKOUT, EXHAUSTION_UP, EXHAUSTION_DOWN, CONSOLIDATION
    verdict: str = "STALK"           # FIRE, STALK, ABORT

    # Precio y estructura
    current_price: float = 0.0
    sma20: float = 0.0
    rsi14: float = 50.0
    atr14: float = 0.0
    distance_to_sma20_atr: float = 0.0  # Distancia en unidades de ATR
    vcp_detected: bool = False           # Volatility Contraction Pattern

    # Niveles de entrada calculados
    entry_price: float = 0.0          # Precio límite recomendado
    stop_price: float = 0.0           # Anclado a Put Wall - buffer
    target_price: float = 0.0         # Call Wall o próxima resistencia
    risk_reward_ratio: float = 0.0    # Target/Stop ratio

    # Dimensión 2: Volumen
    rvol: float = 1.0                 # Relative Volume
    wyckoff_state: str = "UNKNOWN"    # ACCUMULATION, MARKUP, DISTRIBUTION, MARKDOWN, CONSOLIDATION
    volume_confirms: bool = False     # True si volumen confirma la fase

    # Dimensión 3: Opciones
    put_wall: float = 0.0
    call_wall: float = 0.0
    gamma_regime: str = "UNKNOWN"     # PIN, DRIFT, SQUEEZE_UP, SQUEEZE_DOWN
    gamma_confirms: bool = False      # True si gamma confirma la fase

    # Meta
    dimensions_confirming: int = 0    # 0-3 dimensiones que confirman
    confidence: float = 0.0           # 0-100
    diagnosis: str = ""               # Explicación textual


@dataclass
class RSIIntelligenceResult:
    """Result from regime-aware RSI analysis (Cardwell/Brown)."""
    # Regime detection
    rsi_regime: str = "NEUTRAL"         # BULL, BEAR, NEUTRAL
    rsi_value: float = 50.0

    # Regime-aware zone
    rsi_zone: str = "NEUTRAL"           # PULLBACK_BUY, CONTINUATION, OVERBOUGHT_FADE,
                                        # BOUNCE_SELL, CONTINUATION_DOWN, OVERSOLD_TRAP

    # Divergence / Reversal signals (Cardwell)
    divergence_type: str = "NONE"       # POSITIVE_REVERSAL, NEGATIVE_REVERSAL,
                                        # CLASSIC_BULLISH_DIV, CLASSIC_BEARISH_DIV, NONE
    divergence_strength: float = 0.0    # 0.0 → 1.0

    # Slope analysis
    price_slope: float = 0.0            # Linear regression slope of price (normalized)
    rsi_slope: float = 0.0              # Linear regression slope of RSI
    slope_alignment: str = "ALIGNED"    # ALIGNED, DIVERGING, CONVERGING

    # Composite score: -1.0 (max bearish) → +1.0 (max bullish)
    rsi_conviction: float = 0.0

    diagnosis: str = ""
