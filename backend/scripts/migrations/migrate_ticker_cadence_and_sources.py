"""
Migration: Add release_cadence column and calibrate update_source in market.ticker_metadata
==========================================================================================
1. Adds release_cadence column (VARCHAR(32), DEFAULT 'INTRADAY').
2. Updates update_source and release_cadence for:
   - FRED Treasury yields (DGS10, DGS2, DTB3, DFII10, DFII5) -> vault_fred_macro, T_MINUS_1_FED
   - CBOE Put/Call Ratios (CBOE_PCR, CBOE_CPCE) -> vault_cboe_pcr, EOD
   - CBOE Indices (VVIX, SKEW) -> vault_cboe_indices, EOD
   - Synthetic Derived Stations (BSI, SV5_TURBULENCE, ROTATION_INDEX, CREDIT_RATIO, YIELD_SPREAD) -> vault_derived, DERIVED_INTRADAY
   - Orphaned synthetic F&G components -> none_historical_only, EOD
   - Breadth indicators (S5*, SV5*, VBI*) -> vault_breadth_calc, DERIVED_INTRADAY
"""
import sys
import logging
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MigrateCadence")


def run_migration():
    store = TimescaleDataStore()
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            logger.info("1. Ensuring release_cadence column exists...")
            cur.execute("""
                ALTER TABLE market.ticker_metadata 
                ADD COLUMN IF NOT EXISTS release_cadence VARCHAR(32) DEFAULT 'INTRADAY';
            """)

            logger.info("2. Calibrating FRED Yield series...")
            fred_tickers = ("DFII10", "DFII5", "DGS10", "DGS2", "DTB3")
            cur.execute("""
                UPDATE market.ticker_metadata
                SET update_source = 'vault_fred_macro',
                    release_cadence = 'T_MINUS_1_FED',
                    updated_at = NOW()
                WHERE ticker = ANY(%s);
            """, (list(fred_tickers),))
            logger.info(f"   Updated {cur.rowcount} FRED tickers")

            logger.info("3. Calibrating CBOE Put/Call Ratios...")
            cboe_pcr_tickers = ("CBOE_PCR", "CBOE_CPCE")
            cur.execute("""
                UPDATE market.ticker_metadata
                SET update_source = 'vault_cboe_pcr',
                    release_cadence = 'EOD',
                    updated_at = NOW()
                WHERE ticker = ANY(%s);
            """, (list(cboe_pcr_tickers),))
            logger.info(f"   Updated {cur.rowcount} CBOE PCR tickers")

            logger.info("4. Calibrating CBOE Indices (VVIX, SKEW)...")
            cboe_idx_tickers = ("VVIX", "SKEW")
            cur.execute("""
                UPDATE market.ticker_metadata
                SET update_source = 'vault_cboe_indices',
                    release_cadence = 'EOD',
                    updated_at = NOW()
                WHERE ticker = ANY(%s);
            """, (list(cboe_idx_tickers),))
            logger.info(f"   Updated {cur.rowcount} CBOE Index tickers")

            logger.info("5. Calibrating Derived Stations (BSI, SV5_TURBULENCE, ROTATION_INDEX, CREDIT_RATIO, YIELD_SPREAD)...")
            derived_tickers = ("BSI", "SV5_TURBULENCE", "ROTATION_INDEX", "CREDIT_RATIO", "YIELD_SPREAD")
            cur.execute("""
                UPDATE market.ticker_metadata
                SET update_source = 'vault_derived',
                    release_cadence = 'DERIVED_INTRADAY',
                    updated_at = NOW()
                WHERE ticker = ANY(%s);
            """, (list(derived_tickers),))
            logger.info(f"   Updated {cur.rowcount} Derived Station tickers")

            logger.info("6. Deprecating orphaned synthetic F&G sub-indicators...")
            fg_orphaned = (
                "FG_SP", "FG_VIX", "FG_MOMENTUM", "FG_STRENGTH",
                "FG_BREADTH", "FG_PUTCALL", "FG_JUNKBOND", "FG_SAFEHAVEN", "FGBI"
            )
            cur.execute("""
                UPDATE market.ticker_metadata
                SET update_source = 'none_historical_only',
                    release_cadence = 'EOD',
                    updated_at = NOW()
                WHERE ticker = ANY(%s);
            """, (list(fg_orphaned),))
            logger.info(f"   Updated {cur.rowcount} orphaned FG tickers")

            logger.info("7. Calibrating Breadth indicators (S5*, SV5*, VBI*)...")
            cur.execute("""
                UPDATE market.ticker_metadata
                SET update_source = 'vault_breadth_calc',
                    release_cadence = 'DERIVED_INTRADAY',
                    updated_at = NOW()
                WHERE industry = 'INDICATOR'
                  AND (ticker LIKE 'S5%%' OR ticker LIKE 'SV5%%' OR ticker LIKE 'VBI%%');
            """)
            logger.info(f"   Updated {cur.rowcount} Breadth tickers")

            logger.info("8. Neutralizing any remaining indicators still set to 'vault_ohlcv_bars'...")
            cur.execute("""
                UPDATE market.ticker_metadata
                SET update_source = 'none_historical_only',
                    updated_at = NOW()
                WHERE industry = 'INDICATOR'
                  AND update_source = 'vault_ohlcv_bars';
            """)
            logger.info(f"   Updated {cur.rowcount} remaining indicator tickers")

            conn.commit()
            logger.info("✅ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Migration failed: {e}")
        sys.exit(1)
    finally:
        store._put(conn)


if __name__ == "__main__":
    run_migration()
