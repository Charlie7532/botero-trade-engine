"""
Regression Channel — Pure Statistical Functions
==================================================
Linear regression channel and VWAP calculations extracted from
RegressionChannelAdapter. These are pure math functions with no
side effects, no I/O, and no external dependencies beyond numpy.

Used by:
  - RegressionChannelAdapter (simulation/infrastructure) — for Oracle backtest
  - SwingGate (quality_swing/application) — for production entry decisions
  - compute_ticker_fear_level (quality_swing/domain/rules) — for fear/greed bias

Statistical basis:
    68% of prices within ±1σ → normal fluctuation
    95% within ±2σ → entry at -1.5σ to -2σ = 2.5th-16th percentile
"""
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


def calc_vwap(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray,
    window: int = 20,
) -> float:
    """Rolling VWAP over last `window` bars.

    Args:
        close, high, low, volume: Price/volume arrays.
        window: Lookback period (default 20).

    Returns:
        VWAP value for the last `window` bars.
    """
    if len(close) < window:
        return close[-1] if len(close) > 0 else 0.0

    typical = (close[-window:] + high[-window:] + low[-window:]) / 3.0
    vol = volume[-window:]
    total_vol = vol.sum()
    if total_vol <= 0:
        return typical[-1]
    return float(np.sum(typical * vol) / total_vol)


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
