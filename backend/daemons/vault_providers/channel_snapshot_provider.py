"""
Channel Snapshot Provider — Incremental daily update
============================================================
After vault_ohlcv_bars() inserts new bars, this provider computes
channel_snapshots ONLY for the new bars (incremental, not full backfill).

For each ticker:
  1. Find the last snapshot timestamp in engine.channel_snapshots
  2. Find bars AFTER that timestamp
  3. Compute snapshots for new bars only
  4. w_duration: read the last existing snapshot's w_duration and wave_level,
     then continue sequentially

Runs only when new OHLCV bars were inserted. Idempotent (UPSERT).

Architecture: Delivery mechanism (daemon provider). Calls pure domain
rule (compute_channel.py). Writes directly to Vault.
"""
import logging

import numpy as np

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)

# Same universe as backfill_channel_snapshots.py
TICKERS = [
    "AAPL", "AMZN", "COST", "HD", "HON", "IBM", "JNJ", "JPM",
    "MCD", "MRK", "MSFT", "PEP", "PG", "QQQ", "SPY", "WMT", "XOM",
]

MIN_BARS = 250  # Minimum bars needed for compute_channel_snapshot


def vault_channel_snapshots(store: TimescaleDataStore, tickers_updated: int) -> dict:
    """Compute channel snapshots incrementally for new bars only.

    Args:
        store: TimescaleDataStore instance.
        tickers_updated: Number of tickers with new OHLCV bars.
            If 0, skip entirely (no new data).

    Returns:
        dict with status, tickers_processed, snapshots_persisted.
    """
    if tickers_updated <= 0:
        return {"status": "skipped", "reason": "no_new_bars"}

    from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
    from backend.modules.quality_swing.domain.rules.rc_slope_classifier import classify_slopes
    from backend.modules.price_analysis.application.use_cases.analyze_rsi import RSIIntelligence
    from backend.modules.volume_intelligence.application.use_cases.track_volume_dynamics import (
        KalmanVolumeTracker,
    )

    stats = {"tickers_processed": 0, "snapshots_persisted": 0}

    for ticker in TICKERS:
        try:
            # 1. Find last snapshot timestamp
            conn = store._conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT MAX(timestamp) FROM engine.channel_snapshots
                        WHERE ticker = %s AND timeframe = '1d'
                    """, (ticker,))
                    row = cur.fetchone()
                    last_snap_ts = row[0] if row else None

                    # Get last snapshot's w_duration and wave_level for continuity
                    prev_w_duration = 1
                    prev_wave_level = None
                    if last_snap_ts:
                        cur.execute("""
                            SELECT w_duration, tide_slope, current_slope, wave_slope
                            FROM engine.channel_snapshots
                            WHERE ticker = %s AND timeframe = '1d' AND timestamp = %s
                        """, (ticker, last_snap_ts))
                        snap_row = cur.fetchone()
                        if snap_row:
                            prev_w_duration = snap_row[0] or 1
                            sl = classify_slopes(snap_row[1], snap_row[2], snap_row[3])
                            prev_wave_level = sl.wave_level
            finally:
                store._put(conn)

            # 2. Load full OHLCV (needed for regression windows)
            ohlc = store.load_bars(ticker, "1d")
            if ohlc is None or len(ohlc) < MIN_BARS:
                continue

            close = ohlc["close"].values.astype(float)
            high = ohlc["high"].values.astype(float)
            low = ohlc["low"].values.astype(float)
            volume = ohlc["volume"].values.astype(float)
            timestamps = ohlc.index.tolist()

            # 3. Find new bar indices (after last snapshot)
            if last_snap_ts:
                import pandas as pd
                last_ts = pd.Timestamp(last_snap_ts)
                if last_ts.tzinfo is None:
                    last_ts = last_ts.tz_localize("UTC")
                new_mask = ohlc.index > last_ts
                if not new_mask.any():
                    continue  # No new bars
                new_indices = list(range(int(new_mask.argmax()), len(ohlc)))
            else:
                # No snapshots yet — compute all (but this should have been
                # handled by the initial backfill script)
                new_indices = list(range(MIN_BARS, len(ohlc)))

            if not new_indices:
                continue

            # 4. Pre-compute RSI and Kalman for full series (stateful)
            rsi_intel = RSIIntelligence()
            rsi_period = 14
            raw_rsi = rsi_intel._calc_rsi_series(close, rsi_period)
            rsi_series = np.concatenate(([50.0], raw_rsi))

            import pandas as pd
            tracker = KalmanVolumeTracker(dt=1.0, process_noise=0.05, obs_noise=0.2)
            vol_series = pd.Series(volume)
            vol_mean_20 = vol_series.rolling(window=20, min_periods=1).mean()
            returns = pd.Series(close).pct_change()

            kalman_states = []
            for j in range(len(close)):
                raw_vol = float(volume[j])
                avg_vol = float(vol_mean_20.iloc[j])
                observed_rvol = raw_vol / avg_vol if avg_vol > 0 else 1.0
                prev_close = float(close[max(0, j - 1)])
                curr_close = float(close[j])
                change_pct = ((curr_close - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
                state = tracker.update(ticker, observed_rvol, change_pct)
                velocity = state.get("velocity", 0.0)
                if j >= 20:
                    vol_20 = returns.iloc[max(0, j - 19):j + 1].std()
                    vol_adj = velocity / max(vol_20 * 100, 0.01)
                else:
                    vol_adj = 0.0
                kalman_states.append({
                    "kalman_velocity": round(float(velocity), 6),
                    "vol_adj_delta": round(float(vol_adj), 6),
                })

            # 5. Compute snapshots for new bars only
            snapshots = []
            snap_timestamps = []
            w_dur = prev_w_duration

            for idx in new_indices:
                if idx < MIN_BARS:
                    continue

                snap = compute_channel_snapshot(close, high, low, volume, idx)
                if snap is None:
                    continue

                # Sequential w_duration
                sl = classify_slopes(snap.tide_slope, snap.current_slope, snap.wave_slope)
                curr_w_level = sl.wave_level
                if prev_wave_level is not None and curr_w_level == prev_wave_level:
                    w_dur += 1
                else:
                    w_dur = 1
                prev_wave_level = curr_w_level
                snap.w_duration = w_dur

                # Inject RSI
                snap.rsi_value = round(float(rsi_series[idx]), 1)

                # Inject Kalman
                k = kalman_states[idx]
                snap.kalman_velocity = k.get("kalman_velocity", 0.0)
                snap.vol_adj_delta = k.get("vol_adj_delta", 0.0)

                snapshots.append(snap)
                snap_timestamps.append(timestamps[idx])

            # 6. Persist
            if snapshots:
                n = store.save_snapshots_batch(ticker, "1d", snap_timestamps, snapshots)
                stats["snapshots_persisted"] += n
                stats["tickers_processed"] += 1
                logger.info(
                    f"  📊 {ticker}: {n} new channel snapshots "
                    f"(w_dur continuity: {prev_w_duration}→{w_dur})"
                )

        except Exception as e:
            logger.warning(f"  ⚠️  {ticker} channel snapshot update failed: {e}")

    logger.info(
        f"📊 Channel snapshots: {stats['tickers_processed']} tickers, "
        f"{stats['snapshots_persisted']} new snapshots"
    )
    return {"status": "ok", **stats}
