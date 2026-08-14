#!/usr/bin/env python3
"""
Populate prev_leg_return and prev_leg_duration for all major tickers in Neon Vault.
===================================================================================
"""
import sys
import logging
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PopulateAllTickers")

SCALES = ["zz25", "zz50", "zz75"]
TICKERS = ["SPY", "QQQ", "IWM", "DIA"]


def populate_ticker(store: TimescaleDataStore, ticker: str):
    conn = store._conn()
    try:
        total_updated = 0
        for scale in SCALES:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT leg_id, start_timestamp, start_price, end_price,
                           (end_timestamp - start_timestamp) AS duration_interval
                    FROM market.zigzag_legs
                    WHERE ticker = %s AND scale = %s
                    ORDER BY start_timestamp ASC;
                """, [ticker, scale])
                rows = cur.fetchall()

            if len(rows) < 2:
                logger.info(f"  {ticker} {scale}: {len(rows)} legs, skipping")
                continue

            updates = []
            for i in range(1, len(rows)):
                prev_leg_id, _, prev_start_px, prev_end_px, prev_dur = rows[i - 1]
                curr_leg_id = rows[i][0]

                prev_return = (float(prev_end_px) / float(prev_start_px)) - 1.0
                prev_duration = max(prev_dur.days, 1) if hasattr(prev_dur, 'days') else 1

                updates.append((prev_return, prev_duration, curr_leg_id))

            with conn.cursor() as cur:
                cur.executemany("""
                    UPDATE market.zigzag_legs
                    SET prev_leg_return = %s, prev_leg_duration = %s
                    WHERE leg_id = %s;
                """, updates)

            total_updated += len(updates)
            logger.info(f"  {ticker} {scale}: populated {len(updates)}/{len(rows)} legs")

        conn.commit()
        logger.info(f"✅ Finished {ticker}: {total_updated} legs updated.")
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ {ticker} failed: {e}")
        raise
    finally:
        store._put(conn)


def main():
    store = TimescaleDataStore()
    for t in TICKERS:
        populate_ticker(store, t)
    logger.info("🎉 ALL TICKERS POPULATED SUCCESSFULLY.")


if __name__ == "__main__":
    main()
