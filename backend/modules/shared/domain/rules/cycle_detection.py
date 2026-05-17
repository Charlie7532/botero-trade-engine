"""
Dominant Cycle Detection — Pure Statistical Function
======================================================
Detects the dominant price cycle period via autocorrelation on log-returns.

The 'wave on the tide': each asset oscillates at its own frequency.
We find the lag with the strongest positive autocorrelation peak
within [min_period, max_period].

Used by:
  - RSISignalAdapter (simulation/infrastructure) — RSI lookback = cycle / 2
  - RegressionChannelAdapter (simulation/infrastructure) — short regression window
  - compute_ticker_fear_level (quality_swing/domain/rules) — wave regression window

No external dependencies beyond numpy.
"""
import numpy as np


def detect_dominant_cycle(
    close: np.ndarray,
    min_period: int = 8,
    max_period: int = 50,
) -> int:
    """Detect dominant cycle period via autocorrelation on returns.

    Args:
        close: Array of closing prices.
        min_period: Minimum cycle period to search (default 8).
        max_period: Maximum cycle period to search (default 50).

    Returns:
        Dominant cycle period in bars. Default 28 (~monthly) if
        insufficient data or no meaningful cycle detected.
    """
    if len(close) < max_period * 3:
        return 28  # Default: ~28 day cycle → RSI-14

    returns = np.diff(np.log(close[-max_period * 3:]))
    n = len(returns)
    returns_dm = returns - returns.mean()

    # Autocorrelation for lags in [min_period, max_period]
    autocorr = np.zeros(max_period + 1)
    var = np.sum(returns_dm ** 2)
    if var == 0:
        return 28

    for lag in range(min_period, max_period + 1):
        autocorr[lag] = np.sum(returns_dm[:n - lag] * returns_dm[lag:]) / var

    # Find the lag with highest positive autocorrelation
    best_lag = min_period
    best_corr = -1.0
    for lag in range(min_period, max_period + 1):
        if autocorr[lag] > best_corr:
            best_corr = autocorr[lag]
            best_lag = lag

    # If no meaningful cycle found (correlation too weak), use default
    if best_corr < 0.02:
        return 28

    return best_lag
