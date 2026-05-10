"""
Backfill Sector Mapping — One-shot script
===========================================
Looks up sector + industry for every ticker in market.ohlcv_bars
via yfinance and persists to market.ticker_metadata.

Usage:
    python -m backend.scripts.backfill_sectors
"""
import logging
import os
import sys
import time

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


def _classify_market_cap(cap: int | None) -> str:
    """Classify market cap into buckets."""
    if cap is None:
        return "unknown"
    if cap >= 200_000_000_000:
        return "mega"
    if cap >= 10_000_000_000:
        return "large"
    if cap >= 2_000_000_000:
        return "mid"
    return "small"


def main():
    dsn = os.environ.get("POSTGRES_URL")
    if not dsn:
        logger.error("POSTGRES_URL not set")
        sys.exit(1)

    conn = psycopg2.connect(dsn)

    # Ensure table exists
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS market.ticker_metadata (
                ticker TEXT PRIMARY KEY,
                sector TEXT,
                industry TEXT,
                market_cap_bucket TEXT,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
    conn.commit()
    logger.info("✅ market.ticker_metadata table ensured")

    # Get all tickers from OHLCV
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT ticker FROM market.ohlcv_bars WHERE timeframe = '1d' ORDER BY ticker")
        all_tickers = [r[0] for r in cur.fetchall()]

    # Check which already have metadata
    with conn.cursor() as cur:
        cur.execute("SELECT ticker FROM market.ticker_metadata WHERE sector IS NOT NULL")
        already_done = {r[0] for r in cur.fetchall()}

    remaining = [t for t in all_tickers if t not in already_done]
    logger.info(f"Total tickers: {len(all_tickers)}, already mapped: {len(already_done)}, remaining: {len(remaining)}")

    if not remaining:
        logger.info("All tickers already mapped — nothing to do")
        conn.close()
        return

    # Lookup via yfinance (batch-friendly)
    import yfinance as yf

    success = 0
    failed = 0
    batch_size = 20

    for i in range(0, len(remaining), batch_size):
        batch = remaining[i:i + batch_size]
        logger.info(f"Processing batch {i // batch_size + 1}/{(len(remaining) + batch_size - 1) // batch_size} ({len(batch)} tickers)...")

        rows = []
        for ticker in batch:
            try:
                t = yf.Ticker(ticker)
                info = t.info
                sector = info.get("sector")
                industry = info.get("industry")
                market_cap = info.get("marketCap")

                if sector:
                    bucket = _classify_market_cap(market_cap)
                    rows.append((ticker, sector, industry, bucket))
                    success += 1
                else:
                    # Store with unknown sector so we don't retry
                    rows.append((ticker, "Unknown", info.get("industry", "Unknown"), "unknown"))
                    failed += 1
            except Exception as e:
                logger.debug(f"  {ticker}: failed ({e})")
                rows.append((ticker, "Unknown", "Unknown", "unknown"))
                failed += 1

        # Batch insert
        if rows:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO market.ticker_metadata (ticker, sector, industry, market_cap_bucket)
                       VALUES %s
                       ON CONFLICT (ticker) DO UPDATE SET
                         sector = EXCLUDED.sector,
                         industry = EXCLUDED.industry,
                         market_cap_bucket = EXCLUDED.market_cap_bucket,
                         updated_at = NOW()
                       WHERE EXCLUDED.sector != 'Unknown'""",
                    rows,
                )
            conn.commit()

        # Rate limiting — yfinance is sensitive
        time.sleep(1)

    # Summary
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM market.ticker_metadata WHERE sector IS NOT NULL AND sector != 'Unknown'")
        mapped = cur.fetchone()[0]
        cur.execute("SELECT sector, COUNT(*) FROM market.ticker_metadata WHERE sector != 'Unknown' GROUP BY sector ORDER BY COUNT(*) DESC")
        sectors = cur.fetchall()

    logger.info(f"\n✅ Sector backfill complete:")
    logger.info(f"   Mapped: {mapped} tickers with known sector")
    logger.info(f"   Success: {success}, Unknown: {failed}")
    logger.info(f"\n   Sector distribution:")
    for sector, count in sectors:
        logger.info(f"     {sector}: {count}")

    conn.close()


if __name__ == "__main__":
    main()
