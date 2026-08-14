#!/usr/bin/env python3
"""
Migration 003: Add prev_leg_return and prev_leg_duration to market.zigzag_legs
==============================================================================
Reversible migration that adds domino-effect columns and populates them for SPY.

Usage:
  python -m backend.migrations.003_add_prev_leg_columns --up
  python -m backend.migrations.003_add_prev_leg_columns --down
  python -m backend.migrations.003_add_prev_leg_columns --up --populate
"""
import argparse
import logging
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Migration003")

SCALES = ["zz25", "zz50", "zz75"]


def migrate_up(store: TimescaleDataStore):
    """Add prev_leg_return and prev_leg_duration columns."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE market.zigzag_legs
                ADD COLUMN IF NOT EXISTS prev_leg_return NUMERIC,
                ADD COLUMN IF NOT EXISTS prev_leg_duration INTEGER;
            """)
        conn.commit()
        logger.info("✅ migrate_up: Added prev_leg_return, prev_leg_duration columns.")
    finally:
        store._put(conn)


def migrate_down(store: TimescaleDataStore):
    """Remove prev_leg_return and prev_leg_duration columns."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE market.zigzag_legs
                DROP COLUMN IF EXISTS prev_leg_return,
                DROP COLUMN IF EXISTS prev_leg_duration;
            """)
        conn.commit()
        logger.info("✅ migrate_down: Dropped prev_leg_return, prev_leg_duration columns.")
    finally:
        store._put(conn)


def populate(store: TimescaleDataStore, ticker: str = "SPY"):
    """Populate prev_leg_return and prev_leg_duration for a ticker across all scales.

    For each scale, ordered by start_timestamp ASC:
      prev_leg_return = (end_price[i-1] / start_price[i-1]) - 1.0  (signed decimal)
      prev_leg_duration = duration_bars[i-1]                        (days)
    First leg of each scale gets NULL.
    """
    conn = store._conn()
    try:
        total_updated = 0
        for scale in SCALES:
            with conn.cursor() as cur:
                # Fetch legs ordered by start_timestamp (NOT by leg_id)
                cur.execute("""
                    SELECT leg_id, start_timestamp, start_price, end_price,
                           (end_timestamp - start_timestamp) AS duration_interval
                    FROM market.zigzag_legs
                    WHERE ticker = %s AND scale = %s
                    ORDER BY start_timestamp ASC;
                """, [ticker, scale])
                rows = cur.fetchall()

            if len(rows) < 2:
                logger.info(f"  {scale}: {len(rows)} legs, skipping (need ≥2)")
                continue

            # Build update batch: for each leg i>0, prev = leg i-1
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
            logger.info(f"  {scale}: populated {len(updates)}/{len(rows)} legs")

        conn.commit()
        logger.info(f"✅ populate: {total_updated} legs updated for {ticker}")
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ populate failed: {e}")
        raise
    finally:
        store._put(conn)


def main():
    parser = argparse.ArgumentParser(description="Migration 003: prev_leg columns")
    parser.add_argument("--up", action="store_true", help="Add columns")
    parser.add_argument("--down", action="store_true", help="Remove columns")
    parser.add_argument("--populate", action="store_true", help="Populate for SPY")
    parser.add_argument("--ticker", default="SPY", help="Ticker to populate (default: SPY)")
    args = parser.parse_args()

    if not any([args.up, args.down, args.populate]):
        parser.print_help()
        return

    store = TimescaleDataStore()

    if args.down:
        migrate_down(store)
        return

    if args.up:
        migrate_up(store)

    if args.populate:
        populate(store, args.ticker)


if __name__ == "__main__":
    main()
