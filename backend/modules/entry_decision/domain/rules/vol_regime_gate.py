"""
Vol Regime Gate — Snapshot Classifier for Entry Decisions
=========================================================
Computes vol regime at the current moment from OHLCV price data.
Used by QualityEntryGate and SpeculativeEntryHub as Gate -1.

This is a domain rule — pure Python, no infra dependencies.

Evidence Status: HYPOTHESIS (same as VolRegimeClassifier).
"""
import pandas as pd
import numpy as np
from backend.modules.volatility_regime.domain.entities.vol_regime import (
    VolRegimeState, QUALITY_LABELS, SPECULATIVE_LABELS,
)
from backend.modules.volatility_regime.domain.rules.vol_classifier import VolRegimeClassifier


def compute_vol_regime_snapshot(
    prices: pd.DataFrame,
    vix_zscore: float = 0.0,
) -> VolRegimeState:
    """Compute current vol regime from a price DataFrame.

    Computes the sensor values (calm duration, vol persistence, vol ratio,
    vol-of-vol) from the price history, then classifies using VolRegimeClassifier.
    Returns the LAST value in the classified series.

    Args:
        prices: DataFrame with Close, High, Low, Volume columns. Min 60 rows.
        vix_zscore: Pre-computed VIX z-score (avoids redundant fetching).

    Returns:
        VolRegimeState with quality_regime and speculative_regime set.
    """
    if prices is None or len(prices) < 60:
        return VolRegimeState()

    close = prices['Close'].astype(float)
    high = prices['High'].astype(float)
    low = prices['Low'].astype(float)

    # ── Sensor: Realized Volatility (fast/slow) ─────────────────
    log_returns = np.log(close / close.shift(1))
    real_vol_fast = log_returns.rolling(10, min_periods=5).std() * np.sqrt(252)
    real_vol_slow = log_returns.rolling(60, min_periods=30).std() * np.sqrt(252)

    # ── Sensor: Vol Ratio (fast/slow) ───────────────────────────
    vol_ratio = real_vol_fast / real_vol_slow.replace(0, np.nan)
    vol_ratio = vol_ratio.fillna(1.0)

    # ── Sensor: Vol Persistence (autocorrelation) ───────────────
    abs_rets = log_returns.abs()
    vol_persistence = abs_rets.rolling(20, min_periods=10).apply(
        lambda x: x.autocorr(lag=1) if len(x) > 5 else 0.5,
        raw=False,
    ).fillna(0.5)

    # ── Sensor: Vol of Vol ──────────────────────────────────────
    vol_of_vol = real_vol_fast.rolling(20, min_periods=10).std().fillna(0.15)

    # ── Sensor: Calm Duration ───────────────────────────────────
    vol_mean = real_vol_fast.rolling(60, min_periods=30).mean()
    is_calm = (real_vol_fast < vol_mean).astype(float)
    calm_groups = (is_calm != is_calm.shift(1)).cumsum()
    calm_duration = is_calm.groupby(calm_groups).cumsum()

    # ── VIX (as Series) ─────────────────────────────────────────
    vix_z_series = pd.Series(vix_zscore, index=close.index)
    vix_vel_series = pd.Series(0.0, index=close.index)  # Velocity not available at entry

    # ── Classify ────────────────────────────────────────────────
    classifier = VolRegimeClassifier()
    quality = classifier.classify_quality_series(
        calm_duration, vol_persistence, vol_of_vol, vol_ratio,
        vix_z_series, vix_vel_series,
    )
    speculative = classifier.classify_speculative_series(
        calm_duration, vol_persistence, vol_of_vol, vol_ratio,
        vix_z_series, vix_vel_series,
    )

    return VolRegimeState(
        quality_regime=int(quality.iloc[-1]),
        speculative_regime=int(speculative.iloc[-1]),
    )
