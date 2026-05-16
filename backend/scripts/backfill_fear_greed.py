"""
Backfill CNN Fear & Greed Historical — One-shot script
========================================================
Downloads 15 years (2011–2026) of daily CNN Fear & Greed Index data
from the whit3rabbit/fear-greed-data GitHub repository and persists
to market.ohlcv_bars as ticker 'FG'. Safe to re-run (ON CONFLICT DO NOTHING).

Source: https://github.com/whit3rabbit/fear-greed-data
Canonical file: fear-greed.csv (combined, auto-updated weekly)

Usage:
    python -m backend.scripts.backfill_fear_greed
"""
import logging
import os
import sys
from io import StringIO

import pandas as pd
import psycopg2
import psycopg2.extras
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

TICKER = "FG"
TIMEFRAME = "1d"
CSV_URL = "https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/fear-greed.csv"


def main():
    dsn = os.environ.get("POSTGRES_URL")
    if not dsn:
        logger.error("POSTGRES_URL not set")
        sys.exit(1)

    # Download CSV from GitHub
    logger.info(f"Downloading Fear & Greed historical data from GitHub...")
    resp = requests.get(CSV_URL, timeout=30)
    resp.raise_for_status()

    # Parse CSV
    df = pd.read_csv(StringIO(resp.text), parse_dates=["Date"])
    df = df.dropna(subset=["Date", "Fear Greed"])
    df = df.drop_duplicates(subset=["Date"], keep="last")

    # Validate score range
    score_min = df["Fear Greed"].min()
    score_max = df["Fear Greed"].max()
    logger.info(
        f"Parsed {len(df)} rows: {df['Date'].min().date()} → {df['Date'].max().date()} "
        f"(score range: {score_min:.1f} – {score_max:.1f})"
    )

    if score_min < 0 or score_max > 100:
        logger.warning(f"Score range [{score_min}, {score_max}] outside expected 0-100")

    # Prepare rows for INSERT
    # Store as OHLCV bar: open=high=low=close=score, volume=0
    rows = []
    for _, row in df.iterrows():
        score = float(row["Fear Greed"])
        rows.append((
            row["Date"].to_pydatetime(),
            TICKER,
            TIMEFRAME,
            score,   # open
            score,   # high
            score,   # low
            score,   # close
            0,       # volume
            None,    # vwap
            None,    # trade_count
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
                "SELECT COUNT(*), MIN(time)::date, MAX(time)::date, "
                "MIN(close), MAX(close), AVG(close) "
                "FROM market.ohlcv_bars WHERE ticker = %s AND timeframe = %s",
                (TICKER, TIMEFRAME),
            )
            count, min_dt, max_dt, min_score, max_score, avg_score = cur.fetchone()

        logger.info(
            f"✅ Fear & Greed backfill complete:\n"
            f"   Bars: {count}\n"
            f"   Range: {min_dt} → {max_dt}\n"
            f"   Score: {min_score:.1f} – {max_score:.1f} (avg {avg_score:.1f})"
        )
    except Exception as e:
        conn.rollback()
        logger.error(f"Insert failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
