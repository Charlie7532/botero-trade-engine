"""
Geometric Features — 3D Vector Projections in Slope/Sigma Space
==================================================================
Computes 5 geometric features from a ChannelSnapshot's slope and sigma
fields. These features capture the spatial dynamics of the 3-line
regression system (Tide/Current/Wave) as a 3D vector field.

All functions are pure: no I/O, no side effects, numpy only.

Normalization (LdP Audit Correction):
    Slopes have different intrinsic variances across horizons
    (wave_slope oscillates ~10x more than tide_slope). Before forming
    3D vectors, each slope component is divided by its rolling standard
    deviation to equalize variance contributions. The raw slopes are
    NEVER modified — normalization happens only inside this module.

    slope_stds dict format:
        {"tide": float, "current": float, "wave": float}
    Each value is the rolling σ (e.g. 60-bar) of the respective slope
    for the same ticker. Computed by the daemon/backfill, NOT here.

Pipeline position: Called by compute_channel_snapshot() after all
base fields are populated.
"""
import numpy as np


def compute_geometric_features(
    sigma_tide: float,
    sigma_current: float,
    sigma_wave: float,
    tide_slope: float,
    current_slope: float,
    wave_slope: float,
    tide_accel: float,
    current_accel: float,
    wave_accel: float,
    slope_stds: dict[str, float] | None = None,
) -> tuple[float, float, float, float, float]:
    """Compute 5 geometric features from channel snapshot fields.

    Args:
        sigma_tide/current/wave: Price position in σ units per regression.
        tide/current/wave_slope: Normalized slopes (% of mean price/bar).
        tide/current/wave_accel: Slope changes vs previous bar.
        slope_stds: Rolling standard deviations per slope for normalization.
            If None, slopes are used raw (acceptable for single-ticker
            analysis but not ideal for cross-ticker ML).

    Returns:
        (state_norm, velocity_align, exit_align, accel_align, phase_angle)
    """
    # ── 1. State Norm: magnitude of sigma vector ─────────────
    # How far are we from the channel center across all 3 horizons?
    # Large norm = price deeply displaced from all regressions.
    state_norm = float(np.sqrt(
        sigma_tide ** 2 + sigma_current ** 2 + sigma_wave ** 2
    ))

    # ── 2-4. Velocity vectors (normalized slopes) ────────────
    if slope_stds is not None:
        std_t = max(slope_stds.get("tide", 1.0), 1e-8)
        std_c = max(slope_stds.get("current", 1.0), 1e-8)
        std_w = max(slope_stds.get("wave", 1.0), 1e-8)
    else:
        std_t = std_c = std_w = 1.0

    velocity = np.array([
        tide_slope / std_t,
        current_slope / std_c,
        wave_slope / std_w,
    ])

    # Ideal entry direction: all slopes declining → price falling toward us
    ideal_entry = np.array([-1.0, -1.0, -1.0])

    # Ideal exit direction: all slopes rising → price moving away
    ideal_exit = np.array([1.0, 1.0, 1.0])

    # Acceleration vector (also normalized)
    accel = np.array([
        tide_accel / std_t,
        current_accel / std_c,
        wave_accel / std_w,
    ])

    velocity_align = _cosine(velocity, ideal_entry)
    exit_align = _cosine(velocity, ideal_exit)
    accel_align = _cosine(velocity, accel)

    # ── 5. Phase Angle: arctan2(wave, tide) ──────────────────
    # Where is the wave relative to the tide in the slope plane?
    # Near 0 = aligned. Near ±π = counter-trending.
    phase_angle = float(np.arctan2(
        wave_slope / std_w,
        tide_slope / std_t,
    ))

    return (
        round(state_norm, 4),
        round(velocity_align, 4),
        round(exit_align, 4),
        round(accel_align, 4),
        round(phase_angle, 4),
    )


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors. Returns 0.0 for zero vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-12 or norm_b < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
