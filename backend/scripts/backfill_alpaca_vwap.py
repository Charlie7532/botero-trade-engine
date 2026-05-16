"""
backfill_alpaca_vwap.py — Enrich historical 1d bars with Alpaca VWAP + trade_count
=====================================================================================
Optimized v2: Uses batch UPDATE via temp table for ~100x faster execution.
"""
import sys
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("AlpacaBackfill")

_root = Path("/root/botero-trade")
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from sqlalchemy import text


# Indices/breadth that Alpaca doesn't cover
SKIP_TICKERS = {
    'VIX', 'VVIX', 'S5FI', 'S5TH', 'S5TW', 'TNX', 'TRIN', 'DXY', 'SKEW',
    'PCCE', 'MOVE', 'BCOM',
}


def backfill():
    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
    if not api_key:
        logger.error("ALPACA_API_KEY not set — cannot backfill")
        return

    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(api_key, secret_key)
    store = TimescaleDataStore()

    # Get tickers needing backfill
    with store.engine.connect() as c:
        r = c.execute(text("""
            SELECT ticker, COUNT(*) as total,
                COUNT(CASE WHEN vwap IS NOT NULL AND vwap > 0 THEN 1 END) as filled,
                MIN(time)::date as first_date, MAX(time)::date as last_date
            FROM market.ohlcv_bars WHERE timeframe = '1d'
            GROUP BY ticker
            HAVING COUNT(CASE WHEN vwap IS NULL OR vwap = 0 THEN 1 END) > 5
            ORDER BY ticker
        """))
        tickers_raw = [(row[0], row[1], row[2], row[3], row[4]) for row in r]

    # Filter out indices
    tickers_to_fill = [
        t for t in tickers_raw
        if t[0] not in SKIP_TICKERS and not t[0].startswith('S5_')
    ]
    skipped = len(tickers_raw) - len(tickers_to_fill)

    logger.info(f"Tickers to backfill: {len(tickers_to_fill)} (skipped {skipped} indices/breadth)")
    logger.info(f"{'='*70}")

    total_updated = 0
    total_errors = 0
    done = 0

    for ticker, total, filled, first_date, last_date in tickers_to_fill:
        done += 1
        try:
            request = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=TimeFrame.Day,
                start=datetime(first_date.year, first_date.month, first_date.day,
                               tzinfo=timezone.utc),
                end=datetime(last_date.year, last_date.month, last_date.day,
                             tzinfo=timezone.utc) + timedelta(days=1),
            )
            alpaca_bars = client.get_stock_bars(request)

            if not alpaca_bars or ticker not in alpaca_bars.data:
                logger.warning(f"  [{done}/{len(tickers_to_fill)}] ⚠️  {ticker}: no Alpaca data")
                total_errors += 1
                continue

            bars_list = alpaca_bars.data[ticker]

            # Collect (date, vwap, trade_count) tuples
            updates = []
            for bar in bars_list:
                vwap = float(bar.vwap) if hasattr(bar, 'vwap') and bar.vwap else None
                tc = int(bar.trade_count) if hasattr(bar, 'trade_count') and bar.trade_count else None
                if vwap and tc:
                    updates.append((bar.timestamp.date().isoformat(), vwap, tc))

            if not updates:
                continue

            # Batch UPDATE using a temp table + UPDATE FROM
            conn = store._conn()
            try:
                with conn.cursor() as cur:
                    # Create temp table
                    cur.execute("""
                        CREATE TEMP TABLE IF NOT EXISTS _vwap_backfill (
                            dt DATE, vwap DOUBLE PRECISION, trade_count INT
                        ) ON COMMIT DROP
                    """)
                    cur.execute("TRUNCATE _vwap_backfill")

                    # Batch insert into temp
                    from psycopg2.extras import execute_values
                    execute_values(
                        cur,
                        "INSERT INTO _vwap_backfill (dt, vwap, trade_count) VALUES %s",
                        updates,
                        page_size=500,
                    )

                    # Single UPDATE joining temp
                    cur.execute("""
                        UPDATE market.ohlcv_bars ob
                        SET vwap = vb.vwap, trade_count = vb.trade_count
                        FROM _vwap_backfill vb
                        WHERE ob.ticker = %s
                          AND ob.timeframe = '1d'
                          AND ob.time::date = vb.dt
                          AND (ob.vwap IS NULL OR ob.vwap = 0)
                    """, (ticker,))
                    updated = cur.rowcount

                conn.commit()
                total_updated += updated

                if done % 20 == 0 or done <= 5:
                    logger.info(
                        f"  [{done}/{len(tickers_to_fill)}] ✅ {ticker:8s}: "
                        f"{len(bars_list)} bars → {updated} rows updated"
                    )

            except Exception as e:
                conn.rollback()
                logger.error(f"  [{done}/{len(tickers_to_fill)}] ❌ {ticker}: DB error — {e}")
                total_errors += 1
            finally:
                store._put(conn)

        except Exception as e:
            logger.error(f"  [{done}/{len(tickers_to_fill)}] ❌ {ticker}: Alpaca error — {e}")
            total_errors += 1

    # ── FINAL REPORT ──
    logger.info(f"\n{'='*70}")
    logger.info(f"BACKFILL COMPLETE")
    logger.info(f"  Tickers processed: {done}")
    logger.info(f"  Total rows updated: {total_updated}")
    logger.info(f"  Errors: {total_errors}")
    logger.info(f"{'='*70}\n")

    # Post-verification
    logger.info("POST-BACKFILL VERIFICATION:")
    with store.engine.connect() as c:
        r = c.execute(text("""
            SELECT ticker,
                COUNT(*) as total,
                COUNT(CASE WHEN vwap IS NOT NULL AND vwap > 0 THEN 1 END) as vwap_filled,
                COUNT(CASE WHEN trade_count IS NOT NULL AND trade_count > 0 THEN 1 END) as tc_filled
            FROM market.ohlcv_bars
            WHERE timeframe = '1d'
              AND ticker IN ('AAPL','NVDA','TSLA','SPY','META','AMZN','JPM','GOOGL','MSFT','AMD',
                             'COST','WMT','LLY','UNH','XOM','MA','V','JNJ','ABBV','HD')
            GROUP BY ticker ORDER BY ticker
        """))
        for row in r:
            t, total, vw, tc = row
            vp = vw / total * 100
            tp = tc / total * 100
            vs = '✅' if vp > 90 else ('⚠️' if vp > 50 else '❌')
            print(f"  {t:8s}: {total} bars, vwap={vp:>5.1f}% {vs}  trade_count={tp:>5.1f}%")

    store.close()


if __name__ == "__main__":
    backfill()
