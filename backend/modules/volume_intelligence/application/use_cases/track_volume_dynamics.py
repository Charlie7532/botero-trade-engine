import logging
import numpy as np
from typing import Dict, Optional
from backend.modules.volume_intelligence.domain.rules.volume_rules import SectorRegimeDetector

logger = logging.getLogger(__name__)

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
            'history_len': 0,
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
            Dict con rvol suavizado, velocidad, aceleración y estado Wyckoff.
        """
        if etf not in self._states:
            self._states[etf] = self._init_state(observed_rvol)

        state = self._states[etf]
        x_prev = state['x']
        P_prev = state['P']

        # ── 1. Predicción ──
        x_pred = self.F.dot(x_prev)
        P_pred = self.F.dot(P_prev).dot(self.F.T) + self.Q

        # ── 2. Actualización ──
        z = np.array([observed_rvol])
        y = z - self.H.dot(x_pred)  # Residual (innovation)
        S = self.H.dot(P_pred).dot(self.H.T) + self.R
        K = P_pred.dot(self.H.T).dot(np.linalg.inv(S))  # Kalman Gain

        x_new = x_pred + K.dot(y)
        P_new = (np.eye(2) - K.dot(self.H)).dot(P_pred)

        # ── 3. Derivadas y Clasificación ──
        smoothed_rvol = x_new[0]
        velocity = x_new[1]
        acceleration = velocity - state.get('prev_vel', 0.0)

        wyckoff = SectorRegimeDetector.classify(
            rel_vol=smoothed_rvol,
            velocity=velocity,
            acceleration=acceleration,
            change_pct=change_pct,
        )

        # Guardar estado para la próxima iteración
        self._states[etf] = {
            'x': x_new,
            'P': P_new,
            'prev_vel': velocity,
            'history_len': state.get('history_len', 0) + 1,
        }

        # Calcular confianza inversamente proporcional a la incertidumbre (P)
        # Traza de P es la varianza total. Si es alta, confianza baja.
        trace_p = P_new[0, 0] + P_new[1, 1]
        confidence = max(0.0, min(1.0, 1.0 - (trace_p / 4.0)))

        return {
            'etf': etf,
            'rvol_smoothed': round(float(smoothed_rvol), 2),
            'velocity': round(float(velocity), 4),
            'acceleration': round(float(acceleration), 4),
            'wyckoff_state': wyckoff,
            'confidence': round(float(confidence), 3),
        }

    def get_early_rotations(self, min_velocity: float = 0.2,
                            min_confidence: float = 0.5) -> list:
        """
        Escanea el universo buscando los sectores con mayor aceleración
        hacia un estado de Acumulación (dinero inteligente rotando).

        Returns:
            Lista ordenada por velocidad descendente de los mejores candidatos.
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
