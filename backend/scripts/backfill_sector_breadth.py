"""
Backfill Sector Breadth — Historical Seed Data
=================================================
Calculates and inserts ~5 years of historical sector breadth indicators
using existing SP500 constituent OHLCV data already in the vault.

Usage:
    python -m backend.scripts.backfill_sector_breadth

This gives us immediate seed data for backtesting the new sector breadth
indicators (S5_XLK_TH, S5_XLK_FI, S5_XLK_TW, etc.) without needing
external historical data sources.
"""
import logging
import os
import sys
from datetime import date, timedelta

import numpy as np
import psycopg2

from backend.modules.shared.domain.constants.sectors import (
    SECTOR_ETFS,
    SECTOR_BREADTH_TICKERS,
    BREADTH_MA_LENGTHS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Reverse map: sector_name -> etf
_SECTOR_TO_ETF = {v: k for k, v in SECTOR_ETFS.items()}

# Finviz → canonical
_FINVIZ_TO_CANONICAL = {
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Financial Services": "Financials",
    "Basic Materials": "Materials",
}


def _canonicalize(s: str) -> str:
    return _FINVIZ_TO_CANONICAL.get(s, s)


def main():
    pg_url = os.getenv("POSTGRES_URL")
    if not pg_url:
        logger.error("POSTGRES_URL not set")
        sys.exit(1)

    conn = psycopg2.connect(pg_url)
    cur = conn.cursor()

    # 1. Load ALL historical SP500 closes with sector info
    logger.info("Loading historical SP500 closes with sector info...")
    cur.execute("""
        SELECT b.ticker, m.sector, b.time::date, b.close
        FROM market.ohlcv_bars b
        JOIN market.ticker_metadata m ON b.ticker = m.ticker
        WHERE b.timeframe = '1d'
          AND m.asset_type = 'STOCK'
          AND 'SP500' = ANY(m.index_membership)
          AND m.sector IS NOT NULL
        ORDER BY b.ticker, b.time
    """)

    # Build: {ticker: [(date, close), ...]} and {ticker: sector}
    ticker_history: dict[str, list[tuple[date, float]]] = {}
    ticker_sector: dict[str, str] = {}
    row_count = 0
    for ticker, sector, dt, close in cur.fetchall():
        if close is not None:
            ticker_history.setdefault(ticker, []).append((dt, float(close)))
            ticker_sector[ticker] = _canonicalize(sector)
            row_count += 1

    logger.info(f"Loaded {row_count:,} rows for {len(ticker_history)} SP500 tickers")

    # 2. Build a union of all trading dates
    all_dates_set: set[date] = set()
    for hist in ticker_history.values():
        for dt, _ in hist:
            all_dates_set.add(dt)
    all_dates = sorted(all_dates_set)
    logger.info(f"Date range: {all_dates[0]} to {all_dates[-1]} ({len(all_dates)} trading days)")

    # 3. For each date, compute sector breadth
    # Build {ticker: {date: close}} for fast lookup
    ticker_date_close: dict[str, dict[date, float]] = {}
    for ticker, hist in ticker_history.items():
        ticker_date_close[ticker] = {dt: c for dt, c in hist}

    # Pre-index: date → index in all_dates
    date_to_idx = {d: i for i, d in enumerate(all_dates)}

    # For each ticker, build a numpy array of closes aligned to all_dates
    logger.info("Building aligned close arrays...")
    ticker_arrays: dict[str, np.ndarray] = {}
    for ticker in ticker_history:
        arr = np.full(len(all_dates), np.nan)
        for dt, close in ticker_date_close[ticker].items():
            idx = date_to_idx.get(dt)
            if idx is not None:
                arr[idx] = close
        ticker_arrays[ticker] = arr

    # Group tickers by canonical sector
    sector_tickers: dict[str, list[str]] = {}
    for ticker, sector in ticker_sector.items():
        sector_tickers.setdefault(sector, []).append(ticker)

    # 4. Calculate breadth for every date × sector × timeframe
    total_written = 0
    insert_batch = []

    for sector, tickers in sector_tickers.items():
        etf = _SECTOR_TO_ETF.get(sector)
        if not etf or etf not in SECTOR_BREADTH_TICKERS:
            continue

        breadth_tickers = SECTOR_BREADTH_TICKERS[etf]

        for tf_key, indicator_ticker in breadth_tickers.items():
            ma_length = BREADTH_MA_LENGTHS[tf_key]

            # Need at least ma_length days to start calculating
            start_idx = ma_length

            for day_idx in range(start_idx, len(all_dates)):
                day = all_dates[day_idx]
                above = 0
                total = 0

                for ticker in tickers:
                    arr = ticker_arrays[ticker]
                    # Get the MA window
                    window = arr[day_idx - ma_length + 1: day_idx + 1]
                    valid = window[~np.isnan(window)]
                    if len(valid) < ma_length:
                        continue

                    ma_val = float(np.mean(valid))
                    current = arr[day_idx]
                    if np.isnan(current) or ma_val <= 0:
                        continue

                    total += 1
                    if current > ma_val:
                        above += 1

                if total < 10:
                    continue

                breadth_pct = round(above / total * 100, 1)

                insert_batch.append((
                    day, indicator_ticker, "1d",
                    breadth_pct, breadth_pct, breadth_pct, breadth_pct,
                    total,
                ))

                if len(insert_batch) >= 1000:
                    _flush_batch(cur, conn, insert_batch)
                    total_written += len(insert_batch)
                    insert_batch.clear()

        logger.info(f"  {sector} ({etf}): {len(tickers)} constituents processed")

    # Flush remaining
    if insert_batch:
        _flush_batch(cur, conn, insert_batch)
        total_written += len(insert_batch)

    # 5. Register indicator tickers in metadata
    from backend.modules.shared.domain.constants.sectors import ALL_SECTOR_BREADTH_TICKERS
    for ticker in ALL_SECTOR_BREADTH_TICKERS:
        cur.execute("""
            INSERT INTO market.ticker_metadata (ticker, asset_type, sector, update_source)
            VALUES (%s, 'Indicator', 'Indicator', 'breadth_calculation')
            ON CONFLICT (ticker) DO NOTHING
        """, (ticker,))
    conn.commit()

    logger.info(f"✅ Backfilled {total_written:,} sector breadth rows")
    logger.info(f"   Registered {len(ALL_SECTOR_BREADTH_TICKERS)} indicator tickers")

    cur.close()
    conn.close()


def _flush_batch(cur, conn, batch: list) -> None:
    """Batch upsert breadth bars."""
    from psycopg2.extras import execute_values
    execute_values(
        cur,
        """INSERT INTO market.ohlcv_bars
           (time, ticker, timeframe, open, high, low, close, volume)
           VALUES %s
           ON CONFLICT (ticker, timeframe, time) DO UPDATE SET
             close = EXCLUDED.close,
             volume = EXCLUDED.volume""",
        batch,
    )
    conn.commit()


if __name__ == "__main__":
    main()
