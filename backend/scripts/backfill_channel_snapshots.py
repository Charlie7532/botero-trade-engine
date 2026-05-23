#!/usr/bin/env python3
"""
Backfill Channel Snapshots — One-Time Historical Computation
================================================================
Computes ChannelSnapshot for EVERY bar of EVERY ticker in the Vault
and persists to engine.channel_snapshots.

This runs ONCE. After that, the daily daemon appends new bars.

Estimated: 17 tickers × ~5,000 bars = ~85,000 snapshots
Time: ~5-10 minutes (depends on DB latency)

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# All tickers in the Vault (from AGENTS.md registry)
TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "AMZN", "COST", "HD", "HON",
    "IBM", "JNJ", "JPM", "MCD", "MRK", "PEP", "PG", "WMT", "XOM",
]

BATCH_SIZE = 500  # Rows per DB upsert
MIN_BARS = 250    # Minimum bars needed for compute_channel_snapshot


def backfill_ticker(store: TimescaleDataStore, ticker: str) -> int:
    """Compute and persist snapshots for all bars of a ticker."""
    ohlc = store.load_bars(ticker, "1d")
    if ohlc is None or len(ohlc) < MIN_BARS:
        logger.warning(f"  {ticker}: skipped (only {len(ohlc) if ohlc is not None else 0} bars)")
        return 0

    close = ohlc["close"].values.astype(float)
    high = ohlc["high"].values.astype(float)
    low = ohlc["low"].values.astype(float)
    volume = ohlc["volume"].values.astype(float)
    timestamps = ohlc.index.tolist()

    # Check existing count to report progress
    existing = store.count_snapshots(ticker, "1d")

    snapshots = []
    snap_timestamps = []
    total_persisted = 0

    for idx in range(MIN_BARS, len(ohlc)):
        snap = compute_channel_snapshot(close, high, low, volume, idx)
        if snap is None:
            continue

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

    logger.info(
        f"  {ticker}: {total_persisted} snapshots persisted "
        f"(was {existing}, bars={len(ohlc)}, valid from idx {MIN_BARS})"
    )
    return total_persisted


def main():
    print("=" * 80)
    print("  BACKFILL CHANNEL SNAPSHOTS — Feature Lake Phase 1")
    print("  41 fields × every bar × every ticker → engine.channel_snapshots")
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
