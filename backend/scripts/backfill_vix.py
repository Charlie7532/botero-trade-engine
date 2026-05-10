"""
Backfill VIX OHLCV — One-shot script
======================================
Downloads 5Y of ^VIX daily data from yfinance and persists
to market.ohlcv_bars. Safe to re-run (ON CONFLICT DO NOTHING).

Usage:
    python -m backend.scripts.backfill_vix
"""
import logging
import os
import sys

import pandas as pd
import psycopg2
import psycopg2.extras
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

TICKER = "VIX"
YF_TICKER = "^VIX"
TIMEFRAME = "1d"
PERIOD = "max"  # Get all available history


def main():
    dsn = os.environ.get("POSTGRES_URL")
    if not dsn:
        logger.error("POSTGRES_URL not set")
        sys.exit(1)

    # Download from yfinance
    logger.info(f"Downloading {YF_TICKER} history (period={PERIOD})...")
    t = yf.Ticker(YF_TICKER)
    hist = t.history(period=PERIOD)

    if hist.empty:
        logger.error("No data returned from yfinance")
        sys.exit(1)

    # Handle MultiIndex columns (yfinance sometimes returns these)
    if isinstance(hist.columns, pd.MultiIndex):
        hist.columns = hist.columns.get_level_values(0)

    logger.info(f"Downloaded {len(hist)} bars: {hist.index[0].date()} → {hist.index[-1].date()}")

    # Prepare rows for INSERT
    rows = []
    for ts, row in hist.iterrows():
        rows.append((
            ts.to_pydatetime(),
            TICKER,
            TIMEFRAME,
            float(row["Open"]),
            float(row["High"]),
            float(row["Low"]),
            float(row["Close"]),
            int(row.get("Volume", 0)),
            None,   # vwap
            None,   # trade_count
        ))

    # Insert into PostgreSQL
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO market.ohlcv_bars
                   (time, ticker, timeframe, open, high, low, close, volume, vwap, trade_count)
                   VALUES %s
                   ON CONFLICT (ticker, timeframe, time) DO NOTHING""",
                rows,
                page_size=1000,
            )
        conn.commit()

        # Verify
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), MIN(time)::date, MAX(time)::date "
                "FROM market.ohlcv_bars WHERE ticker = %s AND timeframe = %s",
                (TICKER, TIMEFRAME),
            )
            count, min_dt, max_dt = cur.fetchone()

        logger.info(f"✅ VIX backfill complete: {count} bars ({min_dt} → {max_dt})")
    except Exception as e:
        conn.rollback()
        logger.error(f"Insert failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
