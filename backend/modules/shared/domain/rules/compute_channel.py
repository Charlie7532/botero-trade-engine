"""
Compute Channel Snapshot — Single Pure Function
==================================================
Computes ALL regression channel + VWAP derivatives at a single point
in time, returning a ChannelSnapshot with zero duplication.

This is the ONLY function that calls linreg_channel(). All consumers
(RCIntelligence, RSIIntelligence, Oracle, SwingGate) receive a
pre-computed ChannelSnapshot instead of recomputing independently.

Triple regression: TIDE(240) + CURRENT(60) + WAVE(cycle-adaptive)
Triple VWAP: same three windows, volume-weighted fair price.

Pipeline position: PIEZA 1 core computation.

Performance per bar:
  - 6 regressions (3 current + 3 previous bar for acceleration)
  - 3 VWAPs
  - 1 cycle detection
  - 0 duplicates
  Total: ~10 operations vs 12+ with duplicates in old system.

No external dependencies beyond numpy.
"""
import numpy as np

from backend.modules.shared.domain.entities.channel_snapshot import ChannelSnapshot
from backend.modules.shared.domain.rules.regression_channel import (
    linreg_channel,
    calc_vwap,
    sigma_position,
)
from backend.modules.shared.domain.rules.cycle_detection import detect_dominant_cycle
from backend.modules.shared.domain.rules.geometric_features import compute_geometric_features


# ── Fear level thresholds (from quality_swing/domain/rules/fear_level.py) ──
# Moved here to avoid importing the full fear_level module and its
# duplicate linreg_channel() calls.
_BULL_SLOPE_MIN = 0.01
_BEAR_SLOPE_MAX = -0.01
_SHALLOW_BEAR_LIMIT = -0.03


def _classify_fear_level(
    tide_slope: float,
    wave_slope: float,
    tide_accel: float,
) -> tuple[int, str]:
    """Classify fear/greed from pre-computed slopes.

    Pure classification — zero regression calls.

    Empirical basis (2026-05-14, 20,580 observations):
      PANIC P(↑)=47.6%, Ret20d=+3.12% (best — contrarian)
      GREED P(↑)=40.4%, Ret20d=+1.26% (worst)
    """
    if tide_slope < -0.02 and wave_slope < -0.05 and tide_accel < 0:
        return 5, "PANIC"
    elif tide_slope < -0.01 and wave_slope <= 0.02:
        return 4, "FEAR"
    elif tide_slope > 0.01 and wave_slope < -0.02:
        return 3, "ANXIETY"
    elif -0.01 <= tide_slope <= 0.01:
        return 2, "NEUTRAL"
    elif tide_slope > 0.01 and wave_slope > 0.02 and tide_accel <= 0:
        return 1, "CONFIDENCE"
    elif tide_slope > 0.02 and wave_slope > 0.05 and tide_accel > 0:
        return 0, "GREED"
    else:
        return 2, "NEUTRAL"


def _classify_regime(tide_slope: float) -> str:
    """Regime classification from tide slope."""
    if tide_slope > _BULL_SLOPE_MIN:
        return "BULL"
    elif tide_slope < _BEAR_SLOPE_MAX:
        return "BEAR"
    return "FLAT"


def _compute_vol_ratio(close: np.ndarray, volume: np.ndarray, idx: int) -> float:
    """Volume UP/DOWN ratio over last 5 bars."""
    if idx < 5:
        return 1.0
    up_vol = 0.0
    down_vol = 0.0
    up_n = 0
    down_n = 0
    for j in range(max(1, idx - 4), idx + 1):
        if close[j] > close[j - 1]:
            up_vol += volume[j]
            up_n += 1
        else:
            down_vol += volume[j]
            down_n += 1
    avg_up = up_vol / max(up_n, 1)
    avg_down = down_vol / max(down_n, 1)
    return avg_up / avg_down if avg_down > 0 else 2.0


def _calc_vwap_with_std(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray,
    window: int,
) -> tuple[float, float]:
    """VWAP + volume-weighted standard deviation.

    Returns:
        (vwap_value, vwap_std) — std used for sigma_vwap computation.
    """
    if len(close) < window:
        val = close[-1] if len(close) > 0 else 0.0
        return val, 1.0

    typical = (close[-window:] + high[-window:] + low[-window:]) / 3.0
    vol = volume[-window:]
    total_vol = vol.sum()

    if total_vol <= 0:
        return float(typical[-1]), 1.0

    vwap = float(np.sum(typical * vol) / total_vol)
    deviations = typical - vwap
    vwap_std = float(np.sqrt(np.sum(vol * deviations ** 2) / total_vol))

    return vwap, max(vwap_std, 1e-8)


def compute_channel_snapshot(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray,
    idx: int,
    tide_window: int = 240,
    current_window: int = 60,
    wave_window: int | None = None,
) -> ChannelSnapshot | None:
    """Compute complete channel snapshot at bar index `idx`.

    This is the SINGLE entry point for all regression + VWAP computations.
    Call this ONCE per bar, pass the result to all downstream consumers.

    Args:
        close: Full array of closing prices.
        high: Full array of high prices.
        low: Full array of low prices.
        volume: Full array of volume.
        idx: Bar index to analyze (0-based). Uses data up to and including idx.
        tide_window: Long regression window (default 240, ~1 year).
        current_window: Medium regression window (default 60, ~quarter).
        wave_window: Short regression window. None = auto-detect via
                     dominant cycle (autocorrelation on returns).

    Returns:
        ChannelSnapshot with all derivatives, or None if insufficient data.
    """
    if idx < tide_window + 5:
        return None

    price_now = close[idx]
    pw = close[: idx + 1]       # price window up to current bar
    pw_prev = close[: idx]      # price window up to previous bar

    # ── Cycle detection (once, shared by regression + VWAP) ──
    if wave_window is None:
        wave_window = max(10, min(detect_dominant_cycle(close), 60))

    snap = ChannelSnapshot(
        tide_window=tide_window,
        current_window=current_window,
        wave_window=wave_window,
    )

    # ══════════════════════════════════════════════════════════
    # TRIPLE REGRESSION — 3 lines, current bar
    # ══════════════════════════════════════════════════════════
    tide_val, tide_slope, tide_std = linreg_channel(pw, tide_window)
    curr_val, curr_slope, curr_std = linreg_channel(pw, current_window)
    wave_val, wave_slope, wave_std = linreg_channel(pw, wave_window)

    # Regression values
    snap.reg_value_tide = round(tide_val, 2)
    snap.reg_value_current = round(curr_val, 2)
    snap.reg_value_wave = round(wave_val, 2)

    # Residual stds (channel width)
    snap.residual_std_tide = round(tide_std, 4)
    snap.residual_std_current = round(curr_std, 4)
    snap.residual_std_wave = round(wave_std, 4)

    # Slopes
    snap.tide_slope = round(tide_slope, 6)
    snap.current_slope = round(curr_slope, 6)
    snap.wave_slope = round(wave_slope, 6)

    # Sigmas
    snap.sigma_tide = round(sigma_position(price_now, tide_val, tide_std), 4)
    snap.sigma_current = round(sigma_position(price_now, curr_val, curr_std), 4)
    snap.sigma_wave = round(sigma_position(price_now, wave_val, wave_std), 4)

    # ══════════════════════════════════════════════════════════
    # TRIPLE REGRESSION — 3 lines, previous bar (for accel + flip)
    # ══════════════════════════════════════════════════════════
    if idx > tide_window + 6 and len(pw_prev) >= tide_window:
        _, tide_slope_p, _ = linreg_channel(pw_prev, tide_window)
        _, curr_slope_p, _ = linreg_channel(pw_prev, current_window)
        _, wave_slope_p, _ = linreg_channel(pw_prev, wave_window)

        snap.tide_accel = round(tide_slope - tide_slope_p, 6)
        snap.current_accel = round(curr_slope - curr_slope_p, 6)
        snap.wave_accel = round(wave_slope - wave_slope_p, 6)

        # Wave flip detection
        snap.wave_flip = (wave_slope > 0) != (wave_slope_p > 0)
        if snap.wave_flip:
            snap.wave_flip_direction = 1 if wave_slope > 0 else -1

    # ══════════════════════════════════════════════════════════
    # 3 CONJUGATIONS (slope differences between pairs)
    # ══════════════════════════════════════════════════════════
    snap.conj_wave_current = round(wave_slope - curr_slope, 6)
    snap.conj_wave_tide = round(wave_slope - tide_slope, 6)
    snap.conj_current_tide = round(curr_slope - tide_slope, 6)

    # ══════════════════════════════════════════════════════════
    # 3 SIGMA SPREADS (sigma differences between lines)
    # ══════════════════════════════════════════════════════════
    snap.spread_tide_current = round(snap.sigma_tide - snap.sigma_current, 4)
    snap.spread_tide_wave = round(snap.sigma_tide - snap.sigma_wave, 4)
    snap.spread_current_wave = round(snap.sigma_current - snap.sigma_wave, 4)

    # ══════════════════════════════════════════════════════════
    # TRIPLE VWAP — same 3 windows, volume-weighted
    # ══════════════════════════════════════════════════════════
    hw = high[: idx + 1]
    lw = low[: idx + 1]
    vw = volume[: idx + 1]

    vwap_t, vstd_t = _calc_vwap_with_std(pw, hw, lw, vw, tide_window)
    vwap_c, vstd_c = _calc_vwap_with_std(pw, hw, lw, vw, current_window)
    vwap_w, vstd_w = _calc_vwap_with_std(pw, hw, lw, vw, wave_window)

    snap.vwap_tide = round(vwap_t, 2)
    snap.vwap_current = round(vwap_c, 2)
    snap.vwap_wave = round(vwap_w, 2)

    # VWAP sigmas
    snap.vwap_sigma_tide = round(
        (price_now - vwap_t) / vstd_t if vstd_t > 0 else 0.0, 4
    )
    snap.vwap_sigma_current = round(
        (price_now - vwap_c) / vstd_c if vstd_c > 0 else 0.0, 4
    )
    snap.vwap_sigma_wave = round(
        (price_now - vwap_w) / vstd_w if vstd_w > 0 else 0.0, 4
    )

    # VWAP spreads (% difference between VWAP levels)
    snap.vwap_spread_tide_current = round(
        (vwap_t - vwap_c) / max(abs(vwap_t), 1e-8) * 100, 4
    )
    snap.vwap_spread_tide_wave = round(
        (vwap_t - vwap_w) / max(abs(vwap_t), 1e-8) * 100, 4
    )
    snap.vwap_spread_current_wave = round(
        (vwap_c - vwap_w) / max(abs(vwap_c), 1e-8) * 100, 4
    )

    # Composite VWAP flags
    snap.below_all_vwaps = (
        price_now < vwap_t and price_now < vwap_c and price_now < vwap_w
    )
    snap.above_all_vwaps = (
        price_now > vwap_t and price_now > vwap_c and price_now > vwap_w
    )

    # ══════════════════════════════════════════════════════════
    # DERIVED: Fear/Greed, Regime, Volume
    # ══════════════════════════════════════════════════════════
    snap.fear_level, snap.fear_label = _classify_fear_level(
        tide_slope, wave_slope, snap.tide_accel,
    )
    snap.regime = _classify_regime(tide_slope)
    snap.vol_up_down_ratio = round(
        _compute_vol_ratio(close, volume, idx), 2
    )

    # ══════════════════════════════════════════════════════════
    # TENSIONS: Reg σ minus VWAP σ (Wyckoff cross-type)
    # ══════════════════════════════════════════════════════════
    snap.tension_tide = round(snap.sigma_tide - snap.vwap_sigma_tide, 4)
    snap.tension_current = round(snap.sigma_current - snap.vwap_sigma_current, 4)
    snap.tension_wave = round(snap.sigma_wave - snap.vwap_sigma_wave, 4)

    # ══════════════════════════════════════════════════════════
    # COMPRESSION RATIO (Mandelbrot squeeze)
    # ══════════════════════════════════════════════════════════
    snap.compression_ratio = round(
        snap.residual_std_wave / snap.residual_std_tide
        if snap.residual_std_tide > 0.01 else 0.0,
        4,
    )

    # ══════════════════════════════════════════════════════════
    # DUAL PROB FEATURES: vol_surge
    # ══════════════════════════════════════════════════════════
    # vol_surge: volume / SMA(volume, 20) — capitulation intensity
    if idx >= 19 and len(volume) >= 20:
        sma20 = float(volume[max(0, idx - 19):idx + 1].mean())
        snap.vol_surge = round(volume[idx] / sma20, 4) if sma20 > 0 else 1.0
    else:
        snap.vol_surge = 1.0

    # w_duration: computed during sequential backfill/daemon processing.
    # Not computed here (would require O(60) regressions per bar).
    # Default = 1, updated externally when processing bars sequentially.

    # ══════════════════════════════════════════════════════════
    # GEOMETRIC FEATURES (3D vector projections)
    # slope_stds not available in single-bar computation — uses raw slopes.
    # Backfill and daemon supply slope_stds for proper normalization.
    # ══════════════════════════════════════════════════════════
    (
        snap.geo_state_norm,
        snap.geo_velocity_align,
        snap.geo_exit_align,
        snap.geo_accel_align,
        snap.geo_phase_angle,
    ) = compute_geometric_features(
        snap.sigma_tide, snap.sigma_current, snap.sigma_wave,
        snap.tide_slope, snap.current_slope, snap.wave_slope,
        snap.tide_accel, snap.current_accel, snap.wave_accel,
        slope_stds=None,  # No rolling stds in single-bar mode
    )

    return snap

