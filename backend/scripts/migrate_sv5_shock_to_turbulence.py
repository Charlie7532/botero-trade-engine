"""
Migrate SV5_SHOCK ticker to SV5_TURBULENCE in Neon PostgreSQL Vault.
Updates both market.ohlcv_bars and market.ticker_metadata tables.
"""
import sys
import os
import logging

sys.path.append("/root/botero-trade")
os.chdir("/root/botero-trade")

from dotenv import load_dotenv
load_dotenv(".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_sv5_shock")

def migrate():
    store = TimescaleDataStore()
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            # 1. Update ohlcv_bars
            cur.execute("""
                UPDATE market.ohlcv_bars
                SET ticker = 'SV5_TURBULENCE'
                WHERE ticker = 'SV5_SHOCK';
            """)
            bars_updated = cur.rowcount
            logger.info(f"Updated {bars_updated} bars in market.ohlcv_bars from SV5_SHOCK to SV5_TURBULENCE")

            # 2. Update ticker_metadata
            cur.execute("""
                UPDATE market.ticker_metadata
                SET ticker = 'SV5_TURBULENCE'
                WHERE ticker = 'SV5_SHOCK';
            """)
            meta_updated = cur.rowcount
            logger.info(f"Updated {meta_updated} rows in market.ticker_metadata from SV5_SHOCK to SV5_TURBULENCE")

            conn.commit()
            logger.info("✅ Migration committed successfully!")
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Migration failed: {e}")
        raise
    finally:
        store._put(conn)

if __name__ == "__main__":
    migrate()
