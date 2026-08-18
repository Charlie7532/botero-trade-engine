#!/usr/bin/env python3
"""
RSI Backfill — Fills rsi_value + rsi_divergence_strength + rsi_conviction
============================================================================
Computes RSI(14) Wilder + Cardwell divergence + composite conviction score
for ALL bars of each ticker and writes results into engine.channel_snapshots.

Current state: 16/17 tickers have rsi_value = 50.0 constant (default).
Target: Real RSI data with std > 3.0 for every ticker.

Uses RSIIntelligence from price_analysis module (same code as production)
to ensure consistency between backfill and live computation.

Usage:
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backfill_rsi.py
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backfill_rsi.py --ticker AAPL
    PYTHONPATH=/root/botero-trade backend/.venv/bin/python backend/scripts/backfill_rsi.py --dry-run
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
from backend.modules.price_analysis.application.use_cases.analyze_rsi import RSIIntelligence

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)

def p(t): print(f"\n{'='*80}\n  {t}\n{'='*80}")
def sp(t): print(f"\n  ── {t} ──")

TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]

RSI_PERIOD = 14
MIN_BARS = RSI_PERIOD + 30  # Need enough history for divergence detection


def compute_rsi_for_ticker(ticker: str, ohlc: pd.DataFrame) -> pd.DataFrame:
    """Compute RSI + divergence + conviction for entire OHLCV history.

    Uses RSIIntelligence.analyze() for each bar (rolling window) to ensure
    identical computation to production. This is slow but correct.

    For efficiency, we compute the raw RSI series once (Wilder smoothing),
    then call the full analysis only at each bar to get divergence/conviction.

    Returns DataFrame with columns: [time, rsi_value, rsi_divergence_strength, rsi_conviction]
    """
    rsi_intel = RSIIntelligence()
    close = ohlc["close"].values.astype(float)

    # Step 1: Compute full RSI series efficiently (Wilder smoothing)
    # _calc_rsi_series uses np.diff internally → returns N-1 elements.
    # Pad front with 50.0 to align with OHLCV index.
    raw_rsi = rsi_intel._calc_rsi_series(close, RSI_PERIOD)
    rsi_series = np.concatenate(([50.0], raw_rsi))  # Now length == len(close)

    # Step 2: For each bar, compute divergence + conviction using RSIIntelligence
    # We pass a sliding window of close prices for divergence detection
    results = []
    window_size = 60  # Lookback for divergence detection

    for i in range(len(ohlc)):
        ts = ohlc.index[i]
        rsi_val = float(rsi_series[i])  # Full-series Wilder RSI (correct memory)

        if i < MIN_BARS:
            # Not enough history for full analysis — store raw RSI only
            results.append({
                'time': ts,
                'rsi_value': round(rsi_val, 1),
                'rsi_divergence_strength': 0.0,
                'rsi_conviction': 0.0,
            })
            continue

        # Full analysis on the window for divergence/conviction detection.
        # IMPORTANT: rsi_value comes from full-series (rsi_val above), NOT
        # from the windowed result. Wilder smoothing is exponential —
        # a 60-bar window doesn't have enough memory for correct RSI.
        # The windowed analysis is only used for divergence/conviction
        # which inherently need local pivot detection.
        start_idx = max(0, i - window_size)
        close_window = close[start_idx:i + 1]

        try:
            result = rsi_intel.analyze(close_window, regime_hint="NEUTRAL", period=RSI_PERIOD)
            results.append({
                'time': ts,
                'rsi_value': round(rsi_val, 1),  # ← FULL SERIES, not windowed
                'rsi_divergence_strength': round(result.divergence_strength, 4),
                'rsi_conviction': round(result.rsi_conviction, 4),
            })
        except Exception as e:
            # Fallback: use raw RSI from series
            results.append({
                'time': ts,
                'rsi_value': round(rsi_val, 1),
                'rsi_divergence_strength': 0.0,
                'rsi_conviction': 0.0,
            })

    return pd.DataFrame(results)


def backfill_ticker(store, ticker, dry_run=False):
    """Compute and write RSI data for one ticker."""
    sp(f"{ticker}")

    # Load OHLCV
    ohlc = store.load_bars(ticker, "1d")
    if ohlc is None or ohlc.empty:
        print(f"    ⚠️ No OHLCV data for {ticker}")
        return 0

    print(f"    OHLCV: {len(ohlc):,d} bars ({ohlc.index[0].date()} → {ohlc.index[-1].date()})")

    # Compute RSI
    t0 = time.time()
    rsi_df = compute_rsi_for_ticker(ticker, ohlc)
    elapsed = time.time() - t0
    print(f"    RSI computed: {len(rsi_df):,d} rows ({elapsed:.1f}s)")

    # Stats
    rsi_vals = rsi_df['rsi_value']
    div_vals = rsi_df['rsi_divergence_strength']
    conv_vals = rsi_df['rsi_conviction']
    print(f"    rsi_value:      mean={rsi_vals.mean():.1f}, std={rsi_vals.std():.2f}, "
          f"range=[{rsi_vals.min():.1f}, {rsi_vals.max():.1f}]")
    print(f"    divergence_str: mean={div_vals.mean():.4f}, std={div_vals.std():.4f}, "
          f"non-zero={(div_vals != 0).sum():,d}")
    print(f"    conviction:     mean={conv_vals.mean():.4f}, std={conv_vals.std():.4f}, "
          f"range=[{conv_vals.min():.2f}, {conv_vals.max():.2f}]")

    # Verify: std must be > 3 for rsi_value (not constant)
    if rsi_vals.std() < 3.0:
        print(f"    ❌ RSI std={rsi_vals.std():.2f} < 3.0 — something is wrong!")
        return 0

    # Verify no NaN/inf
    n_bad = rsi_df[['rsi_value', 'rsi_divergence_strength', 'rsi_conviction']].isna().sum().sum()
    n_inf = np.isinf(rsi_df[['rsi_value', 'rsi_divergence_strength', 'rsi_conviction']].values).sum()
    if n_bad > 0 or n_inf > 0:
        print(f"    ⚠️ {n_bad} NaN, {n_inf} Inf values — cleaning")
        rsi_df = rsi_df.fillna(0.0)
        rsi_df = rsi_df.replace([np.inf, -np.inf], 0.0)

    if dry_run:
        print(f"    [DRY RUN] Would update {len(rsi_df):,d} rows")
        return len(rsi_df)

    # Write to DB using batch UPDATE (same pattern as Kalman backfill)
    conn = store.engine.raw_connection()
    cur = conn.cursor()

    timestamps = rsi_df['time'].tolist()
    rsi_values = rsi_df['rsi_value'].tolist()
    div_values = rsi_df['rsi_divergence_strength'].tolist()
    conv_values = rsi_df['rsi_conviction'].tolist()

    batch_size = 500
    updated = 0
    for start in range(0, len(timestamps), batch_size):
        end = min(start + batch_size, len(timestamps))
        batch_ts = timestamps[start:end]
        batch_rsi = rsi_values[start:end]
        batch_div = div_values[start:end]
        batch_conv = conv_values[start:end]

        values = []
        for ts, rv, dv, cv in zip(batch_ts, batch_rsi, batch_div, batch_conv):
            values.append(f"('{ts}'::timestamptz, {rv}, {dv}, {cv})")
        values_str = ",\n".join(values)

        sql = f"""
            UPDATE engine.channel_snapshots cs
            SET rsi_value = v.rv,
                rsi_divergence_strength = v.dv,
                rsi_conviction = v.cv
            FROM (VALUES {values_str}) AS v(ts, rv, dv, cv)
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
    parser = argparse.ArgumentParser(description="RSI Backfill")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ticker", type=str, default=None)
    args = parser.parse_args()

    tickers = [args.ticker] if args.ticker else TICKERS

    p("RSI BACKFILL — rsi_value + divergence + conviction")
    print(f"  Tickers: {len(tickers)}")
    print(f"  RSI Period: {RSI_PERIOD}")
    if args.dry_run:
        print(f"  Mode: DRY RUN (no writes)")

    t0 = time.time()
    store = TimescaleDataStore()

    # Pre-check: variance per ticker (detect fake data)
    sp("PRE-CHECK: VARIANCE (std=0 = fake)")
    q = """
        SELECT ticker,
               COUNT(*) as total,
               ROUND(STDDEV(rsi_value)::numeric, 2) as rsi_std,
               ROUND(AVG(rsi_value)::numeric, 1) as rsi_avg,
               ROUND(MIN(rsi_value)::numeric, 1) as rsi_min,
               ROUND(MAX(rsi_value)::numeric, 1) as rsi_max
        FROM engine.channel_snapshots
        WHERE ticker = ANY(%s) AND sigma_tide IS NOT NULL
        GROUP BY ticker ORDER BY ticker
    """
    pre = pd.read_sql(q, store.engine, params=(tickers,))
    for _, row in pre.iterrows():
        std = row['rsi_std'] if row['rsi_std'] else 0
        if std < 1.0:
            status = f"❌ FAKE (std={std}, avg={row['rsi_avg']})"
        else:
            status = f"✅ REAL (std={std}, range=[{row['rsi_min']}, {row['rsi_max']}])"
        print(f"    {row['ticker']:>6s}: {row['total']:>6,d} bars {status}")

    # Backfill
    total_updated = 0
    for ticker in tickers:
        n = backfill_ticker(store, ticker, dry_run=args.dry_run)
        total_updated += n

    # Post-check
    if not args.dry_run:
        sp("POST-CHECK: VARIANCE")
        post = pd.read_sql(q, store.engine, params=(tickers,))
        all_good = True
        for _, row in post.iterrows():
            std = row['rsi_std'] if row['rsi_std'] else 0
            if std < 1.0:
                status = f"❌ STILL FAKE (std={std})"
                all_good = False
            else:
                status = f"✅ (std={std}, range=[{row['rsi_min']}, {row['rsi_max']}])"
            print(f"    {row['ticker']:>6s}: {status}")

        if all_good:
            print(f"\n    ★★★ ALL TICKERS HAVE REAL RSI DATA ★★★")
        else:
            print(f"\n    ✖ SOME TICKERS STILL HAVE FAKE DATA")

    store.close()
    elapsed = time.time() - t0

    p("RSI BACKFILL COMPLETE")
    print(f"  Total updated: {total_updated:,d} rows")
    print(f"  Time: {elapsed:.1f}s ({elapsed/60:.1f} min)")


if __name__ == "__main__":
    main()
