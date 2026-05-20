from dataclasses import dataclass

@dataclass
class IndicatorSnapshot:
    """
    Snapshot MÍNIMO de mercado/indicador al momento de la señal.
    Contiene SOLO lo que el indicador ya produce nativamente o que se deriva de forma ortogonal.
    
    Separado en:
      - PRIMITIVAS ORTOGONALES: para ML (features independientes)
      - LABELS DERIVADAS: para diagnóstico humano (redundantes con primitivas)
    """
    # ══════════════════════════════════════════════════════════
    # PRIMITIVAS ORTOGONALES — Input para ML (Tier 1)
    # Cada campo mide una dimensión independiente del mercado
    # ══════════════════════════════════════════════════════════
    sigma_tide: float             # Posición vs tendencia macro (200-bar)
    sigma_wave: float             # Posición vs ciclo actual
    tide_slope: float             # Dirección macro (normalized)
    wave_slope: float             # Dirección micro (normalized)
    tide_accel: float             # Aceleración de la tendencia
    below_vwap: bool              # Descuento institucional
    vol_up_down_ratio: float      # Acumulación vs distribución
    wave_flip: bool               # Punto de inflexión micro
    wave_flip_direction: int      # +1 knife stopped, -1 knife started
    rvol: float                   # Convicción del mercado
    
    # ── Per-indicator (ortogonales entre sí) ──
    rsi_value: float | None = None        # Momentum (ortogonal a posición)
    wyckoff_state: str | None = None      # Estado de volumen (Kalman)
    kalman_velocity: float | None = None  # Velocidad suavizada
    vol_regime: str | None = None         # Régimen de volatilidad
    
    # ══════════════════════════════════════════════════════════
    # LABELS DERIVADAS — Solo para diagnóstico humano
    # Se capturan para los ReportCards, NO se pasan al ML
    # ══════════════════════════════════════════════════════════
    regime: str = "FLAT"          # SBULL/BULL/FLAT/BEAR/SBEAR (= f(tide_slope))
    fear_level: int = 2           # 0-5 GREED→PANIC (= f(tide, wave, accel))
    fear_label: str = "NEUTRAL"   # Etiqueta legible del fear_level
    slope_conjugation: float = 0.0  # wave - tide (= wave_slope - tide_slope)
