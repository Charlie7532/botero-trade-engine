"""
Macro Trend Calculator — Pure Domain Rule
==========================================
Converts raw time-series data into IndicatorTrend objects
and calculates market breadth (S5TH, S5TW) from OHLCV bars.

No external dependencies — stdlib + numpy only.
"""
import logging
from typing import Optional

import numpy as np

from backend.modules.shared.domain.entities.indicator_trend import IndicatorTrend

logger = logging.getLogger(__name__)


def calculate_trend(name: str, history: list[tuple[str, float]]) -> IndicatorTrend:
    """
    Convert a list of (date_str, value) into an IndicatorTrend.

    Args:
        name: Indicator name ("VIX", "VVIX", "FEAR_GREED", etc.)
        history: Chronologically ordered [(date, value), ...].
                 Minimum 2 points for delta calculation.

    Returns:
        IndicatorTrend with all fields populated.
    """
    if not history:
        return IndicatorTrend(name=name, current=0.0)

    values = [v for _, v in history]
    current = values[-1]

    if len(values) < 2:
        return IndicatorTrend(name=name, current=current)

    previous = values[-2]
    delta_1d = current - previous

    # Delta 5d
    delta_5d = current - values[-6] if len(values) >= 6 else current - values[0]

    # Moving averages
    ma5 = float(np.mean(values[-5:])) if len(values) >= 5 else float(np.mean(values))
    ma20 = float(np.mean(values[-20:])) if len(values) >= 20 else float(np.mean(values))

    # Direction (based on last 3 days to avoid noise)
    if len(values) >= 3:
        recent_deltas = [values[i] - values[i - 1] for i in range(-2, 0)]
        recent_deltas.append(delta_1d)
        avg_delta = sum(recent_deltas) / len(recent_deltas)
        if avg_delta > 0.01 * current:  # >1% avg daily move
            direction = "RISING"
        elif avg_delta < -0.01 * current:
            direction = "FALLING"
        else:
            direction = "FLAT"
    else:
        direction = "RISING" if delta_1d > 0 else ("FALLING" if delta_1d < 0 else "FLAT")

    # Trend (based on MA crossover)
    if ma5 > ma20 * 1.005:
        trend = "BULLISH"
    elif ma5 < ma20 * 0.995:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    # Days of trend (consecutive days in same direction)
    days_of_trend = 0
    if len(values) >= 2:
        for i in range(len(values) - 1, 0, -1):
            d = values[i] - values[i - 1]
            if direction == "RISING" and d > 0:
                days_of_trend += 1
            elif direction == "FALLING" and d < 0:
                days_of_trend += 1
            else:
                break

    # Percentile within the history (use up to 90 days)
    window = values[-90:] if len(values) >= 90 else values
    percentile_90d = float(np.sum(np.array(window) <= current) / len(window) * 100)

    return IndicatorTrend(
        name=name,
        current=round(current, 4),
        previous=round(previous, 4),
        delta_1d=round(delta_1d, 4),
        delta_5d=round(delta_5d, 4),
        ma5=round(ma5, 4),
        ma20=round(ma20, 4),
        direction=direction,
        trend=trend,
        days_of_trend=days_of_trend,
        percentile_90d=round(percentile_90d, 1),
    )


def calculate_breadth(
    all_closes: dict[str, list[float]],
    ma_length: int,
) -> Optional[float]:
    """
    Calculate % of tickers trading above their moving average.

    S5TH: ma_length=200 (% above 200-DMA) — structural
    S5FI: ma_length=50  (% above 50-DMA)  — intermediate
    S5TW: ma_length=20  (% above 20-DMA)  — tactical

    Args:
        all_closes: {ticker: [close_day1, close_day2, ...]} chronologically ordered.
        ma_length: Moving average window (200 for S5TH, 50 for S5FI, 20 for S5TW).

    Returns:
        Percentage (0-100) of tickers above their MA, or None if insufficient data.
    """
    above = 0
    total = 0

    for ticker, closes in all_closes.items():
        if len(closes) < ma_length:
            continue

        ma = float(np.mean(closes[-ma_length:]))
        current = closes[-1]

        if ma > 0:
            total += 1
            if current > ma:
                above += 1

    if total == 0:
        return None

    return round(above / total * 100, 1)
