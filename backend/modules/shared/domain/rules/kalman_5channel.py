"""
Kalman 5-Channel — Pure Domain Rule
========================================
Applies 5 independent 1D Kalman filters with constant-velocity state model
to signals derived from a ChannelSnapshot.

Channels:
  1. PRICE:       daily returns (%) — momentum direction
  2. RVOL:        relative volume (vol / MA20) — flow intensity
  3. TENSION:     tension_tide — elastic snap vs VWAP
  4. RSI:         rsi_value — ★ SHAP #1 universal
  5. CONJUGATION: conj_wave_tide — wave-vs-tide angle

Each channel outputs:
  - predicted_value:    model forecast for NEXT bar (before seeing it)
  - filtered_velocity:  best estimate of current rate of change
  - innovation:         surprise = actual - predicted

Evidence: Sprint 2, 91K bars, 17 tickers, 20 years.
  kf_rsi_pred_val SHAP importance > 10x any RC feature.
  kf_price_pred_trend_5bar predicts turns 5 bars ahead.

Promoted from: backend/scratch/sprint2_redo_infrastructure_v21.py L142-280

Clean Architecture: Domain rule. Pure math, no IO, no side effects.
"""
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# ── Channel configuration ──
# (name, source_field_in_snapshot, process_noise_frac, obs_noise_frac)
KALMAN_CHANNELS = [
    ("price",       None,              0.05, 0.3),
    ("rvol",        None,              0.10, 0.3),
    ("tension",     "tension_tide",    0.05, 0.2),
    ("rsi",         "rsi_value",       0.03, 0.2),
    ("conjugation", "conj_wave_tide",  0.05, 0.2),
]


@dataclass
class KalmanChannelOutput:
    """Output of one Kalman channel for one bar."""
    predicted_value: float = 0.0
    filtered_velocity: float = 0.0
    innovation: float = 0.0


@dataclass
class KalmanSnapshot:
    """Output of all 5 Kalman channels for one bar.

    This is the "velocity layer" of the pipeline:
    ChannelSnapshot tells WHERE the price is,
    KalmanSnapshot tells WHERE IT'S GOING.
    """
    # ── PRICE channel (returns %) ──
    kf_price_pred_val: float = 0.0
    kf_price_filt_vel: float = 0.0
    kf_price_innovation: float = 0.0

    # ── RVOL channel (relative volume) ──
    kf_rvol_pred_val: float = 0.0
    kf_rvol_filt_vel: float = 0.0

    # ── TENSION channel (tension_tide) ──
    kf_tension_pred_val: float = 0.0
    kf_tension_filt_vel: float = 0.0

    # ── RSI channel ★ SHAP #1 ──
    kf_rsi_pred_val: float = 0.0
    kf_rsi_filt_vel: float = 0.0

    # ── CONJUGATION channel (conj_wave_tide) ──
    kf_conj_pred_val: float = 0.0
    kf_conj_filt_vel: float = 0.0


class FullKalmanFilter1D:
    """1D Kalman filter with constant-velocity model.

    State: x = [value, velocity]
    Transition: x_{t+1} = F * x_t + noise
    Observation: z_t = H * x_t + noise

    Promoted from sprint2_redo_infrastructure_v21.py L142-231.
    """

    def __init__(self, process_noise: float = 0.05, obs_noise: float = 0.2, dt: float = 1.0):
        self.dt = dt
        self.F = np.array([[1.0, dt], [0.0, 1.0]])
        self.H = np.array([[1.0, 0.0]])
        self.Q = np.array([
            [process_noise * dt**2, process_noise * dt],
            [process_noise * dt,    process_noise],
        ])
        self.R = np.array([[obs_noise]])
        self.x: Optional[np.ndarray] = None
        self.P: Optional[np.ndarray] = None

    def reset(self, initial_value: float = 0.0) -> None:
        """Reset state for a new ticker."""
        self.x = np.array([initial_value, 0.0])
        self.P = np.eye(2) * 1.0

    def get_state(self) -> dict:
        """Serialize state for Vault persistence."""
        if self.x is None:
            return {"x0": 0.0, "x1": 0.0, "p00": 1.0, "p01": 0.0, "p10": 0.0, "p11": 1.0}
        return {
            "x0": float(self.x[0]), "x1": float(self.x[1]),
            "p00": float(self.P[0, 0]), "p01": float(self.P[0, 1]),
            "p10": float(self.P[1, 0]), "p11": float(self.P[1, 1]),
        }

    def set_state(self, state: dict) -> None:
        """Restore state from Vault."""
        self.x = np.array([state["x0"], state["x1"]])
        self.P = np.array([
            [state["p00"], state["p01"]],
            [state["p10"], state["p11"]],
        ])

    def update(self, observation: float) -> KalmanChannelOutput:
        """Full Kalman cycle: predict → innovate → update.

        Returns KalmanChannelOutput with predicted_value (t+1 forecast),
        filtered_velocity, and innovation (surprise).
        """
        if self.x is None:
            self.reset(observation)
            return KalmanChannelOutput(
                predicted_value=observation,
                filtered_velocity=0.0,
                innovation=0.0,
            )

        # 1. PREDICT (a priori)
        x_pred = self.F.dot(self.x)
        P_pred = self.F.dot(self.P).dot(self.F.T) + self.Q

        # 2. INNOVATION (surprise)
        z = np.array([observation])
        y = z - self.H.dot(x_pred)
        S = self.H.dot(P_pred).dot(self.H.T) + self.R

        # 3. UPDATE (a posteriori)
        K = P_pred.dot(self.H.T).dot(np.linalg.inv(S))
        x_new = x_pred + K.dot(y)
        P_new = (np.eye(2) - K.dot(self.H)).dot(P_pred)

        # 4. PREDICT NEXT (t+1 forecast)
        x_next_pred = self.F.dot(x_new)

        # Store state
        self.x = x_new
        self.P = P_new

        return KalmanChannelOutput(
            predicted_value=float(x_next_pred[0]),
            filtered_velocity=float(x_new[1]),
            innovation=float(y[0]),
        )


def _auto_calibrate_noise(values: np.ndarray, q_frac: float, r_frac: float) -> tuple[float, float]:
    """Auto-calibrate Kalman noise from data variance.

    Noise params are fractions of the input variance (estimated from
    first 50 points). This ensures proper calibration regardless of
    input scale (RSI 0-100, sigma -3..+3, returns -5..+5%).
    """
    warmup = min(50, len(values))
    warmup_vals = values[:warmup]
    warmup_vals = warmup_vals[np.isfinite(warmup_vals) & (warmup_vals != 0)]
    data_var = float(np.var(warmup_vals)) if len(warmup_vals) > 2 else 1.0
    data_var = max(data_var, 1e-8)
    return q_frac * data_var, r_frac * data_var


def compute_kalman_5ch_series(
    rsi_values: np.ndarray,
    tension_values: np.ndarray,
    conj_values: np.ndarray,
    price_returns: np.ndarray,
    rvol_values: np.ndarray,
) -> tuple[list[KalmanSnapshot], dict]:
    """Compute all 5 Kalman channels for a full series (backfill mode).

    Args:
        rsi_values: RSI(14) values per bar
        tension_values: tension_tide per bar
        conj_values: conj_wave_tide per bar
        price_returns: daily returns (%) per bar
        rvol_values: relative volume (vol / MA20) per bar

    Returns:
        (list of KalmanSnapshot per bar, final_state dict for persistence)
    """
    n = len(rsi_values)
    sources = {
        "price":       price_returns,
        "rvol":        rvol_values,
        "tension":     tension_values,
        "rsi":         rsi_values,
        "conjugation": conj_values,
    }

    # Initialize filters with auto-calibrated noise
    filters: dict[str, FullKalmanFilter1D] = {}
    for ch_name, _, q_frac, r_frac in KALMAN_CHANNELS:
        vals = np.nan_to_num(sources[ch_name], nan=0.0, posinf=0.0, neginf=0.0)
        q_noise, r_noise = _auto_calibrate_noise(vals, q_frac, r_frac)
        filters[ch_name] = FullKalmanFilter1D(process_noise=q_noise, obs_noise=r_noise)

    snapshots: list[KalmanSnapshot] = []
    for i in range(n):
        outputs: dict[str, KalmanChannelOutput] = {}
        for ch_name, _, _, _ in KALMAN_CHANNELS:
            val = float(sources[ch_name][i]) if np.isfinite(sources[ch_name][i]) else 0.0
            outputs[ch_name] = filters[ch_name].update(val)

        snap = KalmanSnapshot(
            kf_price_pred_val=outputs["price"].predicted_value,
            kf_price_filt_vel=outputs["price"].filtered_velocity,
            kf_price_innovation=outputs["price"].innovation,
            kf_rvol_pred_val=outputs["rvol"].predicted_value,
            kf_rvol_filt_vel=outputs["rvol"].filtered_velocity,
            kf_tension_pred_val=outputs["tension"].predicted_value,
            kf_tension_filt_vel=outputs["tension"].filtered_velocity,
            kf_rsi_pred_val=outputs["rsi"].predicted_value,
            kf_rsi_filt_vel=outputs["rsi"].filtered_velocity,
            kf_conj_pred_val=outputs["conjugation"].predicted_value,
            kf_conj_filt_vel=outputs["conjugation"].filtered_velocity,
        )
        snapshots.append(snap)

    # Serialize final state for each filter
    final_state = {ch_name: filters[ch_name].get_state() for ch_name, _, _, _ in KALMAN_CHANNELS}
    return snapshots, final_state


def compute_kalman_5ch_single(
    rsi_value: float,
    tension_tide: float,
    conj_wave_tide: float,
    price_return: float,
    rvol: float,
    prev_state: Optional[dict],
) -> tuple[KalmanSnapshot, dict]:
    """Compute 5 Kalman channels for a SINGLE bar (daemon/live mode).

    Args:
        prev_state: dict of {channel_name: {x0, x1, p00, p01, p10, p11}}
                    from the previous bar. None on first bar.

    Returns:
        (KalmanSnapshot, new_state dict for persistence)
    """
    sources = {
        "price": price_return,
        "rvol": rvol,
        "tension": tension_tide,
        "rsi": rsi_value,
        "conjugation": conj_wave_tide,
    }

    filters: dict[str, FullKalmanFilter1D] = {}
    for ch_name, _, q_frac, r_frac in KALMAN_CHANNELS:
        # For single-bar mode, use fixed noise (can't auto-calibrate from 1 point)
        # These defaults are calibrated from Sprint 2 data variance analysis
        noise_defaults = {
            "price": (0.01, 0.06),
            "rvol": (0.05, 0.15),
            "tension": (0.005, 0.02),
            "rsi": (1.5, 10.0),
            "conjugation": (0.0001, 0.0004),
        }
        q, r = noise_defaults[ch_name]
        kf = FullKalmanFilter1D(process_noise=q, obs_noise=r)

        if prev_state and ch_name in prev_state:
            kf.set_state(prev_state[ch_name])
        else:
            kf.reset(sources[ch_name])

        filters[ch_name] = kf

    outputs: dict[str, KalmanChannelOutput] = {}
    for ch_name in filters:
        val = sources[ch_name]
        if not np.isfinite(val):
            val = 0.0
        outputs[ch_name] = filters[ch_name].update(val)

    snap = KalmanSnapshot(
        kf_price_pred_val=outputs["price"].predicted_value,
        kf_price_filt_vel=outputs["price"].filtered_velocity,
        kf_price_innovation=outputs["price"].innovation,
        kf_rvol_pred_val=outputs["rvol"].predicted_value,
        kf_rvol_filt_vel=outputs["rvol"].filtered_velocity,
        kf_tension_pred_val=outputs["tension"].predicted_value,
        kf_tension_filt_vel=outputs["tension"].filtered_velocity,
        kf_rsi_pred_val=outputs["rsi"].predicted_value,
        kf_rsi_filt_vel=outputs["rsi"].filtered_velocity,
        kf_conj_pred_val=outputs["conjugation"].predicted_value,
        kf_conj_filt_vel=outputs["conjugation"].filtered_velocity,
    )

    new_state = {ch_name: filters[ch_name].get_state() for ch_name in filters}
    return snap, new_state
