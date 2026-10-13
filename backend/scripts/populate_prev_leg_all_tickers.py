#!/usr/bin/env python3
"""
Populate prev_leg_return and prev_leg_duration for all major tickers in Neon Vault.
===================================================================================
High-performance batch populator ensuring strict determinism via (start_timestamp, leg_id).
"""
import sys
import time
import logging
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PopulateAllTickers")

BATCH_SIZE = 25


def populate_ticker_batch(store: TimescaleDataStore, tickers: list[str]) -> int:
    """Populate prev_leg_return and prev_leg_duration for a batch of tickers using set-based SQL."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                WITH ordered AS (
                    SELECT leg_id,
                           LAG(start_price) OVER (PARTITION BY ticker, scale ORDER BY start_timestamp, leg_id) AS prev_start_px,
                           LAG(end_price) OVER (PARTITION BY ticker, scale ORDER BY start_timestamp, leg_id) AS prev_end_px,
                           LAG(GREATEST((end_timestamp - start_timestamp), INTERVAL '1 day'))
                               OVER (PARTITION BY ticker, scale ORDER BY start_timestamp, leg_id) AS prev_dur
                    FROM market.zigzag_legs
                    WHERE ticker = ANY(%s)
                )
                UPDATE market.zigzag_legs z
                SET prev_leg_return = (o.prev_end_px / o.prev_start_px) - 1.0,
                    prev_leg_duration = EXTRACT(DAY FROM o.prev_dur)::INTEGER
                FROM ordered o
                WHERE z.leg_id = o.leg_id AND o.prev_start_px IS NOT NULL;
            """, (tickers,))
            updated_count = cur.rowcount
        conn.commit()
        return updated_count
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Batch {tickers[:3]}... failed: {e}")
        raise
    finally:
        store._put(conn)


def get_target_tickers(store: TimescaleDataStore, all_tickers: bool = False) -> list[str]:
    """Get list of tickers needing population."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            if all_tickers:
                cur.execute("SELECT DISTINCT ticker FROM market.zigzag_legs ORDER BY ticker;")
            else:
                # Target real financial assets (stocks and ETFs)
                cur.execute("""
                    SELECT DISTINCT z.ticker
                    FROM market.zigzag_legs z
                    LEFT JOIN market.ticker_metadata m ON m.ticker = z.ticker
                    WHERE m.industry != 'INDICATOR' OR m.industry IS NULL
                    ORDER BY z.ticker;
                """)
            rows = cur.fetchall()
            return [r[0] for r in rows]
    finally:
        store._put(conn)


def main():
    store = TimescaleDataStore()
    all_flag = "--all" in sys.argv
    tickers = get_target_tickers(store, all_tickers=all_flag)
    logger.info(f"Targeting {len(tickers)} tickers for prev_leg kinematics population (all={all_flag})...")

    total_updated = 0
    t0_global = time.time()
    n_batches = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE

    for idx in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[idx : idx + BATCH_SIZE]
        batch_num = (idx // BATCH_SIZE) + 1
        t0_batch = time.time()
        
        n_up = populate_ticker_batch(store, batch)
        total_updated += n_up
        elapsed = time.time() - t0_batch
        
        logger.info(
            f"[{batch_num}/{n_batches}] Updated {n_up:,} legs across {len(batch)} tickers ({batch[0]}..{batch[-1]}) in {elapsed:.2f}s"
        )

    logger.info(
        f"🎉 POPULATION COMPLETED: {total_updated:,} legs updated across {len(tickers)} tickers in {time.time() - t0_global:.1f}s."
    )


if __name__ == "__main__":
    main()
