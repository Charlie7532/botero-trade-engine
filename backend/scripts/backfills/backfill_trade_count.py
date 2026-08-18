"""
Backfill trade_count + vwap — Alpaca → Neon
===============================================
Updates existing OHLCV bars in Neon with trade_count and vwap
from Alpaca SDK (yfinance doesn't provide these fields).

Usage:
    python -m backend.scripts.backfill_trade_count --tickers SPY,QQQ,AAPL
    python -m backend.scripts.backfill_trade_count --all --batch 50

Why:
    The 707K+ bars in Neon were downloaded via yfinance, which only provides
    OHLCV. Alpaca provides trade_count (number of trades per bar) and VWAP.
    trade_count enables Market Making estimation: avg_trade_size = volume/trade_count.
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, UTC
from pathlib import Path
from time import sleep

import psycopg2
import psycopg2.extras

_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def get_tickers_needing_backfill(conn, limit: int = 0) -> list[str]:
    """Find tickers with NULL trade_count in Neon."""
    with conn.cursor() as cur:
        query = """
            SELECT DISTINCT ticker
            FROM market.ohlcv_bars
            WHERE timeframe = '1d'
              AND trade_count IS NULL
            ORDER BY ticker
        """
        if limit > 0:
            query += f" LIMIT {limit}"
        cur.execute(query)
        return [row[0] for row in cur.fetchall()]


def get_date_range(conn, ticker: str) -> tuple:
    """Get the min/max dates for a ticker's bars."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT MIN(time)::date, MAX(time)::date
               FROM market.ohlcv_bars
               WHERE ticker = %s AND timeframe = '1d'""",
            (ticker,),
        )
        row = cur.fetchone()
        return row[0], row[1]


def fetch_alpaca_bars(ticker: str, start, end) -> list[dict]:
    """Fetch bars from Alpaca SDK with trade_count + vwap."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
    if not api_key:
        raise ValueError("ALPACA_API_KEY not set")

    client = StockHistoricalDataClient(api_key, secret_key)

    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame.Day,
        start=datetime.combine(start, datetime.min.time()).replace(tzinfo=UTC),
        end=datetime.combine(end, datetime.max.time()).replace(tzinfo=UTC),
        limit=10000,
    )

    bars = client.get_stock_bars(request)
    if not bars or ticker not in bars.data:
        return []

    results = []
    for bar in bars.data[ticker]:
        results.append({
            "time": bar.timestamp.date(),
            "vwap": float(bar.vwap) if hasattr(bar, 'vwap') and bar.vwap else None,
            "trade_count": int(bar.trade_count) if hasattr(bar, 'trade_count') and bar.trade_count else None,
        })
    return results


def update_bars(conn, ticker: str, bars: list[dict]) -> int:
    """Update existing rows with trade_count + vwap."""
    if not bars:
        return 0

    updated = 0
    with conn.cursor() as cur:
        for bar in bars:
            if bar["trade_count"] is None and bar["vwap"] is None:
                continue
            cur.execute(
                """UPDATE market.ohlcv_bars
                   SET trade_count = %s, vwap = %s
                   WHERE ticker = %s AND timeframe = '1d'
                   AND time::date = %s""",
                (bar["trade_count"], bar["vwap"], ticker, bar["time"]),
            )
            updated += cur.rowcount
    conn.commit()
    return updated


def backfill_ticker(conn, ticker: str) -> int:
    """Full backfill for one ticker."""
    start, end = get_date_range(conn, ticker)
    if not start or not end:
        logger.warning(f"  {ticker}: no date range found")
        return 0

    logger.info(f"  {ticker}: fetching Alpaca bars {start} → {end}")

    # Alpaca free tier: max ~10K bars per request, chunk by year
    total_updated = 0
    current_start = start

    while current_start <= end:
        chunk_end = min(current_start + timedelta(days=365), end)
        try:
            bars = fetch_alpaca_bars(ticker, current_start, chunk_end)
            if bars:
                n = update_bars(conn, ticker, bars)
                total_updated += n
                logger.info(f"  {ticker}: {current_start}→{chunk_end} — {n} rows updated")
            else:
                logger.warning(f"  {ticker}: no Alpaca data for {current_start}→{chunk_end}")
        except Exception as e:
            logger.error(f"  {ticker}: Alpaca fetch failed: {e}")

        current_start = chunk_end + timedelta(days=1)
        sleep(0.3)  # Rate limit courtesy

    return total_updated


def main():
    parser = argparse.ArgumentParser(description="Backfill trade_count + vwap from Alpaca")
    parser.add_argument("--tickers", help="Comma-separated tickers (e.g., SPY,QQQ,AAPL)")
    parser.add_argument("--all", action="store_true", help="Backfill ALL tickers with NULL trade_count")
    parser.add_argument("--batch", type=int, default=20, help="Max tickers per run (with --all)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be backfilled")
    args = parser.parse_args()

    conn = psycopg2.connect(os.environ["POSTGRES_URL"])

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
    elif args.all:
        tickers = get_tickers_needing_backfill(conn, limit=args.batch)
    else:
        parser.error("Specify --tickers or --all")
        return

    logger.info(f"Backfill targets: {len(tickers)} tickers")

    if args.dry_run:
        for t in tickers:
            start, end = get_date_range(conn, t)
            logger.info(f"  {t}: {start} → {end}")
        conn.close()
        return

    grand_total = 0
    for i, ticker in enumerate(tickers):
        logger.info(f"[{i+1}/{len(tickers)}] Backfilling {ticker}...")
        n = backfill_ticker(conn, ticker)
        grand_total += n
        logger.info(f"  {ticker}: ✅ {n} rows updated")

    logger.info(f"✅ Backfill complete: {grand_total} total rows updated across {len(tickers)} tickers")
    conn.close()


if __name__ == "__main__":
    main()
