"""
RSI Calculation — Pure Mathematical Function
==============================================
Wilder's RSI series computation extracted as a standalone function.

Used by:
  - RSISignalAdapter (simulation/infrastructure) — signal generation
  - RegressionChannelAdapter (simulation/infrastructure) — via RSI adapter
  - OracleTrainer (simulation/application) — snapshot building
  - QuantFeatureEngineer (simulation/application) — feature pipeline

No external dependencies beyond numpy.
"""
import numpy as np


def calc_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Calculate full RSI series using Wilder's exponential smoothing.

    Args:
        close: Array of closing prices.
        period: RSI period (default 14).

    Returns:
        RSI series (0-100) aligned with input close array.
        First `period` values are set to 50.0 (unreliable).
    """
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.zeros(len(gains))
    avg_loss = np.zeros(len(gains))

    if len(gains) < period:
        return np.full(len(close), 50.0)

    avg_gain[period - 1] = np.mean(gains[:period])
    avg_loss[period - 1] = np.mean(losses[:period])

    for i in range(period, len(gains)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period

    with np.errstate(divide='ignore', invalid='ignore'):
        rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100.0)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi[:period] = 50.0
    # Prepend one value so rsi aligns with close (np.diff removes one element)
    return np.concatenate(([50.0], rsi))
