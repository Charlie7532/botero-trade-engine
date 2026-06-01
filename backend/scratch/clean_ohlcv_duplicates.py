#!/usr/bin/env python3
"""
Clean OHLCV Duplicates — Purge SPY/QQQ duplicate midnight bars
===================================================================
Connects to Neon TimescaleDataStore and performs transaction-safe
cleaning of duplicate bars for SPY and QQQ.

Fase E: Plan de Remediación - Technical execution.
"""
import os, sys, time
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))

from dotenv import load_dotenv
load_dotenv(root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def main():
    store = TimescaleDataStore()
    conn = store.engine.raw_connection()
    cur = conn.cursor()
    
    try:
        log("1. AUDITING CURRENT DUPLICATES...")
        cur.execute("""
            SELECT ticker, COUNT(*), COUNT(DISTINCT DATE(time)) 
            FROM market.ohlcv_bars 
            WHERE ticker IN ('SPY', 'QQQ') AND timeframe = '1d'
            GROUP BY ticker;
        """)
        rows = cur.fetchall()
        for r in rows:
            ticker, count, unique_days = r
            dups = count - unique_days
            log(f"   {ticker}: Total={count:,d}, Unique Days={unique_days:,d}, Duplicates={dups:,d}")
            
        # 2. CREATE BACKUP TABLE IF NOT EXISTS
        log("2. CREATING BACKUP TABLE market.ohlcv_bars_backup_20260529...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS market.ohlcv_bars_backup_20260529 AS 
            SELECT * FROM market.ohlcv_bars WHERE ticker IN ('SPY', 'QQQ');
        """)
        conn.commit()
        log("   Backup table verified.")
        
        # 3. PURGING DUPLICATES
        log("3. DELETING DUPLICATE MIDNIGHT BARS (time::time = '00:00:00')...")
        cur.execute("""
            DELETE FROM market.ohlcv_bars 
            WHERE ticker IN ('SPY', 'QQQ') 
              AND timeframe = '1d'
              AND time::time = '00:00:00'
              AND (ticker, DATE(time)) IN (
                SELECT ticker, DATE(time) FROM market.ohlcv_bars 
                WHERE ticker IN ('SPY', 'QQQ') AND timeframe = '1d'
                GROUP BY ticker, DATE(time) HAVING COUNT(*) > 1
              );
        """)
        deleted_count = cur.rowcount
        conn.commit()
        log(f"   ✅ Deleted {deleted_count:,d} duplicate midnight bars.")
        
        # 4. POST-CLEANING VALIDATION
        log("4. RUNNING POST-CLEANING INTEGRITY CHECKS...")
        cur.execute("""
            SELECT ticker, COUNT(*), COUNT(DISTINCT DATE(time)) 
            FROM market.ohlcv_bars 
            WHERE ticker IN ('SPY', 'QQQ') AND timeframe = '1d'
            GROUP BY ticker;
        """)
        rows = cur.fetchall()
        failures = 0
        for r in rows:
            ticker, count, unique_days = r
            dups = count - unique_days
            log(f"   {ticker}: Total={count:,d}, Unique Days={unique_days:,d}, Duplicates={dups:,d}")
            if dups > 0:
                log(f"   🔴 ERROR: Duplicates still exist for {ticker}!")
                failures += 1
            else:
                log(f"   ✅ Integrity verified for {ticker}: 0 duplicates.")
                
        # Also check channel_snapshots for duplicate timestamps
        log("5. CHECKING engine.channel_snapshots FOR DUPLICATES...")
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
            log(f"   Snapshots {ticker}: Total={count:,d}, Unique Days={unique_days:,d}, Duplicates={dups:,d}")
            
        if failures == 0:
            log("🎉 DATABASE CLEANUP SUCCESSFULLY COMPLETED!")
        else:
            log("⚠️ DATABASE CLEANUP ENCOUNTERED INTEGRITY CHECK ERRORS.")
            
    except Exception as e:
        conn.rollback()
        log(f"🔴 DATABASE TRANSACTION FAILED: {str(e)}")
    finally:
        cur.close()
        conn.close()
        store.close()

if __name__ == "__main__":
    main()
