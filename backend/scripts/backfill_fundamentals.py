"""
Backfill Fundamental Data — One-shot script
===========================================
Fetches deep screening data (QGARP) from GuruFocus for all tickers
in market.ohlcv_bars and persists to market.mcp_snapshots.

Usage:
    python -m backend.scripts.backfill_fundamentals
"""
import logging
import os
import sys
import time
from datetime import datetime, UTC, timedelta

import psycopg2
from backend.modules.portfolio_management.infrastructure.gurufocus_mcp_bridge import GuruFocusMCPBridge
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

def main():
    dsn = os.environ.get("POSTGRES_URL")
    if not dsn:
        logger.error("POSTGRES_URL not set")
        sys.exit(1)

    store = TimescaleDataStore(dsn)
    bridge = GuruFocusMCPBridge()

    # 1. Get all tickers from OHLCV
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT ticker FROM market.ohlcv_bars WHERE timeframe = '1d' ORDER BY ticker")
            all_tickers = [r[0] for r in cur.fetchall()]

        # 2. Get tickers already screened in the last 24 hours
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ticker FROM market.mcp_snapshots 
                WHERE category = 'fundamental/screening' 
                AND time >= NOW() - INTERVAL '24 hours'
            """)
            already_done = {r[0] for r in cur.fetchall()}

        remaining = [t for t in all_tickers if t not in already_done and t not in ('VIX', 'SKEW', 'VVIX')]
        logger.info(f"Total tickers: {len(all_tickers)}, Already screened (24h): {len(already_done)}, Remaining: {len(remaining)}")

        if not remaining:
            logger.info("All tickers already screened — nothing to do")
            return

        # 3. Ingest remaining
        success = 0
        failed = 0
        
        # GuruFocus rate limit is strict. 1.5s per call, deep_screening makes 2 calls = 3s/ticker.
        for ticker in remaining:
            try:
                # Basic logging to show progress
                data = bridge.fetch_deep_screening(ticker)
                if data and data.get("gf_score"):
                    store.save_mcp_snapshot("fundamental/screening", ticker, data)
                    success += 1
                    logger.info(f"  ✅ {ticker}: GF Score = {data.get('gf_score')} ({success}/{len(remaining)})")
                else:
                    logger.warning(f"  ⚠️ {ticker}: No data or GF Score missing")
                    failed += 1
            except Exception as e:
                logger.error(f"  ❌ {ticker}: Failed ({e})")
                failed += 1
                time.sleep(5)

        logger.info(f"\n✅ Fundamental backfill complete:")
        logger.info(f"   Success: {success}")
        logger.info(f"   Failed/Empty: {failed}")
    
    finally:
        store.close()
        conn.close()

if __name__ == "__main__":
    main()
