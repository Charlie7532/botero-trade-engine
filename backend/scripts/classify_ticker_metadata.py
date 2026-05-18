"""
Classify all tickers in ticker_metadata and migrate VIX to ohlcv_bars.
Ensures a unified data access pattern: load_bars(ticker, "1d") for everything.

Usage:
    PYTHONPATH=. python backend/scripts/classify_ticker_metadata.py
"""
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# Ticker classification registry
TICKER_REGISTRY = {
    # ETFs
    "SPY":      {"sector": "Broad Market",   "industry": "ETF", "cap": "MEGA"},
    "QQQ":      {"sector": "Technology",     "industry": "ETF", "cap": "MEGA"},
    # Indicators (stored in ohlcv_bars as pseudo-OHLCV)
    "FG":       {"sector": "Sentiment",      "industry": "INDICATOR", "cap": None},
    "CBOE_PCR": {"sector": "Options Flow",   "industry": "INDICATOR", "cap": None},
    "VIX":      {"sector": "Volatility",     "industry": "INDICATOR", "cap": None},
    "VVIX":     {"sector": "Volatility",     "industry": "INDICATOR", "cap": None},
}


def migrate_vix_to_ohlcv(store):
    """
    Copy VIX from market.macro_data → market.ohlcv_bars as ticker 'VIX'.
    macro_data stores (time, name='vix', value=close).
    We create OHLCV bars with open=high=low=close=value, volume=0.
    """
    logger.info("Migrating VIX from macro_data → ohlcv_bars...")

    conn = store._conn()
    try:
        with conn.cursor() as cur:
            # Check if VIX already exists in ohlcv_bars
            cur.execute(
                "SELECT COUNT(*) FROM market.ohlcv_bars WHERE ticker = 'VIX' AND timeframe = '1d'"
            )
            existing = cur.fetchone()[0]
            if existing > 100:
                logger.info(f"  VIX already in ohlcv_bars ({existing} bars), skipping migration")
                return

            # Read from macro_data
            cur.execute(
                "SELECT time, value FROM market.macro_data WHERE name = 'vix' ORDER BY time"
            )
            rows = cur.fetchall()
            if not rows:
                logger.warning("  No VIX data in macro_data")
                return

            logger.info(f"  Found {len(rows)} VIX points in macro_data")

            # Insert into ohlcv_bars (open=high=low=close=value)
            insert_rows = [
                (ts, "VIX", "1d", float(val), float(val), float(val), float(val), 0)
                for ts, val in rows if val is not None
            ]

            from psycopg2.extras import execute_values
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
        logger.info(f"  ✅ VIX migrated: {len(insert_rows)} bars → ohlcv_bars")
    except Exception as e:
        conn.rollback()
        logger.error(f"  VIX migration failed: {e}")
    finally:
        store._put(conn)


def classify_tickers(store):
    """Upsert ticker_metadata for all registered tickers."""
    logger.info("Classifying ticker metadata...")

    for ticker, meta in TICKER_REGISTRY.items():
        try:
            store.upsert_ticker_metadata(
                ticker=ticker,
                sector=meta["sector"],
                industry=meta["industry"],
                market_cap_bucket=meta["cap"],
            )
            logger.info(f"  {ticker:10s} → {meta['industry']}/{meta['sector']}")
        except Exception as e:
            logger.warning(f"  {ticker} metadata failed: {e}")


def print_vault_summary(store):
    """Print current state of ohlcv_bars by asset type."""
    logger.info("\n═══ Vault Summary ═══")
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    b.ticker,
                    COALESCE(m.industry, 'UNKNOWN') as asset_type,
                    COALESCE(m.sector, 'Unknown') as sector,
                    COUNT(*) as bars,
                    MIN(b.time)::date as start,
                    MAX(b.time)::date as end
                FROM market.ohlcv_bars b
                LEFT JOIN market.ticker_metadata m ON b.ticker = m.ticker
                WHERE b.timeframe = '1d'
                AND b.ticker IN ('SPY','QQQ','FG','CBOE_PCR','VIX','VVIX')
                GROUP BY b.ticker, m.industry, m.sector
                ORDER BY asset_type, b.ticker
            """)
            rows = cur.fetchall()

            current_type = None
            for ticker, asset_type, sector, bars, start, end in rows:
                if asset_type != current_type:
                    current_type = asset_type
                    print(f"\n  [{asset_type}]")
                print(f"    {ticker:10s} {sector:15s} {bars:6d} bars  {start} → {end}")

    finally:
        store._put(conn)


def main():
    from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
    store = TimescaleDataStore()

    migrate_vix_to_ohlcv(store)
    classify_tickers(store)
    print_vault_summary(store)

    store.close()
    logger.info("\n═══ Classification Complete ═══")


if __name__ == "__main__":
    main()
