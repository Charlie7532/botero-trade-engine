"""
Ticker Fear Level — Per-Ticker Contrarian Sentiment Bias
==========================================================
Computes per-ticker fear/greed bias from dual regression channel slopes.

This is a BIAS, not a signal. It modulates conviction of existing signals
(RC, RSI) using the contrarian Buffett/Munger principle: high fear = high
opportunity (provided the moat is intact and the knife stopped falling).

Empirical forensic audit (2026-05-14, 20 tickers × 5 years = 20,580 obs):
  GREED (tide+wave up+accel) → P(↑)=40.4%, Ret20d=+1.26% (worst)
  PANIC (tide+wave down+accel) → P(↑)=47.6%, Ret20d=+3.12% (best)
  Wave FLIP → 8.6% spread in P(↑) — most discriminative feature

No external dependencies beyond numpy/pandas.
"""
import numpy as np
import pandas as pd

from backend.modules.quality_swing.domain.entities.swing_bias import TickerSentimentBias
from backend.modules.quality_swing.domain.rules.regression_channel import linreg_channel
from backend.modules.shared.domain.rules.cycle_detection import detect_dominant_cycle


def compute_ticker_fear_level(
    ohlc: pd.DataFrame,
    idx: int,
    long_window: int = 200,
    short_window: int | None = None,
) -> TickerSentimentBias | None:
    """Compute per-ticker fear/greed bias from regression channel slopes.

    Args:
        ohlc: DataFrame with 'close', 'high', 'low', 'volume' columns.
        idx: Current bar index (iloc position).
        long_window: Bars for the tide regression (default 200).
        short_window: Bars for the wave regression (auto-detected if None).

    Returns:
        TickerSentimentBias or None if insufficient data.
    """
    if idx < long_window + 5:
        return None

    close = ohlc["close"].values.astype(float)
    price_window = close[:idx + 1]
    price_window_prev = close[:idx]

    # Auto-detect cycle for short window
    if short_window is None:
        short_window = max(10, min(
            detect_dominant_cycle(close), 60
        ))

    # Current slopes
    reg_value, tide_slope, res_std = linreg_channel(price_window, long_window)
    _, wave_slope, _ = linreg_channel(price_window, short_window)

    # Previous bar slopes (for acceleration and flip detection)
    _, tide_slope_prev, _ = linreg_channel(price_window_prev, long_window)
    _, wave_slope_prev, _ = linreg_channel(price_window_prev, short_window)

    # Derived metrics
    tide_accel = tide_slope - tide_slope_prev
    wave_flip = (wave_slope > 0) != (wave_slope_prev > 0)
    wave_flip_dir = 0
    if wave_flip:
        wave_flip_dir = 1 if wave_slope > 0 else -1

    sig_pos = (close[idx] - reg_value) / res_std if res_std > 0 else 0.0

    # Slope conjugation: the angle between the two regression lines
    # Feature J11 (MTF_SlopeConjugation_5): ranked #11 global, spread -6.7%
    # Negative = wave falling while tide rising → PULLBACK (entry zone, WR=100% THESIS)
    # Positive = wave rising vs tide → MOMENTUM (hold)
    # Very positive (>0.10) = parabolic → EXHAUSTION (trim zone)
    slope_conj = wave_slope - tide_slope

    # ── FEAR LEVEL CLASSIFICATION ──
    # Based on empirical P(↑) ranking:
    #   PANIC > FEAR > ANXIETY > NEUTRAL > CONFIDENCE > GREED
    if tide_slope < -0.02 and wave_slope < -0.05 and tide_accel < 0:
        fear_level, fear_label = 5, "PANIC"
    elif tide_slope < -0.01 and wave_slope <= 0.02:
        fear_level, fear_label = 4, "FEAR"
    elif tide_slope > 0.01 and wave_slope < -0.02:
        fear_level, fear_label = 3, "ANXIETY"
    elif -0.01 <= tide_slope <= 0.01:
        fear_level, fear_label = 2, "NEUTRAL"
    elif tide_slope > 0.01 and wave_slope > 0.02 and tide_accel <= 0:
        fear_level, fear_label = 1, "CONFIDENCE"
    elif tide_slope > 0.02 and wave_slope > 0.05 and tide_accel > 0:
        fear_level, fear_label = 0, "GREED"
    else:
        fear_level, fear_label = 2, "NEUTRAL"

    return TickerSentimentBias(
        fear_level=fear_level,
        fear_label=fear_label,
        tide_slope=tide_slope,
        wave_slope=wave_slope,
        tide_accel=tide_accel,
        wave_flip=wave_flip,
        wave_flip_direction=wave_flip_dir,
        sigma_position=sig_pos,
        slope_conjugation=slope_conj,
    )
