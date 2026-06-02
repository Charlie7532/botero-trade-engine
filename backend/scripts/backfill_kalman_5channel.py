#!/usr/bin/env python3
"""
Backfill Kalman 5-Channel — Extend Feature Lake
====================================================
Extends engine.channel_snapshots with 11 Kalman 5-channel columns
and 4 turn signal placeholder columns.

Reads from:
  - engine.channel_snapshots (existing 42 columns: rsi_value, tension_tide, conj_wave_tide)
  - market.ohlcv_bars (close, volume for returns and rvol)

Writes to:
  - engine.channel_snapshots (11 new Kalman columns + 4 turn signal columns)
  - engine.kalman_state (final Kalman state per ticker/channel for daemon use)

Pipeline per ticker:
  1. Load all existing snapshots (rsi_value, tension_tide, conj_wave_tide)
  2. Load OHLCV (close, volume)
  3. Compute 5 Kalman channels sequentially (stateful)
  4. UPDATE snapshots with 11 Kalman features
  5. Save final Kalman state for daemon

Estimated: 17 tickers × ~5,000 bars × 5 channels = ~425,000 filter updates
Time: ~3-5 minutes

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backfill_kalman_5channel.py

Re-runnable (idempotent): uses UPDATE SET.
"""
import os
import sys
import time
import logging
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.domain.rules.kalman_5channel import (
    compute_kalman_5ch_series,
    KalmanSnapshot,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# All tickers in the Vault
TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]

BATCH_SIZE = 500


def ensure_kalman_columns(store: TimescaleDataStore) -> None:
    """Add Kalman 5-channel columns to engine.channel_snapshots if they don't exist."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            kalman_cols = [
                ("kf_price_pred_val", "REAL"),
                ("kf_price_filt_vel", "REAL"),
                ("kf_price_innovation", "REAL"),
                ("kf_rvol_pred_val", "REAL"),
                ("kf_rvol_filt_vel", "REAL"),
                ("kf_tension_pred_val", "REAL"),
                ("kf_tension_filt_vel", "REAL"),
                ("kf_rsi_pred_val", "REAL"),
                ("kf_rsi_filt_vel", "REAL"),
                ("kf_conj_pred_val", "REAL"),
                ("kf_conj_filt_vel", "REAL"),
                # Turn signal columns (populated later by train_sentinel)
                ("turn_prob_piso", "REAL"),
                ("turn_prob_techo", "REAL"),
                ("turn_archetype", "VARCHAR(4)"),
                ("turn_density", "VARCHAR(16)"),
            ]
            for col_name, col_type in kalman_cols:
                cur.execute(f"""
                    DO $$ BEGIN
                        ALTER TABLE engine.channel_snapshots
                        ADD COLUMN IF NOT EXISTS {col_name} {col_type};
                    EXCEPTION WHEN duplicate_column THEN NULL;
                    END $$;
                """)

            # Create kalman_state table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS engine.kalman_state (
                    ticker      VARCHAR(10),
                    channel     VARCHAR(16),
                    x0          DOUBLE PRECISION,
                    x1          DOUBLE PRECISION,
                    p00         DOUBLE PRECISION,
                    p01         DOUBLE PRECISION,
                    p10         DOUBLE PRECISION,
                    p11         DOUBLE PRECISION,
                    updated_at  TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (ticker, channel)
                );
            """)
            conn.commit()
            logger.info("✅ Kalman columns and state table ensured")
    except Exception as e:
        conn.rollback()
        logger.error(f"Schema update failed: {e}")
        raise
    finally:
        store._put(conn)


def save_kalman_state(store: TimescaleDataStore, ticker: str, final_state: dict) -> None:
    """Persist final Kalman state for daemon use."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            for channel, state in final_state.items():
                cur.execute("""
                    INSERT INTO engine.kalman_state (ticker, channel, x0, x1, p00, p01, p10, p11, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (ticker, channel) DO UPDATE SET
                        x0 = EXCLUDED.x0, x1 = EXCLUDED.x1,
                        p00 = EXCLUDED.p00, p01 = EXCLUDED.p01,
                        p10 = EXCLUDED.p10, p11 = EXCLUDED.p11,
                        updated_at = NOW()
                """, (ticker, channel, state["x0"], state["x1"],
                      state["p00"], state["p01"], state["p10"], state["p11"]))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Kalman state save failed for {ticker}: {e}")
    finally:
        store._put(conn)


def backfill_ticker(store: TimescaleDataStore, ticker: str) -> int:
    """Compute and persist Kalman 5-channel features for one ticker.

    Pipeline:
      1. Load snapshots (rsi_value, tension_tide, conj_wave_tide)
      2. Load OHLCV (close, volume)
      3. Compute 5 Kalman channels (sequential, full series)
      4. Batch UPDATE snapshots with 11 Kalman features
      5. Save final state
    """
    # 1. Load existing snapshots
    snapshots = store.load_snapshots(ticker, "1d")
    if snapshots is None or snapshots.empty:
        logger.warning(f"  {ticker}: no snapshots found")
        return 0

    # 2. Load OHLCV
    ohlcv = store.load_bars(ticker, "1d")
    if ohlcv is None or ohlcv.empty:
        logger.warning(f"  {ticker}: no OHLCV data")
        return 0

    # Align snapshots with OHLCV by date
    snap_dates = pd.to_datetime(snapshots.index).normalize()
    ohlcv_dates = pd.to_datetime(ohlcv.index).normalize()

    # Build close/volume arrays aligned with snapshots
    close_lookup = {}
    volume_lookup = {}
    for i, d in enumerate(ohlcv_dates):
        close_lookup[d] = float(ohlcv.iloc[i]["close"])
        volume_lookup[d] = float(ohlcv.iloc[i]["volume"])

    n = len(snapshots)
    close_aligned = np.zeros(n)
    volume_aligned = np.zeros(n)
    for i, d in enumerate(snap_dates):
        d_ts = pd.Timestamp(d)
        close_aligned[i] = close_lookup.get(d_ts, 0.0)
        volume_aligned[i] = volume_lookup.get(d_ts, 0.0)

    # Compute returns and rvol
    price_returns = np.zeros(n)
    price_returns[1:] = np.where(
        close_aligned[:-1] > 0,
        (close_aligned[1:] - close_aligned[:-1]) / close_aligned[:-1] * 100,
        0.0,
    )

    vol_ma20 = pd.Series(volume_aligned).rolling(20, min_periods=1).mean().values
    rvol = np.where(vol_ma20 > 0, volume_aligned / vol_ma20, 1.0)

    # Extract source signals from snapshots
    rsi_values = snapshots["rsi_value"].fillna(50.0).values.astype(float)
    tension_values = snapshots["tension_tide"].fillna(0.0).values.astype(float)
    conj_values = snapshots["conj_wave_tide"].fillna(0.0).values.astype(float)

    # 3. Compute all 5 Kalman channels
    kalman_snaps, final_state = compute_kalman_5ch_series(
        rsi_values=rsi_values,
        tension_values=tension_values,
        conj_values=conj_values,
        price_returns=price_returns,
        rvol_values=rvol,
    )

    # 4. Batch UPDATE snapshots
    timestamps = snapshots.index.tolist()
    conn = store._conn()
    updated = 0
    try:
        with conn.cursor() as cur:
            batch = []
            for i, (ts, ks) in enumerate(zip(timestamps, kalman_snaps)):
                batch.append((
                    ks.kf_price_pred_val, ks.kf_price_filt_vel, ks.kf_price_innovation,
                    ks.kf_rvol_pred_val, ks.kf_rvol_filt_vel,
                    ks.kf_tension_pred_val, ks.kf_tension_filt_vel,
                    ks.kf_rsi_pred_val, ks.kf_rsi_filt_vel,
                    ks.kf_conj_pred_val, ks.kf_conj_filt_vel,
                    ticker, ts,
                ))

                if len(batch) >= BATCH_SIZE:
                    cur.executemany("""
                        UPDATE engine.channel_snapshots SET
                            kf_price_pred_val = %s, kf_price_filt_vel = %s, kf_price_innovation = %s,
                            kf_rvol_pred_val = %s, kf_rvol_filt_vel = %s,
                            kf_tension_pred_val = %s, kf_tension_filt_vel = %s,
                            kf_rsi_pred_val = %s, kf_rsi_filt_vel = %s,
                            kf_conj_pred_val = %s, kf_conj_filt_vel = %s
                        WHERE ticker = %s AND timestamp = %s
                    """, batch)
                    updated += len(batch)
                    batch = []

            # Flush remaining
            if batch:
                cur.executemany("""
                    UPDATE engine.channel_snapshots SET
                        kf_price_pred_val = %s, kf_price_filt_vel = %s, kf_price_innovation = %s,
                        kf_rvol_pred_val = %s, kf_rvol_filt_vel = %s,
                        kf_tension_pred_val = %s, kf_tension_filt_vel = %s,
                        kf_rsi_pred_val = %s, kf_rsi_filt_vel = %s,
                        kf_conj_pred_val = %s, kf_conj_filt_vel = %s
                    WHERE ticker = %s AND timestamp = %s
                """, batch)
                updated += len(batch)

            conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"  {ticker}: batch update failed: {e}")
        raise
    finally:
        store._put(conn)

    # 5. Save final Kalman state
    save_kalman_state(store, ticker, final_state)

    # Summary stats
    rsi_preds = [ks.kf_rsi_pred_val for ks in kalman_snaps]
    price_vels = [ks.kf_price_filt_vel for ks in kalman_snaps]
    logger.info(
        f"  {ticker}: {updated} rows updated | "
        f"kf_rsi_pred μ={np.mean(rsi_preds):.1f} σ={np.std(rsi_preds):.1f} | "
        f"kf_price_vel μ={np.mean(price_vels):.4f} σ={np.std(price_vels):.4f}"
    )
    return updated


def main():
    print("=" * 80)
    print("  BACKFILL KALMAN 5-CHANNEL — Extend Feature Lake")
    print("  11 Kalman features × every snapshot × every ticker")
    print("  Channels: PRICE, RVOL, TENSION, RSI (★SHAP#1), CONJUGATION")
    print("=" * 80)

    store = TimescaleDataStore()

    # Schema
    print("\n  Ensuring Kalman columns + state table...")
    ensure_kalman_columns(store)

    t0 = time.time()
    grand_total = 0

    print(f"\n  Processing {len(TICKERS)} tickers...\n")
    for ticker in TICKERS:
        t1 = time.time()
        n = backfill_ticker(store, ticker)
        elapsed = time.time() - t1
        grand_total += n
        print(f"  ✅ {ticker:>5s}: {n:>6,d} rows in {elapsed:.1f}s")

    total_elapsed = time.time() - t0
    store.close()

    print(f"\n{'=' * 80}")
    print(f"  BACKFILL COMPLETE")
    print(f"  Total rows updated: {grand_total:,d}")
    print(f"  Total time: {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")
    print(f"  Columns added: 11 Kalman + 4 turn signal placeholders")
    print(f"  State table: engine.kalman_state (17 tickers × 5 channels)")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
