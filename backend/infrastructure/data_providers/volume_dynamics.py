"""
VOLUME DYNAMICS: Derivada de Volumen e Identificación de Régimen
=================================================================
Responde la pregunta que los quants institucionales hacen:
"¿Está el volumen ACELERANDO hacia un sector, o ya llegamos tarde?"

Módulo:
  KalmanVolumeTracker  — Estima velocidad y aceleración del Relative Volume
                          en tiempo real via Filtro de Kalman (sin lag).
  SectorRegimeDetector — Clasifica el estado Wyckoff actual (4 estados)
                          usando la señal Kalman + precio.
  VolumeDynamicsReport — Consolida ambos en el reporte de contexto del motor.

Fundamentos matemáticos:
  El Filtro de Kalman modela el estado del sistema como un vector:
    x = [rel_vol, vel_vol]  (posición + velocidad)
  La observación Z es el rel_vol actual (ruidoso).
  El filtro estima el estado latente suavizando el ruido de mercado,
  entregando la velocidad (primera derivada) sin el lag de las EMAs.

Referencias:
  - Kalman, R.E. (1960): A New Approach to Linear Filtering...
  - Wyckoff, R.D. (1930): The Richard D. Wyckoff Method of Trading...
  - López de Prado (2018): Advances in Financial Machine Learning, Ch. 17
"""
import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime, UTC

logger = logging.getLogger(__name__)


@dataclass
class KalmanState:
    """Estado estimado por el Filtro de Kalman para un ETF."""
    etf: str
    rel_vol: float = 1.0          # Posición estimada (suavizada)
    velocity: float = 0.0         # Primera derivada: velocidad de cambio del rvol
    acceleration: float = 0.0     # Segunda derivada: aceleración
    wyckoff_state: str = 'UNKNOWN'
    confidence: float = 0.0       # Incertidumbre del estimado (baja = más confiable)
    last_update: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    history_len: int = 0          # Cuántas observaciones han pasado por el filtro


class KalmanVolumeTracker:
    """
    Rastreador de Volumen con Filtro de Kalman.

    Para cada ETF mantiene un estado Kalman independiente con su propio
    historial. Permite estimar la velocidad (∂RVol/∂t) y aceleración
    (∂²RVol/∂t²) del Relative Volume en tiempo real.

    Parámetros del modelo:
      dt        : Paso de tiempo (1.0 = 1 lectura = 1 sesión o snapshot)
      process_noise (Q): Cuánto confiamos en que el sistema cambia entre
                  lecturas. Valores altos → más reactivo (más ruido).
      obs_noise (R)    : Cuánto ruido tiene la observación del rvol.
                  Valores altos → confiar más en el modelo que en la obs.

    Esquema del filtro:
      Estado: x = [rvol, vel_rvol]  (vector 2D)
      Transición: F = [[1, dt], [0, 1]]  (modelo de velocidad constante)
      Observación: H = [1, 0]  (solo observamos rvol, no velocidad)
    """

    def __init__(
        self,
        dt: float = 1.0,
        process_noise: float = 0.05,
        obs_noise: float = 0.2,
    ):
        self.dt = dt
        # Matriz de transición de estado (modelo de velocidad constante)
        self.F = np.array([[1.0, dt], [0.0, 1.0]])
        # Matriz de observación: solo medimos rvol
        self.H = np.array([[1.0, 0.0]])
        # Covarianza del ruido del proceso
        self.Q = np.array([
            [process_noise * dt**2, process_noise * dt],
            [process_noise * dt,    process_noise],
        ])
        # Varianza del ruido de observación
        self.R = np.array([[obs_noise]])
        # Estado por ETF: {etf: {'x': [...], 'P': [[...]]}}
        self._states: Dict[str, dict] = {}

    def _init_state(self, initial_rvol: float) -> dict:
        """Inicializa el estado Kalman para un nuevo ETF."""
        return {
            'x': np.array([initial_rvol, 0.0]),   # [rvol, velocidad=0]
            'P': np.eye(2) * 1.0,                  # Alta incertidumbre inicial
            'prev_vel': 0.0,                        # Para calcular aceleración
        }

    def update(self, etf: str, observed_rvol: float, change_pct: float = None) -> dict:
        """
        Procesa una nueva observación de Relative Volume para un ETF.

        Ejecuta el ciclo completo Kalman:
          1. Predicción: proyectar estado anterior al tiempo t
          2. Actualización: corregir con la observación actual

        Args:
            etf: Ticker del ETF (e.g. 'XLK', 'EEM')
            observed_rvol: Relative Volume observado en este snapshot.
            change_pct: Cambio de precio % del período (crucial para
                        clasificación Wyckoff correcta). Si None, el
                        clasificador opera ciego (40% falsos positivos).

        Returns:
            Dict con: rel_vol, velocity, acceleration, wyckoff_state, confidence
        """
        # ── Inicializar si es la primera observación ──────────────────
        if etf not in self._states:
            self._states[etf] = self._init_state(observed_rvol)
            return {
                'etf': etf,
                'rel_vol': observed_rvol,
                'velocity': 0.0,
                'acceleration': 0.0,
                'wyckoff_state': 'UNKNOWN',
                'confidence': 1.0,
                'history_len': 1,
            }

        state = self._states[etf]
        x = state['x']
        P = state['P']
        prev_vel = state['prev_vel']

        # ── Fase 1: PREDICCIÓN ────────────────────────────────────────
        x_pred = self.F @ x
        P_pred = self.F @ P @ self.F.T + self.Q

        # ── Fase 2: ACTUALIZACIÓN (Innovación) ────────────────────────
        z = np.array([[observed_rvol]])
        y = z - self.H @ x_pred                # Innovación (error de predicción)
        S = self.H @ P_pred @ self.H.T + self.R
        K = P_pred @ self.H.T @ np.linalg.inv(S)  # Ganancia Kalman

        x_new = x_pred + K @ y.flatten()
        P_new = (np.eye(2) - K @ self.H) @ P_pred

        # Guardar estado actualizado
        state['x'] = x_new
        state['P'] = P_new
        state['prev_vel'] = x_new[1]
        state.setdefault('history_len', 0)
        state['history_len'] += 1

        vel = x_new[1]
        accel = vel - prev_vel

        # Confianza inversamente proporcional a la incertidumbre diagonal
        confidence = float(np.clip(1.0 - (P_new[0, 0] + P_new[1, 1]) / 4.0, 0.0, 1.0))

        wyckoff = SectorRegimeDetector.classify(
            rel_vol=x_new[0],
            velocity=vel,
            acceleration=accel,
            change_pct=change_pct,
        )

        return {
            'etf': etf,
            'rel_vol': round(float(x_new[0]), 3),
            'velocity': round(float(vel), 4),
            'acceleration': round(float(accel), 4),
            'wyckoff_state': wyckoff,
            'confidence': round(confidence, 3),
            'history_len': state['history_len'],
        }

    def bulk_update(self, readings: Dict[str, float]) -> Dict[str, dict]:
        """
        Actualiza múltiples ETFs en una sola llamada.

        Args:
            readings: {etf_ticker: observed_rvol}

        Returns:
            {etf_ticker: estado_kalman}
        """
        return {etf: self.update(etf, rvol) for etf, rvol in readings.items()}

    def get_early_rotation_signals(
        self,
        min_velocity: float = 0.15,
        min_confidence: float = 0.4,
    ) -> list[dict]:
        """
        Filtra ETFs que muestran señales TEMPRANAS de rotación institucional.

        Un ETF está en acumulación temprana si:
          - Su velocidad de rvol es positiva (acelerando)
          - Su rvol absoluto no ha explotado aún (< 2.5x) → no llegamos tarde
          - La confianza del estimado es suficiente (historial mínimo)

        Args:
            min_velocity: Umbral mínimo de velocidad de rvol para señal temprana.
            min_confidence: Confianza mínima del filtro Kalman.

        Returns:
            Lista de ETFs con señal de acumulación temprana, ordenados por velocidad.
        """
        signals = []
        for etf, state in self._states.items():
            x = state['x']
            rvol = x[0]
            vel = x[1]
            prev_vel = state.get('prev_vel', 0.0)
            accel = vel - prev_vel
            hist = state.get('history_len', 0)

            if hist < 2:
                continue  # Sin suficiente historial

            conf = float(np.clip(1.0 - (state['P'][0, 0] + state['P'][1, 1]) / 4.0, 0.0, 1.0))

            if vel >= min_velocity and rvol < 2.5 and conf >= min_confidence:
                signals.append({
                    'etf': etf,
                    'rvol_current': round(float(rvol), 2),
                    'velocity': round(float(vel), 4),
                    'acceleration': round(float(accel), 4),
                    'wyckoff_state': SectorRegimeDetector.classify(rvol, vel, accel),
                    'confidence': round(conf, 3),
                    'signal': 'EARLY_ACCUMULATION',
                })

        return sorted(signals, key=lambda s: s['velocity'], reverse=True)


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


@dataclass
class VolumeDynamicsReport:
    """
    Reporte consolidado de dinámica de volumen para el Motor de Trading.

    Este es el output final que consume el SmartEntryEngine antes de
    decidir si aprobar o rechazar una entrada.
    """
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    # Señales tempranas de rotación (los "caballos que van a salir")
    early_rotation_signals: list = field(default_factory=list)

    # Estado Wyckoff del sector del ticker candidato
    ticker_sector_etf: str = ""
    ticker_sector_state: str = "UNKNOWN"
    ticker_sector_velocity: float = 0.0

    # Flujo global
    dominated_by_distribution: bool = False   # ¿La mayoría del mercado distribuye?
    risk_off_international: bool = False       # ¿EEM/EFA en distribución?
    n_accumulating: int = 0   # ETFs en acumulación
    n_distributing: int = 0   # ETFs en distribución

    # Recomendación final
    flow_supports_entry: bool = True
    abort_reason: str = ""

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp,
            'early_rotation_signals': self.early_rotation_signals,
            'ticker_sector_etf': self.ticker_sector_etf,
            'ticker_sector_state': self.ticker_sector_state,
            'ticker_sector_velocity': self.ticker_sector_velocity,
            'dominated_by_distribution': self.dominated_by_distribution,
            'risk_off_international': self.risk_off_international,
            'n_accumulating': self.n_accumulating,
            'n_distributing': self.n_distributing,
            'flow_supports_entry': self.flow_supports_entry,
            'abort_reason': self.abort_reason,
        }
