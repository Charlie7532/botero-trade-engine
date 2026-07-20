"""
Volume Breadth Calculator — SV5 Indicators
=============================================
Pure domain rule — no infrastructure dependencies.

Calculates % of tickers where a fast volume MA exceeds a slow volume MA.
Nested design produces 3 independent layers:

    SV5TW (tactical):      EMA(5, vol)  > SMA(20, vol)
    SV5FI (intermediate):  SMA(20, vol) > SMA(50, vol)
    SV5TH (structural):    SMA(50, vol) > SMA(200, vol)

Each layer uses a different fast/slow pair, ensuring low internal
correlation (~0.04) vs the flat design (~0.90).

CRITICAL INTERPRETATION:
    SV5 measures CONVICTION / PARTICIPATION, NOT direction.
    High SV5 = many stocks with elevated volume = strong participation.
    But elevated volume can be BUYING or SELLING.

    Must ALWAYS cross-reference SV5 with S5 (price breadth) for direction:
        S5 ↗ + SV5 ↗ = Rally with conviction (buyers aggressive)
        S5 ↗ + SV5 ↘ = Rally without conviction (vulnerable)
        S5 ↘ + SV5 ↗ = Sell-off with conviction (sellers aggressive)
        S5 ↘ + SV5 ↘ = Apathetic drift (no urgency)

    SV5 alone is DIRECTIONLESS. Never interpret SV5 rising as bullish
    or SV5 falling as bearish without checking the corresponding S5.
"""
from __future__ import annotations

from typing import Optional

import numpy as np


def _sma(data: list[float], length: int) -> Optional[float]:
    """Simple moving average of the last `length` values."""
    if len(data) < length:
        return None
    return float(np.mean(data[-length:]))


def _ema(data: list[float], span: int) -> Optional[float]:
    """Exponential moving average using the last values.

    Uses the standard EMA recurrence with alpha = 2/(span+1).
    Initialises with the SMA of the first `span` values.
    """
    if len(data) < span:
        return None
    alpha = 2.0 / (span + 1)
    # Initialise with SMA of first `span` points
    ema_val = float(np.mean(data[:span]))
    for val in data[span:]:
        ema_val = alpha * val + (1 - alpha) * ema_val
    return ema_val


def calculate_volume_breadth(
    all_volumes: dict[str, list[float]],
    fast_length: int,
    slow_length: int,
    fast_type: str = "sma",
) -> Optional[float]:
    """
    Calculate % of tickers where fast volume MA > slow volume MA.

    Args:
        all_volumes: {ticker: [vol_day1, vol_day2, ...]} chronologically ordered.
        fast_length: Window for the fast MA (5, 20, or 50).
        slow_length: Window for the slow MA (20, 50, or 200).
        fast_type:   "sma" or "ema" for the fast MA calculation.

    Returns:
        Percentage (0-100) of tickers with fast MA > slow MA,
        or None if insufficient data.
    """
    above = 0
    total = 0

    ma_fn = _ema if fast_type == "ema" else _sma

    for ticker, volumes in all_volumes.items():
        if len(volumes) < slow_length:
            continue

        fast_val = ma_fn(volumes, fast_length)
        slow_val = _sma(volumes, slow_length)

        if fast_val is not None and slow_val is not None and slow_val > 0:
            total += 1
            if fast_val > slow_val:
                above += 1

    if total == 0:
        return None

    return round(above / total * 100, 1)


def calculate_all_volume_breadth(
    all_volumes: dict[str, list[float]],
) -> dict[str, Optional[float]]:
    """
    Calculate all 3 SV5 layers in one pass.

    Returns:
        {"sv5tw": float|None, "sv5fi": float|None, "sv5th": float|None}
    """
    from backend.modules.shared.domain.constants.sectors import VOLUME_BREADTH_MA_CONFIG

    results = {}
    for layer_key, config in VOLUME_BREADTH_MA_CONFIG.items():
        results[layer_key] = calculate_volume_breadth(
            all_volumes,
            fast_length=config["fast"],
            slow_length=config["slow"],
            fast_type=config["fast_type"],
        )
    return results
