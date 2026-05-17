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


@dataclass
class RCIntelligenceResult:
    """Result from Regression Channel Intelligence analysis.

    The RC Intelligence is a multi-purpose tool measuring POSITION within
    a statistical channel (orthogonal to RSI which measures MOMENTUM).

    Five functions:
      1. Entry timing (σ ≤ -1.5 = buy zone)
      2. Fear/Greed scoring (per-ticker contrarian bias)
      3. Trim/Exit detection (σ ≥ +1.5 = overextended)
      4. Movement exhaustion (complacency trap)
      5. Conviction modulation (bias for other signals)
    """
    # ── Channel Structure ──
    regime: str = "FLAT"                # BULL, BEAR, FLAT (from tide_slope)
    sigma_position: float = 0.0         # Price position in σ units within channel
                                        # < -1.5 = support/entry, > +1.5 = resistance/trim
    reg_value: float = 0.0              # Regression line value at current bar
    residual_std: float = 1.0           # σ band width (channel volatility)

    # ── Slopes (the two regression lines) ──
    tide_slope: float = 0.0             # Long regression (200 bars, normalized by price)
    wave_slope: float = 0.0             # Short regression (cycle-adaptive, normalized)
    slope_conjugation: float = 0.0      # wave - tide (ángulo entre líneas)
                                        # < 0 = pullback, > 0 = momentum, >> 0 = exhaustion

    # ── Dynamics (acceleration & flips) ──
    tide_accel: float = 0.0             # Change in tide_slope vs previous bar
    wave_flip: bool = False             # Did wave change sign?
    wave_flip_direction: int = 0        # +1 = knife stopped falling, -1 = knife started

    # ── Fear/Greed (contrarian scoring) ──
    fear_level: int = 2                 # 0=GREED, 1=CONFIDENCE, 2=NEUTRAL, 3=ANXIETY, 4=FEAR, 5=PANIC
    fear_label: str = "NEUTRAL"
    # Empirical: PANIC P(↑)=47.6%, GREED P(↑)=40.4%

    # ── VWAP Reference ──
    vwap: float = 0.0                   # 20-bar VWAP (institutional fair price)
    below_vwap: bool = False            # Discount vs institutional consensus

    # ── Volume Confirmation ──
    vol_up_down_ratio: float = 1.0      # Volume on UP days / DOWN days (5 bars)
                                        # > 1.0 = accumulation, < 1.0 = stealth distribution

    # ── Actionable Zones ──
    zone: str = "NEUTRAL"               # DEEP_VALUE, SUPPORT, FAIR_VALUE, RESISTANCE,
                                        # OVEREXTENDED, EXTREME_GREED
    action: str = "HOLD"                # BUY, TRIM, HOLD

    # ── Composite Conviction ──
    conviction: float = 0.0             # -1.0 (bearish) to +1.0 (bullish)

    diagnosis: str = ""

