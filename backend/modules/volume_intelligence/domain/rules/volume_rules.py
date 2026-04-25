from typing import Optional

# ═══════════════════════════════════════════════════════════════
# VOLUME PROFILE (VolumeProfileAnalyzer)
# ═══════════════════════════════════════════════════════════════

# Shape detection
P_SHAPE_SKEW_THRESHOLD = 0.15     # Skew > 0.15 = P-shape (accumulation)
B_SHAPE_SKEW_THRESHOLD = -0.15    # Skew < -0.15 = b-shape (distribution)

# POC Migration
POC_MIGRATION_THRESHOLD = 0.5     # >0.5% migration = significant

# Value Area
VALUE_AREA_PCT = 0.70             # Standard 70% value area

# Volume Node classification
HVN_THRESHOLD = 1.5              # >1.5x avg volume = High Volume Node
LVN_THRESHOLD = 0.5              # <0.5x avg volume = Low Volume Node

# VP Distribution Gate (used by Entry Decision Hub)
VP_DISTRIBUTION_CONFIDENCE_THRESHOLD = 75


# ═══════════════════════════════════════════════════════════════
# KALMAN VOLUME TRACKER
# ═══════════════════════════════════════════════════════════════

# Kalman filter process noise
KALMAN_PROCESS_NOISE = 0.01
KALMAN_MEASUREMENT_NOISE = 0.1

# Wyckoff state thresholds
WYCKOFF_ACCUMULATION_VEL = 0.5    # Positive velocity + low price
WYCKOFF_MARKUP_VEL = 1.0          # High positive velocity
WYCKOFF_DISTRIBUTION_VEL = -0.3   # Negative velocity + high price
WYCKOFF_MARKDOWN_VEL = -1.0       # High negative velocity

class SectorRegimeDetector:
    """
    Clasificador de Régimen de Mercado Wyckoff (4 estados).

    Integra la señal Kalman (velocidad + aceleración del rvol) con el nivel
    absoluto para emitir el estado más probable del ciclo de mercado para
    ese ETF.

    Los 4 estados del ciclo Wyckoff:
      ACCUMULATION  : Precio lateral, volumen acelerando suavemente.
                      Dinero inteligente comprando gradualmente.
                      → MEJOR MOMENTO DE ENTRADA ANTICIPADA.

      MARKUP        : Precio subiendo + volumen confirma.
                      La tendencia está establecida.
                      → ENTRADA VÁLIDA pero no la mejor.

      DISTRIBUTION  : Precio en máximos, volumen muy alto + price reversal.
                      Dinero inteligente distribuyendo.
                      → EVITAR O SALIR.

      MARKDOWN      : Precio bajando con volumen.
                      → SOLO SI BUSCAMOS SHORTS O BOTTOM FISHING.

      UNKNOWN       : Historial insuficiente.
    """

    @staticmethod
    def classify(
        rel_vol: float,
        velocity: float,
        acceleration: float,
        change_pct: Optional[float] = None,
    ) -> str:
        """
        Clasifica el régimen actual de un ETF.

        Args:
            rel_vol: Relative Volume estimado por Kalman.
            velocity: Primera derivada del rvol (velocidad).
            acceleration: Segunda derivada (aceleración de acumulación).
            change_pct: Cambio de precio % (opcional, mejora la clasificación).

        Returns:
            Estado Wyckoff: 'ACCUMULATION' | 'MARKUP' | 'DISTRIBUTION' |
                            'MARKDOWN' | 'CONSOLIDATION'
        """
        # Acumulación: volumen acelerando pero no explotado + no caída fuerte
        if velocity > 0.1 and rel_vol < 2.0 and acceleration >= 0:
            if change_pct is None or change_pct > -1.0:
                return 'ACCUMULATION'

        # Markup: volumen alto + precio subiendo (confirmación)
        if rel_vol >= 1.5 and (change_pct is not None and change_pct > 0.5):
            return 'MARKUP'

        # Distribution: volumen muy alto + velocidad desacelerando o negativa
        if rel_vol >= 2.0 and velocity < 0:
            return 'DISTRIBUTION'

        # Distribution: precio negativo + volumen alto
        if rel_vol >= 1.5 and (change_pct is not None and change_pct < -0.5):
            return 'DISTRIBUTION'

        # Markdown: volumen bajo pero precio cae
        if rel_vol < 0.8 and (change_pct is not None and change_pct < -0.5):
            return 'MARKDOWN'

        # Default: consolidación / estado no determinado
        return 'CONSOLIDATION'
