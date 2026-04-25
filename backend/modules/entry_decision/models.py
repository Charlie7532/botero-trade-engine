"""
Entry Decision Module — Models (Value Objects)
"""
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class EntryIntelligenceReport:
    """Reporte unificado de inteligencia para decisión de entrada."""
    ticker: str
    timestamp: str = ""

    # ── EventFlowIntelligence ──────────────────────────────────
    whale_verdict: str = "UNKNOWN"       # RIDE_THE_WHALES, LEAN_WITH_FLOW, UNCERTAIN, CONTRA_FLOW
    whale_scale: float = 1.0
    whale_confidence: float = 0.0
    whale_diagnosis: str = ""
    nearest_event: str = ""
    hours_to_event: float = 999.0
    freeze_stops: bool = False
    freeze_duration_min: int = 0

    # ── PricePhaseIntelligence ─────────────────────────────────
    phase: str = "UNKNOWN"               # CORRECTION, BREAKOUT, EXHAUSTION_UP/DOWN, CONSOLIDATION
    phase_verdict: str = "STALK"         # FIRE, STALK, ABORT
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    risk_reward: float = 0.0
    dimensions_confirming: int = 0
    phase_confidence: float = 0.0
    phase_diagnosis: str = ""

    # ── Datos Vivos (fuentes) ──────────────────────────────────
    current_price: float = 0.0
    vix: float = 17.0
    rs_vs_spy: float = 1.0
    atr: float = 0.0
    rsi: float = 50.0
    rvol: float = 1.0

    # Gamma (from options_awareness)
    put_wall: float = 0.0
    call_wall: float = 0.0
    gamma_regime: str = "UNKNOWN"
    max_pain: float = 0.0

    # Wyckoff (from volume_dynamics)
    wyckoff_state: str = "UNKNOWN"
    wyckoff_velocity: float = 0.0

    # Whale Flow (from uw_intelligence)
    spy_cum_delta: float = 0.0
    spy_signal: str = "NEUTRAL"
    sweep_call_pct: float = 50.0
    total_sweeps: int = 0
    tide_direction: str = "NEUTRAL"
    tide_accelerating: bool = False
    am_pm_divergence: bool = False
    whale_last_updated: Optional[str] = None

    # ── Flow Persistence (V7) ──────────────────────────────────
    flow_persistence_grade: str = "UNKNOWN"
    flow_freshness_weight: float = 1.0
    flow_consecutive_days: int = 0
    flow_darkpool_confirmed: bool = False
    flow_hours_since_latest: float = 999.0

    # ── Volume Profile (V9) ────────────────────────────────────
    vp_poc_short: float = 0.0
    vp_vah_short: float = 0.0
    vp_val_short: float = 0.0
    vp_poc_long: float = 0.0
    vp_vah_long: float = 0.0
    vp_val_long: float = 0.0
    vp_shape_short: str = "D"          # P (accum), D (balanced), b (distrib)
    vp_shape_long: str = "D"
    vp_poc_migration: str = "NEUTRAL"  # BULLISH, BEARISH, NEUTRAL
    vp_institutional_bias: str = "NEUTRAL"  # ACCUMULATION, DISTRIBUTION, NEUTRAL
    vp_bias_confidence: float = 0.0
    vp_price_vs_va: str = "UNKNOWN"    # ABOVE_VA, IN_VA, BELOW_VA
    vp_diagnosis: str = ""

    # ── Pattern Intelligence (V8 — 4ª Dimensión) ──────────────
    candlestick_pattern: str = "NONE"    # Patrón detectado (ej. BULLISH_ENGULFING)
    pattern_sentiment: str = "NEUTRAL"   # BULLISH | BEARISH | NEUTRAL
    pattern_score: float = 0.0           # -1.0 → +1.0
    pattern_on_support: bool = False     # ¿El patrón ocurre en Put Wall?
    pattern_confirms: bool = False       # True si patrón alineado con la fase
    pattern_diagnosis: str = ""          # Explicación textual del patrón

    # ── RSI Intelligence (V10 — Cardwell/Brown) ────────────────
    rsi_regime: str = "NEUTRAL"          # BULL, BEAR, NEUTRAL
    rsi_zone: str = "NEUTRAL"            # PULLBACK_BUY, CONTINUATION, etc.
    rsi_divergence: str = "NONE"         # POSITIVE_REVERSAL, CLASSIC_BEARISH_DIV, etc.
    rsi_divergence_strength: float = 0.0 # 0.0 → 1.0
    rsi_price_slope: float = 0.0         # Normalized price slope
    rsi_indicator_slope: float = 0.0     # RSI slope
    rsi_slope_alignment: str = "ALIGNED" # ALIGNED, DIVERGING, CONVERGING
    rsi_conviction: float = 0.0          # -1.0 → +1.0 composite
    rsi_diagnosis: str = ""

    # ── Dictamen Final ─────────────────────────────────────────
    final_verdict: str = "PASS"          # EXECUTE, STALK, PASS, BLOCK
    final_scale: float = 0.0            # 0-1
    final_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
