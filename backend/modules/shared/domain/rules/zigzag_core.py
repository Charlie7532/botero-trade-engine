"""
Canonical ZigZag Core Engine — Pure Domain Rules
=================================================
Centralized single source of truth for ZigZag turning point and leg detection.
Zero external infrastructure dependencies (Pure Domain: numpy / pandas).

Two modes:
1. 'points' (zigzag_canonical):
   Used by engine.zigzag_points backfill. Tracks candidate Highs and Lows,
   confirms turn when close crosses candidate extreme by min_pct.
2. 'legs' (zigzag_legs):
   Used by market.zigzag_legs daemon. Generates confirmed directional legs
   with origin, destination, confirmed_at_timestamp, and duration/returns.
"""
from typing import List, Dict, Any, Tuple, Optional, Union
from datetime import datetime
import numpy as np
import pandas as pd


def compute_zigzag_points(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    min_pct: float = 0.05,
) -> List[Tuple[int, str, float]]:
    """
    Canonical zigzag points detector — High for peaks, Low for valleys.
    Confirmation: close crossing the threshold from candidate extreme.
    Returns: List of (index, 'MIN'|'MAX', price) tuples.
    """
    n = len(close)
    if n < 2:
        return []

    pts = []

    # Determine initial direction from first 20 bars
    init_high_idx, init_high_val = 0, high[0]
    init_low_idx, init_low_val = 0, low[0]
    for i in range(1, min(20, n)):
        if high[i] > init_high_val:
            init_high_idx, init_high_val = i, high[i]
        if low[i] < init_low_val:
            init_low_idx, init_low_val = i, low[i]

    if init_high_idx < init_low_idx:
        direction = 1  # Price went up first -> look for MAX
    else:
        direction = -1

    cand_high_idx, cand_high_val = 0, high[0]
    cand_low_idx, cand_low_val = 0, low[0]

    for i in range(1, n):
        if direction == 1:  # Trending up — looking for MAX
            if high[i] > cand_high_val:
                cand_high_idx, cand_high_val = i, high[i]

            if close[i] < cand_high_val * (1.0 - min_pct):
                pts.append((cand_high_idx, "MAX", float(cand_high_val)))
                direction = -1
                cand_low_idx, cand_low_val = i, low[i]

        elif direction == -1:  # Trending down — looking for MIN
            if low[i] < cand_low_val:
                cand_low_idx, cand_low_val = i, low[i]

            if close[i] > cand_low_val * (1.0 + min_pct):
                pts.append((cand_low_idx, "MIN", float(cand_low_val)))
                direction = 1
                cand_high_idx, cand_high_val = i, high[i]

    return pts


def compute_zigzag_legs(
    dates: Any,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    scale_name: str,
    min_pct: float,
    ticker: str = "",
) -> List[Dict[str, Any]]:
    """
    Canonical zigzag leg detector with causal confirmation timestamps.
    Returns: List of leg dictionaries compatible with market.zigzag_legs.
    """
    n = len(dates)
    if n < 10:
        return []

    legs = []
    mode = 0  # 0 = init, +1 = searching High, -1 = searching Low

    extreme_price = None
    extreme_idx = None

    start_type = None
    start_price = None
    start_idx = None

    for i in range(n):
        c_high = float(highs[i])
        c_low = float(lows[i])
        c_close = float(closes[i])

        if mode == 0:
            extreme_price = c_close
            extreme_idx = i
            start_price = c_close
            start_idx = i
            mode = 1
            start_type = "MIN"
            continue

        if mode == 1:  # Moving UP (building peak High)
            if c_high > extreme_price:
                extreme_price = c_high
                extreme_idx = i

            # Check if price dropped by min_pct from peak High
            if c_low <= extreme_price * (1.0 - min_pct):
                end_price = extreme_price
                end_idx = extreme_idx
                end_type = "MAX"

                legs.append({
                    "ticker": ticker,
                    "scale": scale_name,
                    "start_timestamp": dates[start_idx],
                    "start_type": start_type,
                    "start_price": round(float(start_price), 4),
                    "end_timestamp": dates[end_idx],
                    "end_type": end_type,
                    "end_price": round(float(end_price), 4),
                    "confirmed_at_timestamp": dates[i],
                    "status": "CONFIRMED",
                })

                mode = -1
                start_type = "MAX"
                start_price = end_price
                start_idx = end_idx
                extreme_price = c_low
                extreme_idx = i

        elif mode == -1:  # Moving DOWN (building valley Low)
            if c_low < extreme_price:
                extreme_price = c_low
                extreme_idx = i

            # Check if price rose by min_pct from valley Low
            if c_high >= extreme_price * (1.0 + min_pct):
                end_price = extreme_price
                end_idx = extreme_idx
                end_type = "MIN"

                legs.append({
                    "ticker": ticker,
                    "scale": scale_name,
                    "start_timestamp": dates[start_idx],
                    "start_type": start_type,
                    "start_price": round(float(start_price), 4),
                    "end_timestamp": dates[end_idx],
                    "end_type": end_type,
                    "end_price": round(float(end_price), 4),
                    "confirmed_at_timestamp": dates[i],
                    "status": "CONFIRMED",
                })

                mode = 1
                start_type = "MIN"
                start_price = end_price
                start_idx = end_idx
                extreme_price = c_high
                extreme_idx = i

    return legs


def compute_zigzag(
    df: pd.DataFrame,
    deviation_pct: float,
    mode: str = "legs",
    scale_name: Optional[str] = None,
    ticker: str = "",
) -> Union[List[Dict[str, Any]], List[Tuple[int, str, float]]]:
    """
    Unified high-level dispatcher for ZigZag calculations.

    Args:
        df: DataFrame with OHLCV data.
        deviation_pct: Deviation threshold (e.g. 0.025, 0.05, 0.075).
        mode: 'legs' for confirmed legs or 'points' for turning points.
        scale_name: Optional identifier (e.g. 'zz25', 'zz50', 'zz75').
        ticker: Optional ticker symbol.

    Returns:
        List of leg dicts if mode=='legs', or List of (idx, type, price) if mode=='points'.
    """
    if df.empty:
        return []

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    opens = df["open"].values if "open" in df.columns else closes

    if mode == "points":
        return compute_zigzag_points(highs, lows, closes, min_pct=deviation_pct)
    elif mode == "legs":
        sc_name = scale_name or f"zz{int(round(deviation_pct * 1000))}"
        return compute_zigzag_legs(
            dates=df.index,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            scale_name=sc_name,
            min_pct=deviation_pct,
            ticker=ticker,
        )
    else:
        raise ValueError(f"Unsupported mode: {mode}. Must be 'legs' or 'points'.")
