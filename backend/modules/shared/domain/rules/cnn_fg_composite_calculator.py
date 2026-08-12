"""
CNN Fear & Greed SPIndex Calculator — Pure Domain Rules
=========================================================
Computes all 7 CNN F&G sub-indicators from Vault data + composite score.

Named "SPIndex" because sub-indicators #2 (Strength) and #3 (Breadth)
use SP500 constituents (~504 stocks) instead of NYSE-wide (~3000 stocks).
The other 5 sub-indicators are computed IDENTICALLY to CNN.

Sub-indicators:
  1. FG_MOMENTUM:  SPY price vs 125-day MA (distance %)
  2. FG_STRENGTH:  52-week H/L ratio (SP500, log-transformed)
  3. FG_BREADTH:   McClellan Volume Summation Index (SP500)
  4. FG_PUTCALL:   CBOE Put/Call ratio (inverted — lower = greed)
  5. FG_VIX:       VIX level (inverted — lower = greed)
  6. FG_JUNKBOND:  HYG/LQD price ratio (junk vs investment grade)
  7. FG_SAFEHAVEN: 20d return differential (SPY - TLT)

Composite FG_SP = mean(percentile_score(sub_i) for i in 1..7)
Each sub-indicator is scored 0-100 by percentile rank over a 2-year window.

No external API calls. Pure computation from pre-loaded OHLCV series.
"""
import math
import numpy as np
from typing import Optional


# ═══════════════════════════════════════════════════════════════
# Sub-indicator 1: Market Momentum (SPY vs 125-day MA)
# ═══════════════════════════════════════════════════════════════

def calculate_momentum(spy_closes: list[float], ma_period: int = 125) -> Optional[float]:
    """SPY price distance from 125-day moving average (%).

    CNN raw value is the SPY close itself; score is based on where SPY
    sits relative to its 125d MA. We store the % distance as the raw
    value since it's more meaningful for percentile ranking.

    Returns:
        Percent distance from MA: +2.0 means SPY is 2% above 125d MA.
        Positive = greed direction. Negative = fear direction.
    """
    if len(spy_closes) < ma_period:
        return None
    ma = sum(spy_closes[-ma_period:]) / ma_period
    current = spy_closes[-1]
    if ma == 0:
        return None
    return round((current / ma - 1) * 100, 4)


# ═══════════════════════════════════════════════════════════════
# Sub-indicator 4: Put/Call Ratio (CBOE)
# ═══════════════════════════════════════════════════════════════

def calculate_putcall(pcr_closes: list[float]) -> Optional[float]:
    """CBOE equity put/call ratio.

    INVERTED sentiment: lower ratio = more greed (more calls vs puts).
    We store the raw ratio; inversion happens during percentile scoring.

    Returns:
        Raw P/C ratio (e.g. 0.72). Lower = greed, higher = fear.
    """
    if not pcr_closes:
        return None
    return round(pcr_closes[-1], 4)


# ═══════════════════════════════════════════════════════════════
# Sub-indicator 5: Market Volatility (VIX)
# ═══════════════════════════════════════════════════════════════

def calculate_vix(vix_closes: list[float]) -> Optional[float]:
    """VIX level.

    INVERTED sentiment: lower VIX = more greed (complacency).
    We store the raw VIX; inversion happens during percentile scoring.

    Returns:
        Raw VIX close (e.g. 18.5). Lower = greed, higher = fear.
    """
    if not vix_closes:
        return None
    return round(vix_closes[-1], 4)


# ═══════════════════════════════════════════════════════════════
# Sub-indicator 6: Junk Bond Demand (HYG / LQD)
# ═══════════════════════════════════════════════════════════════

def calculate_junkbond(
    hyg_closes: list[float],
    lqd_closes: list[float],
) -> Optional[float]:
    """Junk bond demand: HYG/LQD price ratio.

    When investors are greedy, they buy riskier junk bonds (HYG)
    over investment-grade (LQD), pushing the ratio UP.
    Higher ratio = more greed.

    Returns:
        HYG/LQD price ratio (e.g. 1.35).
    """
    if not hyg_closes or not lqd_closes:
        return None
    if lqd_closes[-1] == 0:
        return None
    return round(hyg_closes[-1] / lqd_closes[-1], 4)


# ═══════════════════════════════════════════════════════════════
# Sub-indicator 7: Safe Haven Demand (SPY - TLT 20d returns)
# ═══════════════════════════════════════════════════════════════

def calculate_safehaven(
    spy_closes: list[float],
    tlt_closes: list[float],
    period: int = 20,
) -> Optional[float]:
    """Safe haven demand: 20-day return differential (SPY - TLT).

    When stocks outperform bonds, investors are risk-seeking (greed).
    When bonds outperform stocks, investors are risk-averse (fear).
    Higher = more greed.

    Returns:
        Return differential in percentage points (e.g. +3.5 means
        SPY gained 3.5pp more than TLT over 20 days).
    """
    if len(spy_closes) < period + 1 or len(tlt_closes) < period + 1:
        return None

    spy_ret = (spy_closes[-1] / spy_closes[-period - 1] - 1) * 100
    tlt_ret = (tlt_closes[-1] / tlt_closes[-period - 1] - 1) * 100

    return round(spy_ret - tlt_ret, 4)


# ═══════════════════════════════════════════════════════════════
# Percentile Scoring — converts raw value to 0-100
# ═══════════════════════════════════════════════════════════════

def percentile_score(
    current: float,
    history: list[float],
    invert: bool = False,
) -> float:
    """Convert a raw indicator value to 0-100 score by percentile rank.

    CNN uses a 2-year (504 trading day) rolling window for ranking.

    Args:
        current: The current raw value.
        history: List of past raw values to rank against.
        invert: If True, lower raw values get HIGHER scores
                (used for VIX and Put/Call where lower = more greed).

    Returns:
        Score 0-100. Higher = more greed.
    """
    if not history:
        return 50.0  # neutral if no history

    if invert:
        # For inverted indicators: count how many HIGHER (worse) values exist
        rank = sum(1 for h in history if h > current) / len(history)
    else:
        # Normal: count how many LOWER values exist
        rank = sum(1 for h in history if h < current) / len(history)

    return round(rank * 100, 1)


# ═══════════════════════════════════════════════════════════════
# Composite: FG_SP (Fear & Greed SPIndex)
# ═══════════════════════════════════════════════════════════════

def calculate_composite(scores: dict[str, float]) -> Optional[float]:
    """Composite F&G SPIndex = simple mean of 7 sub-indicator scores.

    Matches CNN's formula exactly: FG = mean(sub_scores).
    Each sub_score is already normalized to 0-100.

    Args:
        scores: Dict of sub-indicator name → 0-100 score.
                Must have at least 4 valid scores to compute.

    Returns:
        Composite score 0-100, or None if insufficient data.
    """
    valid = [v for v in scores.values() if v is not None]
    if len(valid) < 4:
        return None
    return round(sum(valid) / len(valid), 1)


# Which sub-indicators use inverted scoring
INVERTED_INDICATORS = {"FG_PUTCALL", "FG_VIX"}
