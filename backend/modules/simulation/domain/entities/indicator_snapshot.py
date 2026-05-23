from dataclasses import dataclass

@dataclass
class IndicatorSnapshot:
    """
    Snapshot MÍNIMO de mercado/indicador al momento de la señal.
    Contiene SOLO lo que el indicador ya produce nativamente o que se deriva de forma ortogonal.
    
    Separado en:
      - PRIMITIVAS ORTOGONALES: para ML (features independientes)
      - LABELS DERIVADAS: para diagnóstico humano (redundantes con primitivas)
    
    v2 (2026-05-21): Added triple regression (σ_current, spreads, conjs),
    triple VWAP (vwap_sigma_*), and pattern recognition context.
    New fields default to None for backward compatibility with existing labels.
    """
    # ══════════════════════════════════════════════════════════
    # PRIMITIVAS ORTOGONALES — Input para ML (Tier 1)
    # Each field measures an independent market dimension
    # ══════════════════════════════════════════════════════════

    # ── Triple Regression Sigmas ──
    sigma_tide: float             # vs 240-bar regression (was 200)  ★★ VALIDATED
    sigma_wave: float             # vs cycle-adaptive regression
    sigma_current: float | None = None  # vs 60-bar regression (NEW)

    # ── Triple Slopes ──
    tide_slope: float = 0.0      # Macro direction (normalized)
    wave_slope: float = 0.0      # Short-term direction
    current_slope: float | None = None  # Medium-term direction (NEW)

    # ── Triple Accelerations ──
    tide_accel: float = 0.0      # ★★ STRONG (RC r=-0.103)
    current_accel: float | None = None  # NEW ★ MODERATE (RSI)
    wave_accel: float | None = None     # NEW

    # ── Triple Conjugations (slope diffs) ──
    slope_conjugation: float = 0.0      # wave - tide (LEGACY name, kept for compat)
    conj_wave_tide: float | None = None       # wave - tide (same as slope_conjugation)  ★ MODERATE
    conj_current_tide: float | None = None    # current - tide  ★ MODERATE (RC)
    conj_wave_current: float | None = None    # wave - current

    # ── Triple Sigma Spreads ──
    spread_tide_current: float | None = None  # σ_tide - σ_current  ★ MODERATE (✅ stable)
    spread_tide_wave: float | None = None
    spread_current_wave: float | None = None

    # ── Triple VWAP Sigmas ──
    vwap_sigma_tide: float | None = None      # vs 240-bar VWAP  ★ MODERATE
    vwap_sigma_current: float | None = None   # vs 60-bar VWAP   ★ MODERATE (88% tickers)
    vwap_sigma_wave: float | None = None      # vs cycle VWAP    ★★ STRONG (RSI)

    # ── Existing primitives (carried forward) ──
    below_vwap: bool = False      # DEPRECATED → replaced by vwap_sigma_* continuo
    vol_up_down_ratio: float = 1.0
    wave_flip: bool = False
    wave_flip_direction: int = 0  # +1 knife stopped, -1 knife started
    rvol: float = 1.0            # Relative volume (conviction)

    # ── VWAP composite flags (NEW) ──
    below_all_vwaps: bool | None = None   # Price < all 3 VWAPs = institutional discount
    above_all_vwaps: bool | None = None   # Price > all 3 VWAPs = anti-signal (WR=38.6%)

    # ── Tensions: Reg σ minus VWAP σ (v15 Part 3) ──
    tension_tide: float | None = None       # sigma_tide - vwap_sigma_tide
    tension_current: float | None = None    # sigma_current - vwap_sigma_current
    tension_wave: float | None = None       # sigma_wave - vwap_sigma_wave

    # ── Compression (Mandelbrot squeeze, v15 Part 8) ──
    compression_ratio: float | None = None  # residual_std_wave / residual_std_tide

    # ── Geometric Features (3D vector projections) ──
    geo_state_norm: float | None = None     # ‖σ_vector‖
    geo_velocity_align: float | None = None # cos(velocity, ideal_entry)
    geo_exit_align: float | None = None     # cos(velocity, ideal_exit)
    geo_accel_align: float | None = None    # cos(velocity, acceleration)
    geo_phase_angle: float | None = None    # arctan2(wave_slope_norm, tide_slope_norm)

    # ── Per-indicator (orthogonal) ──
    rsi_value: float | None = None        # Momentum (orthogonal to position)
    wyckoff_state: str | None = None      # Volume state (Kalman)
    kalman_velocity: float | None = None  # Smoothed velocity
    vol_regime: str | None = None         # Volatility regime label

    # ── Pattern Recognition (NEW — optional context) ──
    candle_pattern: str | None = None     # e.g. "HAMMER", "MORNING_STAR", "NONE"
    candle_sentiment: str | None = None   # "BULLISH" / "BEARISH" / "NEUTRAL"
    candle_confirmation_score: float | None = None  # -1.0 to +1.0

    # ══════════════════════════════════════════════════════════
    # LABELS DERIVADAS — Solo para diagnóstico humano
    # Se capturan para los ReportCards, NO se pasan al ML
    # ══════════════════════════════════════════════════════════
    regime: str = "FLAT"          # BULL/FLAT/BEAR (= f(tide_slope))
    fear_level: int = 2           # 0-5 GREED→PANIC (= f(tide, wave, accel))
    fear_label: str = "NEUTRAL"   # Human-readable label

