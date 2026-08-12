"""
CNN Fear & Greed Breadth Calculator — Pure Domain Rules
========================================================
Computes the two SP500-derived sub-indicators of the CNN Fear & Greed Index:

  1. Stock Price Strength (FG_STRENGTH):
     - Ratio of stocks at 52-week highs vs 52-week lows.
     - CNN uses NYSE (~3000 stocks); we use SP500 constituents (~500).
     - Higher ratio = more greed.

  2. Stock Price Breadth (FG_BREADTH):
     - McClellan Volume Summation Index (MVSI).
     - Cumulative sum of the McClellan Volume Oscillator.
     - McClellan Vol Osc = EMA(19, net_adv_vol) - EMA(39, net_adv_vol).
     - Higher MVSI = broader volume participation = greed.

These are raw values, NOT normalized 0-100 scores. Normalization to CNN's
0-100 scale is handled downstream in the FG synthesis service.

No external API calls — pure computation from pre-loaded close/volume arrays.
"""
import numpy as np
from typing import Optional


def calculate_highs_lows_ratio(
    all_closes: dict[str, list[float]],
    lookback: int = 252,
    iwm_closes: list[float] | None = None,
) -> Optional[float]:
    """Compute ratio of stocks at 52-week highs vs 52-week lows.

    Replicates CNN's "Stock Price Strength" sub-indicator.
    CNN measures NYSE-wide (~3000 stocks), but we only have SP500 (~500).
    When ``iwm_closes`` is provided, IWM's position in its 52-week range
    is used to estimate the contribution of ~2500 small/mid-cap stocks
    that we don't track individually.

    Args:
        all_closes: {ticker: [close_day1, close_day2, ...]} chronologically ordered.
                    Must have at least ``lookback`` days of history per ticker.
        lookback: Rolling window in trading days for 52-week range (default 252).
        iwm_closes: Optional list of IWM (Russell 2000 ETF) daily closes,
                    chronologically ordered. When provided, small-cap H/L
                    contribution is estimated from IWM's 52-week position.

    Returns:
        Ratio of stocks at 52wk high / stocks at 52wk low.
        Returns None if insufficient data.
    """
    at_high = 0
    at_low = 0
    total = 0

    for ticker, closes in all_closes.items():
        if len(closes) < lookback:
            continue

        window = closes[-lookback:]
        current = closes[-1]
        high_252 = max(window)
        low_252 = min(window)

        total += 1

        # At 52-week high: current price is the max of the 252d window
        if current >= high_252:
            at_high += 1
        # At 52-week low: current price is the min of the 252d window
        if current <= low_252:
            at_low += 1

    if total == 0:
        return None

    # ── Small-cap adjustment via IWM ──
    # NYSE has ~3000 listings; SP500 = ~500 (17% by count).
    # The remaining ~2500 small/mid caps drive most of the "lows" count
    # during fear episodes. IWM's 52-week position estimates their health.
    if iwm_closes and len(iwm_closes) >= lookback:
        iwm_window = iwm_closes[-lookback:]
        iwm_current = iwm_closes[-1]
        iwm_high = max(iwm_window)
        iwm_low = min(iwm_window)
        iwm_range = iwm_high - iwm_low
        iwm_pos = (iwm_current - iwm_low) / iwm_range if iwm_range > 0 else 0.5

        # Estimated small-cap base rates from NYSE empirics:
        # Bull (IWM near high): ~5% at highs, ~1% at lows
        # Neutral (IWM mid):    ~2.5% each
        # Bear (IWM near low):  ~1% at highs, ~5% at lows
        n_small_cap = 2500
        pct_at_high = 0.01 + 0.04 * iwm_pos
        pct_at_low = 0.01 + 0.04 * (1.0 - iwm_pos)

        at_high += int(n_small_cap * pct_at_high)
        at_low += int(n_small_cap * pct_at_low)

    # Ratio: highs / max(lows, 1) to avoid division by zero
    ratio = at_high / max(at_low, 1)

    return round(ratio, 4)


def calculate_mcclellan_vsi(
    all_closes: dict[str, list[float]],
    all_volumes: dict[str, list[float]],
) -> Optional[float]:
    """Compute McClellan Volume Summation Index from individual stock data.

    Replicates CNN's "Stock Price Breadth" sub-indicator.
    CNN uses NYSE advancing/declining volume; we compute from SP500 constituents.

    Formula:
        1. For each day: advancing_volume = sum(volume of stocks that went up)
                         declining_volume = sum(volume of stocks that went down)
        2. Net Advancing Volume = advancing_volume - declining_volume
        3. McClellan Volume Oscillator = EMA(19, NAV) - EMA(39, NAV)
        4. McClellan Volume Summation Index = cumsum(MVOS)

    Args:
        all_closes: {ticker: [close_day1, ...]} chronologically ordered.
        all_volumes: {ticker: [vol_day1, ...]} chronologically ordered.
                     Keys and lengths must align with all_closes.

    Returns:
        Latest MVSI value (float), or None if insufficient data.
    """
    # Find common tickers with both close and volume data
    common = set(all_closes.keys()) & set(all_volumes.keys())
    if len(common) < 50:  # Need meaningful sample
        return None

    # Determine common date count (shortest aligned series)
    min_len = min(
        min(len(all_closes[t]) for t in common),
        min(len(all_volumes[t]) for t in common),
    )

    if min_len < 60:  # Need at least 60 days for EMA(39) warmup
        return None

    # Build daily advancing and declining volume
    n_days = min_len
    adv_vol = np.zeros(n_days)
    dec_vol = np.zeros(n_days)

    for ticker in common:
        closes = all_closes[ticker][-n_days:]
        volumes = all_volumes[ticker][-n_days:]

        for i in range(1, n_days):
            if closes[i] > closes[i - 1]:
                adv_vol[i] += volumes[i]
            elif closes[i] < closes[i - 1]:
                dec_vol[i] += volumes[i]

    # Net Advancing Volume
    net_adv = adv_vol - dec_vol

    # McClellan Volume Oscillator: EMA(19) - EMA(39) of net_adv
    ema19 = _ema(net_adv, span=19)
    ema39 = _ema(net_adv, span=39)
    mvos = ema19 - ema39

    # McClellan Volume Summation Index: cumulative sum of oscillator
    mvsi = np.cumsum(mvos)

    return round(float(mvsi[-1]), 2)


def _ema(data: np.ndarray, span: int) -> np.ndarray:
    """Compute Exponential Moving Average matching pandas ewm(span=N)."""
    alpha = 2.0 / (span + 1)
    result = np.zeros_like(data, dtype=float)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result

