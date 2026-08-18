"""
Backfill script for FRED Treasury Yield indicators into Neon Timescale Vault.
Downloads full historical daily series from FRED (Federal Reserve Economic Data):
  - DGS2:  2-Year Treasury Constant Maturity Rate (~1976 -> present)
  - DGS10: 10-Year Treasury Constant Maturity Rate (~1962 -> present)
  - DTB3:  3-Month Treasury Bill Secondary Market Rate (~1954 -> present)

Persists into `market.ohlcv_bars` as pseudo-OHLCV (open=high=low=close=value, volume=0)
and registers metadata in `market.ticker_metadata`.

Usage:
    backend/.venv/bin/python backend/scripts/backfill_fred_yields.py
"""
import os
import sys
from pathlib import Path
from datetime import datetime, UTC
import logging

# Ensure root and backend are in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "backend"))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

import pandas as pd
from psycopg2.extras import execute_batch
from fredapi import Fred

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BackfillFredYields")

SERIES_CONFIG = [
    {
        "series_id": "DGS2",
        "ticker": "DGS2",
        "name": "2-Year Treasury Constant Maturity Rate",
        "sector": "Yields",
    },
    {
        "series_id": "DGS10",
        "ticker": "DGS10",
        "name": "10-Year Treasury Constant Maturity Rate",
        "sector": "Yields",
    },
    {
        "series_id": "DTB3",
        "ticker": "DTB3",
        "name": "3-Month Treasury Bill Secondary Market Rate",
        "sector": "Yields",
    },
    {
        "series_id": "DFII10",
        "ticker": "DFII10",
        "name": "10-Year TIPS Inflation-Indexed Security Real Yield",
        "sector": "Yields",
    },
    {
        "series_id": "DFII5",
        "ticker": "DFII5",
        "name": "5-Year TIPS Inflation-Indexed Security Real Yield",
        "sector": "Yields",
    },
    {
        "series_id": "CPIAUCSL",
        "ticker": "CPI",
        "name": "Consumer Price Index for All Urban Consumers (All Items)",
        "sector": "Inflation",
    },
    {
        "series_id": "CPIAUCSL",
        "ticker": "CPIAUCSL",
        "name": "Consumer Price Index (FRED Official Series Ticker)",
        "sector": "Inflation",
    },
]


def backfill_series(store: TimescaleDataStore, fred: Fred, config: dict) -> int:
    ticker = config["ticker"]
    series_id = config["series_id"]
    sector = config["sector"]
    name = config["name"]

    logger.info(f"═══ Fetching {ticker} ({name}) from FRED (Series: {series_id}) ═══")
    raw_series = fred.get_series(series_id)
    if raw_series is None or raw_series.empty:
        logger.warning(f"  No data returned from FRED for {series_id}")
        return 0

    clean_series = raw_series.dropna()
    # Normalize index to midnight UTC
    clean_series.index = pd.to_datetime(clean_series.index).tz_localize("UTC") if clean_series.index.tz is None else clean_series.index.tz_convert("UTC")
    clean_series.index = clean_series.index.normalize()
    clean_series = clean_series[~clean_series.index.duplicated(keep="last")]

    logger.info(
        f"  FRED Raw: {len(raw_series)} points | Clean: {len(clean_series)} bars | "
        f"Range: {clean_series.index.min().date()} → {clean_series.index.max().date()} | "
        f"Latest: {clean_series.iloc[-1]:.2f}%"
    )

    existing = store.load_bars(ticker, "1d")
    existing_dates = set(existing.index.date) if existing is not None and len(existing) > 0 else set()
    logger.info(f"  Already in Vault: {len(existing_dates)} bars")

    records = []
    for ts, val in clean_series.items():
        v = float(val)
        records.append((ticker, "1d", ts, v, v, v, v, 0))

    if not records:
        logger.info(f"  ✅ {ticker}: 0 records to insert")
        return 0

    conn = store._conn()
    try:
        cur = conn.cursor()
        query = """
            INSERT INTO market.ohlcv_bars (ticker, timeframe, time, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, timeframe, time) DO UPDATE
            SET open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume;
        """
        execute_batch(cur, query, records, page_size=2000)
        conn.commit()
    finally:
        store._put(conn)

    store.upsert_ticker_metadata(
        ticker=ticker,
        sector=sector,
        industry="INDICATOR",
        market_cap_bucket=None,
    )

    logger.info(f"  ✅ {ticker}: Successfully persisted {len(records)} bars and updated metadata (Sector={sector}, Industry=INDICATOR)")
    return len(records)


def main():
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        logger.error("FRED_API_KEY is not set in environment or .env")
        sys.exit(1)

    fred = Fred(api_key=api_key)
    store = TimescaleDataStore()

    total_inserted = 0
    try:
        for cfg in SERIES_CONFIG:
            inserted = backfill_series(store, fred, cfg)
            total_inserted += inserted

        logger.info(f"🎉 Backfill complete! Total bars processed/upserted: {total_inserted}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
