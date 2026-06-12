"""
ObserverSnapshot — Persistence Entity
========================================
Value object for persisting UnifiedKalmanObserver output to the Vault.

Stored as additional columns in engine.channel_snapshots:
  obs_recovery_score REAL,
  obs_velocity_norm  REAL,
  obs_state          TEXT

Clean Architecture: Domain entity. Pure data, no behavior.
"""
from dataclasses import dataclass, asdict


@dataclass
class ObserverSnapshot:
    """Persisted output of the UnifiedKalmanObserver for one bar.

    Consumed by SwingGate via load_latest_snapshot().
    """
    obs_recovery_score: float = 0.0    # cos(vel, recovery dir): -1 to +1
    obs_velocity_norm: float = 0.0     # ‖velocity‖: movement speed
    obs_state: str = "STABLE"          # RECOVERING / DETERIORATING / TRANSITIONING / STABLE

    # Individual velocities (forensics)
    obs_vel_sigma_c: float = 0.0
    obs_vel_svw: float = 0.0
    obs_vel_tension_w: float = 0.0
    obs_vel_rsi: float = 0.0
    obs_vel_conj_wt: float = 0.0

    def to_dict(self) -> dict:
        """Serialize for DB storage."""
        return asdict(self)
