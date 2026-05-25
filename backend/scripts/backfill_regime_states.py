"""
Backfill Regime States — Historical Transition Persistence
=============================================================
Vectorized computation of vol regime transitions from SPY OHLCV
history in the Vault. Populates market.regime_states for both
Quality and Speculative vol regimes.

Usage:
    cd /root/botero-trade
    PYTHONPATH=backend backend/.venv/bin/python backend/scripts/backfill_regime_states.py

Runtime: <20s for 9,625 SPY bars (1993-2026).
"""
import logging
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import os
import sys

# Setup
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Add project root to sys.path for 'backend.' imports
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _project_root)

from dotenv import load_dotenv
load_dotenv()

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.postgres_regime_state import PostgresRegimeStateAdapter
from backend.modules.entry_decision.domain.rules.vol_regime_gate import compute_vol_regime_snapshot
from backend.modules.volatility_regime.domain.rules.vol_classifier import VolRegimeClassifier
from backend.modules.volatility_regime.domain.entities.vol_regime import (
    QUALITY_LABELS, SPECULATIVE_LABELS,
)


def compute_sensor_series(prices: pd.DataFrame) -> dict:
    """Compute all vol regime sensor series from price data.

    Replicates the exact computation in vol_regime_gate.py L48-75
    to ensure backfill matches production classification.
    """
    close = prices["close"].astype(float)
    high = prices["high"].astype(float)
    low = prices["low"].astype(float)

    # Realized Volatility
    log_returns = np.log(close / close.shift(1))
    real_vol_fast = log_returns.rolling(10, min_periods=5).std() * np.sqrt(252)
    real_vol_slow = log_returns.rolling(60, min_periods=30).std() * np.sqrt(252)

    # Vol Ratio
    vol_ratio = real_vol_fast / real_vol_slow.replace(0, np.nan)
    vol_ratio = vol_ratio.fillna(1.0)

    # Vol Persistence
    abs_rets = log_returns.abs()
    vol_persistence = abs_rets.rolling(20, min_periods=10).apply(
        lambda x: x.autocorr(lag=1) if len(x) > 5 else 0.5,
        raw=False,
    ).fillna(0.5)

    # Vol of Vol
    vol_of_vol = real_vol_fast.rolling(20, min_periods=10).std().fillna(0.15)

    # Calm Duration
    vol_mean = real_vol_fast.rolling(60, min_periods=30).mean()
    is_calm = (real_vol_fast < vol_mean).astype(float)
    calm_groups = (is_calm != is_calm.shift(1)).cumsum()
    calm_duration = is_calm.groupby(calm_groups).cumsum()

    return {
        "calm_duration": calm_duration,
        "vol_persistence": vol_persistence,
        "vol_of_vol": vol_of_vol,
        "vol_ratio": vol_ratio,
    }


def compute_vix_zscore_series(vix_df: pd.DataFrame) -> pd.Series:
    """Compute VIX z-score series (60-day rolling)."""
    vix_close = vix_df["close"].astype(float)
    vix_mean = vix_close.rolling(60, min_periods=30).mean()
    vix_std = vix_close.rolling(60, min_periods=30).std()
    vix_z = (vix_close - vix_mean) / vix_std.replace(0, 1.0)
    return vix_z.fillna(0.0)


def extract_transitions(
    regime_series: pd.Series,
    label_map: dict,
    key_prefix: str,
) -> list[dict]:
    """Extract transition events from a classified regime series.

    Detects where the regime integer changes and builds transition records
    with entered_at, closed_at, duration_bars, and previous_state.
    """
    transitions = []
    prev_val = None
    prev_state = None
    start_idx = None
    start_bar = 0

    for i, (ts, val) in enumerate(regime_series.items()):
        if np.isnan(val):
            continue
        val = int(val)
        label = label_map.get(val, "UNKNOWN")

        if val != prev_val:
            # Close previous state
            if prev_val is not None and start_idx is not None:
                transitions.append({
                    "key": key_prefix,
                    "current_state": label_map.get(prev_val, "UNKNOWN"),
                    "previous_state": prev_state,
                    "entered_at": start_idx,
                    "closed_at": ts,
                    "duration_bars": i - start_bar,
                    "trigger_event": "BACKFILL",
                })
            prev_state = label_map.get(prev_val, "UNKNOWN") if prev_val is not None else None
            prev_val = val
            start_idx = ts
            start_bar = i

    # Close final active state (leave closed_at=None → currently active)
    if prev_val is not None and start_idx is not None:
        transitions.append({
            "key": key_prefix,
            "current_state": label_map.get(prev_val, "UNKNOWN"),
            "previous_state": prev_state,
            "entered_at": start_idx,
            "closed_at": None,
            "duration_bars": len(regime_series) - start_bar,
            "trigger_event": "BACKFILL",
        })

    return transitions


def main():
    logger.info("=" * 60)
    logger.info("Backfill Regime States — Starting")
    logger.info("=" * 60)

    store = TimescaleDataStore()
    regime_store = PostgresRegimeStateAdapter()

    # ── Load SPY and VIX from Vault ──
    logger.info("Loading SPY and VIX from Vault...")
    spy_df = store.load_bars("SPY", "1d")
    vix_df = store.load_bars("VIX", "1d")
    store.close()

    if spy_df is None or len(spy_df) < 252:
        logger.error("Insufficient SPY data in Vault")
        return

    logger.info(f"SPY: {len(spy_df)} bars ({spy_df.index[0].date()} → {spy_df.index[-1].date()})")
    logger.info(f"VIX: {len(vix_df)} bars ({vix_df.index[0].date()} → {vix_df.index[-1].date()})")

    # ── Compute sensors ──
    logger.info("Computing sensor series...")
    sensors = compute_sensor_series(spy_df)

    # ── VIX z-score (align to SPY index) ──
    vix_z = compute_vix_zscore_series(vix_df)
    # Align VIX z-score to SPY index (forward-fill for missing dates)
    vix_z_aligned = vix_z.reindex(spy_df.index, method="ffill").fillna(0.0)
    vix_vel = pd.Series(0.0, index=spy_df.index)  # Velocity not available historically

    # ── Classify ──
    logger.info("Classifying vol regimes...")
    classifier = VolRegimeClassifier()

    quality = classifier.classify_quality_series(
        sensors["calm_duration"], sensors["vol_persistence"],
        sensors["vol_of_vol"], sensors["vol_ratio"],
        vix_z_aligned, vix_vel,
    )
    speculative = classifier.classify_speculative_series(
        sensors["calm_duration"], sensors["vol_persistence"],
        sensors["vol_of_vol"], sensors["vol_ratio"],
        vix_z_aligned, vix_vel,
    )

    # ── Extract transitions ──
    logger.info("Extracting transitions...")

    # Trim to valid range (need 60 bars warmup)
    quality_valid = quality.iloc[60:]
    spec_valid = speculative.iloc[60:]

    q_transitions = extract_transitions(quality_valid, QUALITY_LABELS, "vol:quality:MARKET")
    s_transitions = extract_transitions(spec_valid, SPECULATIVE_LABELS, "vol:speculative:MARKET")

    logger.info(f"Quality transitions:     {len(q_transitions)}")
    logger.info(f"Speculative transitions: {len(s_transitions)}")

    # ── Persist ──
    logger.info("Persisting to market.regime_states...")
    regime_store.ensure_table()

    q_inserted = regime_store.bulk_insert_transitions(q_transitions)
    s_inserted = regime_store.bulk_insert_transitions(s_transitions)
    regime_store.close()

    logger.info(f"Inserted: {q_inserted} quality + {s_inserted} speculative = {q_inserted + s_inserted} total")

    # ── Summary ──
    logger.info("")
    logger.info("─── Quality Regime Summary ───")
    for t in q_transitions[-5:]:
        dur = t["duration_bars"]
        logger.info(
            f"  {t['entered_at'].date() if hasattr(t['entered_at'], 'date') else t['entered_at']} "
            f"→ {t['current_state']:12s} ({dur:4d} bars) "
            f"prev={t['previous_state']}"
        )

    logger.info("")
    logger.info("─── Speculative Regime Summary ───")
    for t in s_transitions[-5:]:
        dur = t["duration_bars"]
        logger.info(
            f"  {t['entered_at'].date() if hasattr(t['entered_at'], 'date') else t['entered_at']} "
            f"→ {t['current_state']:12s} ({dur:4d} bars) "
            f"prev={t['previous_state']}"
        )

    logger.info("")
    logger.info("✅ Backfill complete")


if __name__ == "__main__":
    main()
