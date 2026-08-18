#!/usr/bin/env python3
"""
Kalman Velocity Backfill — Fills kalman_velocity + vol_adj_delta
==================================================================
Computes KalmanVolumeTracker velocity for ALL bars of each ticker and
writes the results into the existing engine.channel_snapshots rows.

Currently: 0% coverage (all zeros except 48% of SPY).
Target: 100% coverage for all 17 tickers.

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backfill_kalman.py
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backfill_kalman.py --ticker AAPL
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backfill_kalman.py --dry-run
"""
import os, sys, warnings, argparse, time
from pathlib import Path
warnings.filterwarnings("ignore")

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
import pandas as pd

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.volume_intelligence.application.use_cases.track_volume_dynamics import KalmanVolumeTracker

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)

def p(t): print(f"\n{'='*80}\n  {t}\n{'='*80}")
def sp(t): print(f"\n  ── {t} ──")

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]


def compute_kalman_for_ticker(ticker, ohlc):
    """Compute Kalman velocity + vol_adj_delta for entire OHLCV history.

    Returns DataFrame with columns: [time, kalman_velocity, vol_adj_delta]
    """
    tracker = KalmanVolumeTracker(dt=1.0, process_noise=0.05, obs_noise=0.2)
    vol_series = ohlc["volume"].astype(float)
    vol_mean_20 = vol_series.rolling(window=20, min_periods=1).mean()

    results = []
    for i in range(len(ohlc)):
        raw_vol = float(ohlc["volume"].iloc[i])
        avg_vol = float(vol_mean_20.iloc[i])
        observed_rvol = raw_vol / avg_vol if avg_vol > 0 else 1.0

        prev_close = float(ohlc["close"].iloc[max(0, i-1)])
        curr_close = float(ohlc["close"].iloc[i])
        change_pct = ((curr_close - prev_close) / prev_close * 100) if prev_close > 0 else 0.0

        state = tracker.update(ticker, observed_rvol, change_pct)
        velocity = state.get("velocity", 0.0)

        # vol_adj_delta: velocity normalized by rolling 20d volatility of returns
        returns = ohlc["close"].pct_change()
        if i >= 20:
            vol_20 = returns.iloc[max(0, i-19):i+1].std()
            vol_adj = velocity / max(vol_20 * 100, 0.01)  # Normalize by vol%
        else:
            vol_adj = 0.0

        results.append({
            'time': ohlc.index[i],
            'kalman_velocity': round(float(velocity), 6),
            'vol_adj_delta': round(float(vol_adj), 6),
        })

    return pd.DataFrame(results)


def backfill_ticker(store, ticker, dry_run=False):
    """Compute and write Kalman data for one ticker."""
    sp(f"{ticker}")

    # Load OHLCV
    ohlc = store.load_bars(ticker, "1d")
    if ohlc is None or ohlc.empty:
        print(f"    ⚠️ No OHLCV data for {ticker}")
        return 0

    print(f"    OHLCV: {len(ohlc):,d} bars ({ohlc.index[0].date()} → {ohlc.index[-1].date()})")

    # Compute Kalman
    kalman_df = compute_kalman_for_ticker(ticker, ohlc)
    print(f"    Kalman: {len(kalman_df):,d} rows computed")

    # Stats
    vel = kalman_df['kalman_velocity']
    print(f"    velocity: mean={vel.mean():.4f}, std={vel.std():.4f}, "
          f"min={vel.min():.4f}, max={vel.max():.4f}")

    # Verify no NaN/inf
    n_bad = kalman_df[['kalman_velocity', 'vol_adj_delta']].isna().sum().sum()
    n_inf = np.isinf(kalman_df[['kalman_velocity', 'vol_adj_delta']].values).sum()
    if n_bad > 0 or n_inf > 0:
        print(f"    ⚠️ {n_bad} NaN, {n_inf} Inf values — cleaning")
        kalman_df = kalman_df.fillna(0.0)
        kalman_df = kalman_df.replace([np.inf, -np.inf], 0.0)

    if dry_run:
        print(f"    [DRY RUN] Would update {len(kalman_df):,d} rows")
        return len(kalman_df)

    # Write to DB using batch UPDATE
    conn = store.engine.raw_connection()
    cur = conn.cursor()

    # Batch update using UNNEST for performance
    timestamps = []
    velocities = []
    vol_deltas = []

    for _, row in kalman_df.iterrows():
        timestamps.append(row['time'])
        velocities.append(row['kalman_velocity'])
        vol_deltas.append(row['vol_adj_delta'])

    # Use a temporary approach: update in batches of 500
    batch_size = 500
    updated = 0
    for start in range(0, len(timestamps), batch_size):
        end = min(start + batch_size, len(timestamps))
        batch_ts = timestamps[start:end]
        batch_vel = velocities[start:end]
        batch_vad = vol_deltas[start:end]

        # Build VALUES clause
        values = []
        for ts, vel_val, vad in zip(batch_ts, batch_vel, batch_vad):
            values.append(f"('{ts}'::timestamptz, {vel_val}, {vad})")
        values_str = ",\n".join(values)

        sql = f"""
            UPDATE engine.channel_snapshots cs
            SET kalman_velocity = v.kv,
                vol_adj_delta = v.vad
            FROM (VALUES {values_str}) AS v(ts, kv, vad)
            WHERE cs.ticker = %s AND cs.timestamp = v.ts
        """
        cur.execute(sql, (ticker,))
        updated += cur.rowcount

    conn.commit()
    cur.close()
    conn.close()

    print(f"    ✅ Updated {updated:,d} rows in channel_snapshots")
    return updated


def main():
    parser = argparse.ArgumentParser(description="Kalman Velocity Backfill")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ticker", type=str, default=None)
    args = parser.parse_args()

    tickers = [args.ticker] if args.ticker else TICKERS

    p("KALMAN VELOCITY BACKFILL")
    print(f"  Tickers: {len(tickers)}")
    if args.dry_run:
        print(f"  Mode: DRY RUN (no writes)")

    t0 = time.time()
    store = TimescaleDataStore()

    # Pre-check coverage
    sp("PRE-CHECK COVERAGE")
    q = """
        SELECT ticker,
               COUNT(*) as total,
               COUNT(CASE WHEN kalman_velocity != 0 THEN 1 END) as filled,
               ROUND(100.0 * COUNT(CASE WHEN kalman_velocity != 0 THEN 1 END) / COUNT(*), 1) as pct
        FROM engine.channel_snapshots
        WHERE ticker = ANY(%s) AND sigma_tide IS NOT NULL
        GROUP BY ticker ORDER BY ticker
    """
    pre = pd.read_sql(q, store.engine, params=(tickers,))
    for _, row in pre.iterrows():
        status = "✅" if row['pct'] > 90 else "⚠️" if row['pct'] > 0 else "❌"
        print(f"    {row['ticker']:>6s}: {row['filled']:>6,d} / {row['total']:>6,d} ({row['pct']:>5.1f}%) {status}")

    # Backfill
    total_updated = 0
    for ticker in tickers:
        n = backfill_ticker(store, ticker, dry_run=args.dry_run)
        total_updated += n

    # Post-check
    if not args.dry_run:
        sp("POST-CHECK COVERAGE")
        post = pd.read_sql(q, store.engine, params=(tickers,))
        for _, row in post.iterrows():
            status = "✅" if row['pct'] > 90 else "⚠️"
            print(f"    {row['ticker']:>6s}: {row['filled']:>6,d} / {row['total']:>6,d} ({row['pct']:>5.1f}%) {status}")

    store.close()
    elapsed = time.time() - t0

    p("KALMAN BACKFILL COMPLETE")
    print(f"  Total updated: {total_updated:,d} rows")
    print(f"  Time: {elapsed:.1f}s ({elapsed/60:.1f} min)")


if __name__ == "__main__":
    main()
