"""
Trend Strength & Accumulation/Distribution — Pure Domain Rules
================================================================
Converts raw slope/tension values into normalized 0-100 indices
using per-ticker calibrated percentile tables.

TSI (Trend Strength Index):
  0 = Extreme Bear (deepest historical decline)
  50 = Median for this ticker (NOT zero slope — markets have bull bias)
  100 = Extreme Bull (strongest historical advance)

ADI (Accumulation/Distribution Index):
  0 = Strong Accumulation (price far below institutional VWAP)
  50 = Equilibrium (price ≈ VWAP)
  100 = Strong Distribution (price far above institutional VWAP)

Key finding (2026-05-23, 93,776 observations):
  - BEAR + ADI < 20 (accumulation) = WR 72.4%, ret +3.83%
  - This is the best edge in the entire dataset.

Each ticker has its own percentile table because volatilities
differ radically:
  - AAPL: std(tide_slope) = 0.195
  - PEP:  std(tide_slope) = 0.052
  - Same slope means very different things.

No external dependencies beyond numpy. Pure domain rule.
"""
import numpy as np


def compute_tsi(slope: float, percentiles: np.ndarray | list) -> int:
    """Trend Strength Index: 0-100 based on per-ticker percentile.

    Args:
        slope: Current slope value from one regression (tide/current/wave).
        percentiles: Array of 101 slope thresholds (P0..P100) for this
                     ticker and regression, from TickerProfile.

    Returns:
        Integer 0-100. Higher = stronger uptrend relative to this
        ticker's own history.
    """
    if not len(percentiles):
        return 50
    arr = np.asarray(percentiles, dtype=float)
    return int(np.clip(np.searchsorted(arr, slope, side="right"), 0, 100))


def compute_adi(tension: float, percentiles: np.ndarray | list) -> int:
    """Accumulation/Distribution Index: 0-100 based on per-ticker percentile.

    Tension = sigma_regression - sigma_vwap.
    Negative tension = price below institutional VWAP = accumulation.
    Positive tension = price above institutional VWAP = distribution.

    Args:
        tension: Current tension value for one regression.
        percentiles: Array of 101 tension thresholds (P0..P100) for this
                     ticker and regression, from TickerProfile.

    Returns:
        Integer 0-100. Lower = stronger accumulation, higher = stronger
        distribution.
    """
    if not len(percentiles):
        return 50
    arr = np.asarray(percentiles, dtype=float)
    return int(np.clip(np.searchsorted(arr, tension, side="right"), 0, 100))


def compute_all_tsi_adi(
    snapshot,
    profile,
) -> dict[str, int]:
    """Compute all 6 TSI/ADI values from snapshot + profile.

    Args:
        snapshot: ChannelSnapshot with slope and tension fields.
        profile: TickerProfile with calibrated percentile tables.

    Returns:
        Dict with keys: tsi_tide, tsi_current, tsi_wave,
                         adi_tide, adi_current, adi_wave.
        Each value is int 0-100.
    """
    return {
        "tsi_tide": compute_tsi(
            snapshot.tide_slope, profile.tsi_tide_percentiles),
        "tsi_current": compute_tsi(
            snapshot.current_slope, profile.tsi_current_percentiles),
        "tsi_wave": compute_tsi(
            snapshot.wave_slope, profile.tsi_wave_percentiles),
        "adi_tide": compute_adi(
            snapshot.tension_tide, profile.adi_tide_percentiles),
        "adi_current": compute_adi(
            snapshot.tension_current, profile.adi_current_percentiles),
        "adi_wave": compute_adi(
            snapshot.tension_wave, profile.adi_wave_percentiles),
    }
