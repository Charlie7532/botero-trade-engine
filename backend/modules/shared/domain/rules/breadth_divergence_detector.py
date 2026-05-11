"""
Breadth Divergence Detector — Pure Domain Rule
=================================================
Detects divergences between breadth trend and price trend using
dual-timeframe linear regression slopes.

When breadth rises but price falls → BULLISH_DIV (stealth accumulation)
When breadth falls but price rises → BEARISH_DIV (fragile, narrow)

No external dependencies — stdlib + numpy only.
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class BreadthDivergence:
    """Result of divergence analysis between breadth and price."""
    ticker: str                       # "SPY", "XLK", etc.
    breadth_slope_20d: float = 0.0    # Short-term breadth trend (per day)
    breadth_slope_60d: float = 0.0    # Long-term breadth trend (per day)
    price_slope_20d: float = 0.0      # Short-term price trend (% per day)
    price_slope_60d: float = 0.0      # Long-term price trend (% per day)
    divergence_score: float = 0.0     # -1 to +1 (neg=narrowing, pos=broadening)
    divergence_type: str = "NEUTRAL"  # BULLISH_DIV, BEARISH_DIV, CONFIRMING, NEUTRAL
    concentration_flag: bool = False  # True if move is led by few stocks
    leading_subsector: Optional[str] = None  # Which sub-sector drives the anomaly


def compute_slope(series: list[float], window: int) -> float:
    """Compute linear regression slope of the last `window` values.

    Returns slope in units-per-day. Returns 0.0 if insufficient data.
    """
    if len(series) < window:
        return 0.0

    y = np.array(series[-window:], dtype=float)
    x = np.arange(len(y), dtype=float)

    # Remove NaN
    mask = ~np.isnan(y)
    if mask.sum() < max(window // 2, 5):
        return 0.0

    x_clean = x[mask]
    y_clean = y[mask]

    n = len(x_clean)
    x_mean = x_clean.mean()
    y_mean = y_clean.mean()

    denom = (x_clean * x_clean).sum() - n * x_mean * x_mean
    if abs(denom) < 1e-10:
        return 0.0

    slope = ((x_clean * y_clean).sum() - n * x_mean * y_mean) / denom
    return float(slope)


def normalize_price_slope(prices: list[float], window: int) -> float:
    """Compute price slope normalized by price level (% per day)."""
    if len(prices) < window or prices[-window] <= 0:
        return 0.0

    slope = compute_slope(prices, window)
    base_price = np.mean(prices[-window:])
    if base_price <= 0:
        return 0.0

    return slope / base_price * 100  # % per day


def detect_divergence(
    ticker: str,
    breadth_history: list[float],
    price_history: list[float],
    short_window: int = 20,
    long_window: int = 60,
    threshold: float = 0.05,
) -> BreadthDivergence:
    """
    Detect divergence between breadth and price.

    Args:
        ticker: Symbol for this analysis (SPY, XLK, etc.)
        breadth_history: Historical breadth values (% above MA, 0-100)
        price_history: Historical ETF/index prices
        short_window: Tactical slope window (default 20 days)
        long_window: Structural slope window (default 60 days)
        threshold: Minimum slope magnitude to consider non-neutral

    Returns:
        BreadthDivergence with all fields populated.
    """
    b_slope_20 = compute_slope(breadth_history, short_window)
    b_slope_60 = compute_slope(breadth_history, long_window)
    p_slope_20 = normalize_price_slope(price_history, short_window)
    p_slope_60 = normalize_price_slope(price_history, long_window)

    # Classification based on short-term slopes (tactical divergence)
    div_type = _classify(b_slope_20, p_slope_20, threshold)

    # Divergence score: negative = narrowing, positive = broadening
    # Combines both timeframes with short-term weighted more
    score_short = _divergence_sign(b_slope_20, p_slope_20, threshold)
    score_long = _divergence_sign(b_slope_60, p_slope_60, threshold)
    div_score = 0.7 * score_short + 0.3 * score_long
    div_score = max(-1.0, min(1.0, div_score))

    # Concentration flag: price rising but breadth falling significantly
    concentration = (p_slope_20 > threshold and b_slope_20 < -threshold * 2)

    return BreadthDivergence(
        ticker=ticker,
        breadth_slope_20d=round(b_slope_20, 4),
        breadth_slope_60d=round(b_slope_60, 4),
        price_slope_20d=round(p_slope_20, 4),
        price_slope_60d=round(p_slope_60, 4),
        divergence_score=round(div_score, 3),
        divergence_type=div_type,
        concentration_flag=concentration,
    )


def _classify(breadth_slope: float, price_slope: float, threshold: float) -> str:
    """Classify divergence type from slope pair."""
    b_up = breadth_slope > threshold
    b_down = breadth_slope < -threshold
    p_up = price_slope > threshold
    p_down = price_slope < -threshold

    if p_up and b_down:
        return "BEARISH_DIV"
    if p_down and b_up:
        return "BULLISH_DIV"
    if (p_up and b_up) or (p_down and b_down):
        return "CONFIRMING"
    return "NEUTRAL"


def _divergence_sign(breadth_slope: float, price_slope: float, threshold: float) -> float:
    """Return a signed value: positive = broadening, negative = narrowing."""
    if abs(breadth_slope) < threshold and abs(price_slope) < threshold:
        return 0.0

    # Breadth rising relative to price = positive (broadening)
    if abs(price_slope) > 0.001:
        return (breadth_slope - price_slope) / abs(price_slope)

    return breadth_slope * 10  # Price flat, breadth moving


def drill_down_subsectors(
    sector: str,
    industry_closes: dict[str, dict[str, list[float]]],
    ma_length: int = 20,
) -> dict:
    """
    On-demand sub-sector drill-down triggered when divergence is detected.

    Instead of calculating breadth for all 110 sub-sectors every cycle,
    this only runs when a sector shows BEARISH_DIV or BULLISH_DIV.

    Args:
        sector: Canonical sector name
        industry_closes: {industry: {ticker: [closes...]}}
        ma_length: MA window for breadth calculation

    Returns:
        {
            "top_subsector": str,
            "top_breadth": float,
            "bottom_subsector": str,
            "bottom_breadth": float,
            "subsector_breadths": {industry: pct},
        }
    """
    from backend.modules.shared.domain.rules.macro_trend_calculator import calculate_breadth

    breadths: dict[str, float] = {}

    for industry, closes_dict in industry_closes.items():
        # Need at least 3 tickers for meaningful sub-sector breadth
        if len(closes_dict) < 3:
            continue

        pct = calculate_breadth(closes_dict, ma_length)
        if pct is not None:
            breadths[industry] = pct

    if not breadths:
        return {
            "top_subsector": "",
            "top_breadth": 0.0,
            "bottom_subsector": "",
            "bottom_breadth": 0.0,
            "subsector_breadths": {},
        }

    top = max(breadths, key=breadths.get)
    bottom = min(breadths, key=breadths.get)

    return {
        "top_subsector": top,
        "top_breadth": breadths[top],
        "bottom_subsector": bottom,
        "bottom_breadth": breadths[bottom],
        "subsector_breadths": breadths,
    }
