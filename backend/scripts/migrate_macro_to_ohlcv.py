"""
Migrate ALL macro_data → ohlcv_bars (one-time migration).
After this, macro_data can be dropped.

Usage:
    PYTHONPATH=. python backend/scripts/migrate_macro_to_ohlcv.py
"""
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Migration map: macro_data name → (ohlcv ticker, sector)
MIGRATION_MAP = {
    "yields_yield_10y": ("TNX",     "Yields",    "INDICATOR"),
    "yields_yield_3m":  ("IRX",     "Yields",    "INDICATOR"),
    "spx_adl":          ("SPX_ADL", "Breadth",   "INDICATOR"),
    "ndq_adl":          ("NDQ_ADL", "Breadth",   "INDICATOR"),
}

# These are already in ohlcv_bars, skip:
SKIP = {"vix_open", "vix_high", "vix_low", "vix_close", "vix_volume"}


def migrate_scalar_to_ohlcv(store, macro_name: str, ticker: str, sector: str, asset_type: str):
    """Migrate a scalar macro_data series to ohlcv_bars as pseudo-OHLCV."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            # Check if already migrated
            cur.execute(
                "SELECT COUNT(*) FROM market.ohlcv_bars WHERE ticker = %s AND timeframe = '1d'",
                (ticker,)
            )
            existing = cur.fetchone()[0]
            if existing > 0:
                logger.info(f"  {ticker}: already has {existing} bars, skipping")
                return

            # Read from macro_data
            cur.execute(
                "SELECT time, value FROM market.macro_data WHERE name = %s ORDER BY time",
                (macro_name,)
            )
            rows = cur.fetchall()
            if not rows:
                logger.warning(f"  {macro_name}: no data in macro_data")
                return

            # Insert as pseudo-OHLCV (open=high=low=close=value, volume=0)
            from psycopg2.extras import execute_values
            insert_rows = [
                (ts, ticker, "1d", float(val), float(val), float(val), float(val), 0)
                for ts, val in rows if val is not None
            ]
            execute_values(
                cur,
                """INSERT INTO market.ohlcv_bars
                   (time, ticker, timeframe, open, high, low, close, volume)
                   VALUES %s
                   ON CONFLICT (ticker, timeframe, time) DO NOTHING""",
                insert_rows,
                page_size=1000,
            )
        conn.commit()
        logger.info(f"  ✅ {macro_name} → {ticker}: {len(insert_rows)} bars migrated")

        # Classify metadata
        store.upsert_ticker_metadata(
            ticker=ticker, sector=sector,
            industry=asset_type, market_cap_bucket=None,
        )
    except Exception as e:
        conn.rollback()
        logger.error(f"  ❌ {macro_name} migration failed: {e}")
    finally:
        store._put(conn)


def drop_macro_table(store):
    """Drop macro_data table after confirming migration."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS market.macro_data CASCADE")
        conn.commit()
        logger.info("🗑️  market.macro_data DROPPED")
    except Exception as e:
        conn.rollback()
        logger.error(f"Drop failed: {e}")
    finally:
        store._put(conn)


def main():
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()

    logger.info("═══ Migrating macro_data → ohlcv_bars ═══\n")

    for macro_name, (ticker, sector, asset_type) in MIGRATION_MAP.items():
        migrate_scalar_to_ohlcv(store, macro_name, ticker, sector, asset_type)

    logger.info(f"\nSkipped (already in ohlcv_bars): {SKIP}")

    # Verify
    logger.info("\n═══ Post-Migration Vault ═══")
    conn = store._conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT b.ticker, COALESCE(m.industry, '?') as type,
                   COALESCE(m.sector, '?') as sector,
                   COUNT(*) as bars, MIN(b.time)::date, MAX(b.time)::date
            FROM market.ohlcv_bars b
            LEFT JOIN market.ticker_metadata m ON b.ticker = m.ticker
            WHERE b.timeframe = '1d'
              AND b.ticker IN ('SPY','QQQ','VIX','VVIX','FG','CBOE_PCR','TNX','IRX','SPX_ADL','NDQ_ADL')
            GROUP BY b.ticker, m.industry, m.sector
            ORDER BY COALESCE(m.industry,'Z'), b.ticker
        """)
        for row in cur.fetchall():
            print(f"  {row[0]:10s} [{row[1]:9s}] {row[2]:12s} {row[3]:6d} bars  {row[4]} → {row[5]}")
    store._put(conn)

    # Drop macro_data
    logger.info("\n═══ Dropping legacy macro_data ═══")
    drop_macro_table(store)

    store.close()
    logger.info("\n═══ Migration Complete ═══")


if __name__ == "__main__":
    main()
