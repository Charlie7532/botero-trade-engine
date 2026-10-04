"""
Regression Channel — Pure Statistical Functions
==================================================
Linear regression channel and VWAP calculations. Pure math functions
with no side effects, no I/O, and no external dependencies beyond numpy.

Canonical location: shared/domain/rules/regression_channel.py
Backward-compat re-export: quality_swing/domain/rules/regression_channel.py

Used by:
  - compute_channel_snapshot (shared/domain/rules) — triple regression
  - RegressionChannelIntelligence (price_analysis) — zone/action interpretation
  - compute_ticker_fear_level (quality_swing) — fear/greed classification
  - OracleTrainer (simulation) — forensic labeling


Statistical basis:
    68% of prices within ±1σ → normal fluctuation
    95% within ±2σ → entry at -1.5σ to -2σ = 2.5th-16th percentile
"""
from typing import Optional

import numpy as np


def linreg_channel(close: np.ndarray, window: int) -> tuple[float, float, float]:
    """Compute linear regression line and standard deviation of residuals.

    Args:
        close: Array of closing prices.
        window: Number of bars to use for regression.

    Returns:
        (reg_value, slope_normalized, residual_std) at the last bar.
        - reg_value: regression line value at the last bar
        - slope_normalized: slope as % of mean price per bar
        - residual_std: standard deviation of residuals (σ band width)
    """
    if len(close) < window:
        return 0.0, 0.0, 1.0

    y = close[-window:]
    x = np.arange(window, dtype=float)
    x_mean = x.mean()
    y_mean = y.mean()

    ss_xx = np.sum((x - x_mean) ** 2)
    ss_xy = np.sum((x - x_mean) * (y - y_mean))

    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean

    # Regression line value at the last bar
    reg_line = slope * (window - 1) + intercept

    # Standard deviation of residuals (distance from the line)
    fitted = slope * x + intercept
    residuals = y - fitted
    residual_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 1.0

    # Normalize slope by mean price
    slope_norm = (slope / y_mean * 100) if y_mean > 0 else 0.0

    return reg_line, slope_norm, max(residual_std, 1e-8)


def calc_vwap_with_std(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray,
    window: int,
) -> tuple[Optional[float], Optional[float]]:
    """CANONICAL VWAP kernel: VWAP + volume-weighted standard deviation.

    Single source of truth for the VWAP math. Do not re-implement elsewhere.

    Returns (None, None) when uncomputable (fewer than `window` bars, or the
    window carries no volume). Never fabricates a level (no typical[-1]).

    Bar Taxonomy & C2 Behavior:
        - Zero-volume bars weigh 0, so they are excluded per bar automatically.
        - C2 (O=H=L=C, vol > 0): typical=(H+L+C)/3 == C, so the VWAP is exact.
          CARENCIA: C2 bars provide no intraday range (H - L = 0). Any feature
          relying on High - Low (ATR, Parkinson vol) MUST exclude C2 bars.
    """
    if len(close) < window:
        return None, None

    vol = volume[-window:]
    total_vol = vol.sum()

    if total_vol <= 0:
        return None, None

    typical = (close[-window:] + high[-window:] + low[-window:]) / 3.0
    vwap = float(np.sum(typical * vol) / total_vol)
    deviations = typical - vwap
    vwap_std = float(np.sqrt(np.sum(vol * deviations ** 2) / total_vol))

    return vwap, vwap_std


def calc_vwap(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray,
    window: int = 20,
) -> Optional[float]:
    """Rolling VWAP over last `window` bars (level only).

    Delegates to calc_vwap_with_std. Returns None when uncomputable —
    callers must handle None (formerly returned typical[-1] / close[-1],
    a fabricated level).
    """
    return calc_vwap_with_std(close, high, low, volume, window)[0]


def sigma_position(current_price: float, reg_value: float, residual_std: float) -> float:
    """Price position in σ units within the regression channel.

    Args:
        current_price: Current close price.
        reg_value: Regression line value at current bar.
        residual_std: Standard deviation of residuals.

    Returns:
        Position in σ units. Negative = below channel center (cheap).
        -1.5 to -2.0 = statistical support zone (entry territory).
        +1.5 to +2.0 = statistical resistance zone (trim territory).
    """
    if residual_std <= 0:
        return 0.0
    return (current_price - reg_value) / residual_std
