#!/usr/bin/env python3
"""
Backfill Channel Snapshots — Complete Feature Lake Builder
================================================================
Computes ChannelSnapshot for EVERY bar of EVERY ticker in the Vault
and persists to engine.channel_snapshots.

Produces COMPLETE snapshots with ALL indicators:
  - Triple Regression (TIDE/CURRENT/WAVE) + Triple VWAP
  - RSI(14) Wilder + divergence + conviction (stateful, full-series)
  - Kalman velocity + vol_adj_delta (stateful, full-series)
  - Geometric features, Tensions, Compression

RSI and Kalman are stateful indicators that require full price history
for correct computation. They are pre-computed for the entire series
before the per-bar loop, then injected into each ChannelSnapshot.
This matches the oracle_trainer pattern.

Estimated: 17 tickers × ~5,000 bars = ~85,000 snapshots
Time: ~10-15 minutes (includes RSI + Kalman computation)

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backfill_channel_snapshots.py

Re-runnable (idempotent): uses ON CONFLICT DO UPDATE.
"""
import os, sys, time, logging
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.price_analysis.application.use_cases.analyze_rsi import RSIIntelligence
from backend.modules.volume_intelligence.application.use_cases.track_volume_dynamics import KalmanVolumeTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# All tickers in the Vault (from AGENTS.md registry)
TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]

BATCH_SIZE = 500  # Rows per DB upsert
MIN_BARS = 250    # Minimum bars needed for compute_channel_snapshot
RSI_PERIOD = 14   # Wilder standard
RSI_MIN_BARS = RSI_PERIOD + 30  # Minimum for divergence detection
RSI_WINDOW = 60   # Window for divergence/conviction analysis


def _precompute_rsi(close: np.ndarray) -> tuple[np.ndarray, list]:
    """Pre-compute RSI(14) full series + windowed divergence/conviction.

    RSI Wilder uses exponential smoothing — requires full history for
    correct values. The series is computed ONCE and indexed per-bar.

    Divergence and conviction use a 60-bar windowed analysis (local pivots).

    Returns:
        rsi_series: Full-length array aligned with close (padded front).
        div_conv: List of (divergence_strength, conviction) per bar.
    """
    rsi_intel = RSIIntelligence()
    # Full series: _calc_rsi_series returns N-1 elements (np.diff).
    # Pad front with 50.0 to align with close index.
    raw_rsi = rsi_intel._calc_rsi_series(close, RSI_PERIOD)
    rsi_series = np.concatenate(([50.0], raw_rsi))

    div_conv = []
    for i in range(len(close)):
        if i < RSI_MIN_BARS:
            div_conv.append((0.0, 0.0))
            continue
        start_idx = max(0, i - RSI_WINDOW)
        window = close[start_idx:i + 1]
        try:
            result = rsi_intel.analyze(window, regime_hint="NEUTRAL", period=RSI_PERIOD)
            div_conv.append((result.divergence_strength, result.rsi_conviction))
        except Exception:
            div_conv.append((0.0, 0.0))

    return rsi_series, div_conv


def _precompute_kalman(close: np.ndarray, volume: np.ndarray) -> list[dict]:
    """Pre-compute Kalman velocity + vol_adj_delta for full series.

    KalmanVolumeTracker maintains internal state — must be run
    sequentially from bar 0.

    Returns:
        List of {kalman_velocity, vol_adj_delta} per bar.
    """
    import pandas as pd
    tracker = KalmanVolumeTracker(dt=1.0, process_noise=0.05, obs_noise=0.2)
    vol_series = pd.Series(volume)
    vol_mean_20 = vol_series.rolling(window=20, min_periods=1).mean()
    returns = pd.Series(close).pct_change()

    results = []
    for i in range(len(close)):
        raw_vol = float(volume[i])
        avg_vol = float(vol_mean_20.iloc[i])
        observed_rvol = raw_vol / avg_vol if avg_vol > 0 else 1.0

        prev_close = float(close[max(0, i - 1)])
        curr_close = float(close[i])
        change_pct = ((curr_close - prev_close) / prev_close * 100) if prev_close > 0 else 0.0

        state = tracker.update("tmp", observed_rvol, change_pct)
        velocity = state.get("velocity", 0.0)

        if i >= 20:
            vol_20 = returns.iloc[max(0, i - 19):i + 1].std()
            vol_adj = velocity / max(vol_20 * 100, 0.01)
        else:
            vol_adj = 0.0

        results.append({
            'kalman_velocity': round(float(velocity), 6),
            'vol_adj_delta': round(float(vol_adj), 6),
        })

    return results


def backfill_ticker(store: TimescaleDataStore, ticker: str) -> int:
    """Compute and persist COMPLETE snapshots for all bars of a ticker.

    Pipeline:
      1. Load full OHLCV from Vault
      2. Pre-compute RSI series (stateful, full history)
      3. Pre-compute Kalman states (stateful, sequential)
      4. For each bar: compute_channel_snapshot() + inject RSI + Kalman
      5. Batch persist to engine.channel_snapshots
    """
    ohlc = store.load_bars(ticker, "1d")
    if ohlc is None or len(ohlc) < MIN_BARS:
        logger.warning(f"  {ticker}: skipped (only {len(ohlc) if ohlc is not None else 0} bars)")
        return 0

    close = ohlc["close"].values.astype(float)
    high = ohlc["high"].values.astype(float)
    low = ohlc["low"].values.astype(float)
    volume = ohlc["volume"].values.astype(float)
    timestamps = ohlc.index.tolist()

    # ── Pre-compute stateful indicators (full series) ──
    logger.info(f"  {ticker}: computing RSI(14) full series...")
    rsi_series, rsi_div_conv = _precompute_rsi(close)

    logger.info(f"  {ticker}: computing Kalman states...")
    kalman_states = _precompute_kalman(close, volume)

    # Check existing count to report progress
    existing = store.count_snapshots(ticker, "1d")

    snapshots = []
    snap_timestamps = []
    total_persisted = 0

    for idx in range(MIN_BARS, len(ohlc)):
        snap = compute_channel_snapshot(close, high, low, volume, idx)
        if snap is None:
            continue

        # ── Inject RSI (full-series Wilder + windowed divergence/conviction) ──
        snap.rsi_value = round(float(rsi_series[idx]), 1)
        div_str, conv = rsi_div_conv[idx]
        snap.rsi_divergence_strength = round(float(div_str), 4)
        snap.rsi_conviction = round(float(conv), 4)

        # ── Inject Kalman velocity + vol_adj_delta ──
        k = kalman_states[idx]
        snap.kalman_velocity = k['kalman_velocity']
        snap.vol_adj_delta = k['vol_adj_delta']

        snapshots.append(snap)
        snap_timestamps.append(timestamps[idx])

        # Batch persist
        if len(snapshots) >= BATCH_SIZE:
            n = store.save_snapshots_batch(ticker, "1d", snap_timestamps, snapshots)
            total_persisted += n
            snapshots = []
            snap_timestamps = []

    # Flush remaining
    if snapshots:
        n = store.save_snapshots_batch(ticker, "1d", snap_timestamps, snapshots)
        total_persisted += n

    # Sanity check: RSI variance
    rsi_std = float(np.std(rsi_series[MIN_BARS:]))
    kv_std = float(np.std([k['kalman_velocity'] for k in kalman_states[MIN_BARS:]]))
    logger.info(
        f"  {ticker}: {total_persisted} snapshots persisted "
        f"(was {existing}, bars={len(ohlc)}, RSI_std={rsi_std:.2f}, KV_std={kv_std:.4f})"
    )
    return total_persisted


def main():
    print("=" * 80)
    print("  BACKFILL CHANNEL SNAPSHOTS — Complete Feature Lake")
    print("  48 fields (RC + VWAP + RSI + Kalman + Geo) × every bar × every ticker")
    print("  RSI: full-series Wilder(14) + windowed divergence/conviction")
    print("  Kalman: sequential KalmanVolumeTracker velocity + vol_adj_delta")
    print("=" * 80)

    store = TimescaleDataStore()

    # Create table if needed
    print("\n  Creating table engine.channel_snapshots...")
    store.ensure_channel_snapshots_table()
    print("  ✅ Table ready.")

    t0 = time.time()
    grand_total = 0

    print(f"\n  Processing {len(TICKERS)} tickers...\n")
    for ticker in TICKERS:
        t1 = time.time()
        n = backfill_ticker(store, ticker)
        elapsed = time.time() - t1
        grand_total += n
        print(f"  ✅ {ticker:>5s}: {n:>6,d} snapshots in {elapsed:.1f}s")

    total_elapsed = time.time() - t0
    store.close()

    print(f"\n{'=' * 80}")
    print(f"  BACKFILL COMPLETE")
    print(f"  Total snapshots: {grand_total:,d}")
    print(f"  Total time: {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")
    print(f"  Schema version: 1")
    print(f"  Table: engine.channel_snapshots")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
