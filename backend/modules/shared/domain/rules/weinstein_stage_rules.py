"""
Weinstein Stage Rules — Shared Pure Domain Rule
===================================================
Classifies asset/ETF price series into Weinstein Stages (1-4):
  - Stage 1: Basing (oscillating, flat MA)
  - Stage 2: Advancing (price > MA150, rising MA slope, positive RS)
  - Stage 3: Topping (price oscillating around flattening/declining MA)
  - Stage 4: Declining (price < MA150, falling MA slope)

Pure Python — zero I/O, zero side-effects.
"""
from typing import Sequence


def classify_weinstein_stage(prices: Sequence[float], rs: float = 0.0) -> int:
    """
    Classifies prices into Weinstein Stage (1-4).

    Args:
        prices: Sequence of daily close prices (at least 150 bars required).
        rs: Relative strength vs benchmark (-1.0 to 1.0).

    Returns:
        1: Basing, 2: Advancing, 3: Topping, 4: Declining, 0: Insufficient data.
    """
    if not prices or len(prices) < 150:
        return 0

    current_price, ma_150, ma_slope = compute_weinstein_ma_metrics(prices)

    if current_price > ma_150 and ma_slope > 0 and rs > 0.1:
        return 2  # Advancing
    elif current_price > ma_150 and ma_slope <= 0:
        return 3  # Topping
    elif current_price < ma_150 and ma_slope < 0:
        return 4  # Declining
    else:
        return 1  # Basing


def compute_weinstein_ma_metrics(prices: Sequence[float], window: int = 150) -> tuple[float, float, float]:
    """
    Computes current price, 150-day (30-week) MA, and 20-day MA slope.

    Returns:
        (current_price, ma_150, ma_slope)
    """
    if len(prices) < window:
        curr = prices[-1] if prices else 0.0
        return curr, curr, 0.0

    current_price = float(prices[-1])
    ma_150 = float(sum(prices[-window:]) / window)

    # 20-day recent average vs prior 20-day average
    recent_20 = sum(prices[-20:]) / 20.0
    prior_20 = sum(prices[-40:-20]) / 20.0
    ma_slope = float(recent_20 - prior_20)

    return current_price, ma_150, ma_slope
