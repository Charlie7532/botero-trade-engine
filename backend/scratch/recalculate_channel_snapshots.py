#!/usr/bin/env python3
"""
Recalculate Channel Snapshots — Only SPY and QQQ
====================================================================
Step 2 of the Remediation Plan:
  1. Delete all existing snapshots for SPY/QQQ in engine.channel_snapshots
  2. Compute and persist new clean snapshots for SPY/QQQ
"""
import os, sys, time, logging
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "backend" / "scripts"))

from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

import numpy as np
from backend.modules.shared.domain.rules.compute_channel import compute_channel_snapshot
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.price_analysis.application.use_cases.analyze_rsi import RSIIntelligence
from backend.modules.volume_intelligence.application.use_cases.track_volume_dynamics import KalmanVolumeTracker
from backfill_channel_snapshots import _precompute_rsi, _precompute_kalman, backfill_ticker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

TICKERS = ["SPY", "QQQ"]

def main():
    print("=" * 80)
    print("  RECALCULATING CHANNEL SNAPSHOTS FOR SPY & QQQ ONLY")
    print("=" * 80)
    
    store = TimescaleDataStore()
    conn = store.engine.raw_connection()
    cur = conn.cursor()
    
    try:
        # 1. PURGE SNAPSHOTS
        print("\n1. PURGING OLD SNAPSHOTS FOR SPY & QQQ...")
        cur.execute("DELETE FROM engine.channel_snapshots WHERE ticker IN ('SPY', 'QQQ');")
        purged = cur.rowcount
        conn.commit()
        print(f"   ✅ Purged {purged:,d} snapshots for SPY and QQQ.")
        
        # 2. RECALCULATE
        print("\n2. RECALCULATING SNAPSHOTS...")
        t0 = time.time()
        for ticker in TICKERS:
            t1 = time.time()
            n = backfill_ticker(store, ticker)
            elapsed = time.time() - t1
            print(f"   ✅ {ticker}: {n:,d} snapshots calculated in {elapsed:.1f}s")
            
        total_elapsed = time.time() - t0
        print(f"\n🎉 ALL SNAPSHOTS RECALCULATED SUCCESSFULLY in {total_elapsed:.1f}s!")
        
        # 3. VERIFICATION
        print("\n3. POST-RECALCULATION VERIFICATION...")
        cur.execute("""
            SELECT ticker, COUNT(*), COUNT(DISTINCT DATE(timestamp)) 
            FROM engine.channel_snapshots 
            WHERE ticker IN ('SPY', 'QQQ')
            GROUP BY ticker;
        """)
        rows = cur.fetchall()
        for r in rows:
            ticker, count, unique_days = r
            dups = count - unique_days
            print(f"   {ticker}: Snapshots count={count:,d}, Unique Days={unique_days:,d}, Duplicates={dups:,d}")
            if dups > 0:
                print(f"   🔴 ERROR: Duplicates still exist for {ticker} in engine.channel_snapshots!")
            else:
                print(f"   ✅ Snapshots integrity verified for {ticker}: 0 duplicates.")
                
    except Exception as e:
        conn.rollback()
        print(f"🔴 ERROR: Recalculation failed: {str(e)}")
    finally:
        cur.close()
        conn.close()
        store.close()

if __name__ == "__main__":
    main()
