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
    sigma_tide: float | None,
    sigma_current: float | None,
    sigma_wave: float | None,
    tide_slope: float | None,
    current_slope: float | None,
    wave_slope: float | None,
    tide_accel: float | None = None,
    current_accel: float | None = None,
    wave_accel: float | None = None,
    slope_stds: dict[str, float] | None = None,
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
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
        Any feature whose required inputs are None/NaN returns None.
    """
    # ── 1. State Norm: magnitude of sigma vector ─────────────
    # How far are we from the channel center across all 3 horizons?
    if (
        sigma_tide is None
        or sigma_current is None
        or sigma_wave is None
        or np.isnan(sigma_tide)
        or np.isnan(sigma_current)
        or np.isnan(sigma_wave)
    ):
        state_norm = None
    else:
        state_norm = round(
            float(np.sqrt(sigma_tide ** 2 + sigma_current ** 2 + sigma_wave ** 2)),
            4,
        )

    # ── 2-4. Velocity vectors (normalized slopes) ────────────
    if slope_stds is not None:
        std_t = max(slope_stds.get("tide", 1.0), 1e-8)
        std_c = max(slope_stds.get("current", 1.0), 1e-8)
        std_w = max(slope_stds.get("wave", 1.0), 1e-8)
    else:
        std_t = std_c = std_w = 1.0

    has_slopes = (
        tide_slope is not None
        and current_slope is not None
        and wave_slope is not None
        and not np.isnan(tide_slope)
        and not np.isnan(current_slope)
        and not np.isnan(wave_slope)
    )

    if has_slopes:
        velocity = np.array([
            tide_slope / std_t,
            current_slope / std_c,
            wave_slope / std_w,
        ])
        ideal_entry = np.array([-1.0, -1.0, -1.0])
        ideal_exit = np.array([1.0, 1.0, 1.0])

        velocity_align = _cosine(velocity, ideal_entry)
        if velocity_align is not None:
            velocity_align = round(velocity_align, 4)

        exit_align = _cosine(velocity, ideal_exit)
        if exit_align is not None:
            exit_align = round(exit_align, 4)

        phase_angle = round(float(np.arctan2(wave_slope / std_w, tide_slope / std_t)), 4)
    else:
        velocity = None
        velocity_align = None
        exit_align = None
        phase_angle = None

    # Acceleration vector (also normalized)
    has_accel = (
        velocity is not None
        and tide_accel is not None
        and current_accel is not None
        and wave_accel is not None
        and not np.isnan(tide_accel)
        and not np.isnan(current_accel)
        and not np.isnan(wave_accel)
    )

    if has_accel:
        accel = np.array([
            tide_accel / std_t,
            current_accel / std_c,
            wave_accel / std_w,
        ])
        accel_align = _cosine(velocity, accel)
        if accel_align is not None:
            accel_align = round(accel_align, 4)
    else:
        accel_align = None

    return (
        state_norm,
        velocity_align,
        exit_align,
        accel_align,
        phase_angle,
    )


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors. Returns 0.0 for zero vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-12 or norm_b < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
