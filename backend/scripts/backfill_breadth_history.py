"""
Backfill Breadth History — One-shot script
=============================================
Computes S5TH/S5FI/S5TW (global) and 33 sector breadth indicators
from the existing 5-year OHLCV history in the vault.

Persists with ON CONFLICT DO NOTHING so TradingView ground-truth
bars are never overwritten.

Usage:
    python -m backend.scripts.backfill_breadth_history
    python -m backend.scripts.backfill_breadth_history --start 2021-01-01
"""
import argparse
import logging
import os
import sys
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import psycopg2
import psycopg2.extras

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────
MA_LENGTHS = {"TH": 200, "FI": 50, "TW": 20}
TIMEFRAME = "1d"

# Finviz sector names → canonical GICS names (matches sector_breadth_provider)
FINVIZ_TO_CANONICAL = {
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Financial Services": "Financials",
    "Financial": "Financials",
    "Basic Materials": "Materials",
}

# Canonical sector → ETF (for breadth ticker naming)
CANONICAL_TO_ETF = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Materials": "XLB",
    "Communication Services": "XLC",
}


def _canonicalize(sector: str) -> str:
    return FINVIZ_TO_CANONICAL.get(sector, sector)


def _calc_breadth(closes_dict: dict[str, list[float]], ma_length: int) -> float | None:
    """Pure calculation — % of tickers above their MA. Same logic as production."""
    above = 0
    total = 0
    for closes in closes_dict.values():
        if len(closes) < ma_length:
            continue
        ma = float(np.mean(closes[-ma_length:]))
        current = closes[-1]
        if ma > 0:
            total += 1
            if current > ma:
                above += 1
    if total == 0:
        return None
    return round(above / total * 100, 1)


def main():
    parser = argparse.ArgumentParser(
        description="Backfill breadth history from OHLCV vault data"
    )
    parser.add_argument(
        "--start", type=str, default=None,
        help="Start date (YYYY-MM-DD). Default: 250 trading days before earliest full window.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Calculate but don't write to DB.",
    )
    args = parser.parse_args()

    dsn = os.environ.get("POSTGRES_URL")
    if not dsn:
        logger.error("POSTGRES_URL not set")
        sys.exit(1)

    conn = psycopg2.connect(dsn)

    # ── Step 1: Load ALL SP500 OHLCV history ──────────────
    logger.info("Loading SP500 OHLCV history from vault...")
    with conn.cursor() as cur:
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
        raw_rows = cur.fetchall()

    if not raw_rows:
        logger.error("No SP500 OHLCV data found in vault")
        conn.close()
        sys.exit(1)

    # ── Step 2: Build per-ticker time series ──────────────
    # {ticker: [(date, close), ...]}  and {ticker: sector}
    ticker_series: dict[str, list[tuple[date, float]]] = defaultdict(list)
    sector_map: dict[str, str] = {}

    for ticker, sector, dt, close in raw_rows:
        if close is not None:
            ticker_series[ticker].append((dt, float(close)))
            sector_map[ticker] = _canonicalize(sector)

    # Get sorted unique trading dates across all tickers
    all_dates: set[date] = set()
    for series in ticker_series.values():
        for dt, _ in series:
            all_dates.add(dt)
    trading_dates = sorted(all_dates)

    n_tickers = len(ticker_series)
    logger.info(
        f"Loaded {len(raw_rows):,} rows: {n_tickers} tickers, "
        f"{len(trading_dates)} trading dates "
        f"({trading_dates[0]} → {trading_dates[-1]})"
    )

    # ── Step 3: Determine backfill date range ─────────────
    # Need at least 200 days of history for S5TH to be meaningful
    min_history = 200
    if args.start:
        start_date = date.fromisoformat(args.start)
    else:
        # Start from the first date where we have 200+ days of history
        start_date = trading_dates[min_history] if len(trading_dates) > min_history else trading_dates[-1]

    target_dates = [d for d in trading_dates if d >= start_date]
    logger.info(
        f"Backfill range: {target_dates[0]} → {target_dates[-1]} "
        f"({len(target_dates)} dates)"
    )

    # ── Step 4: Build date-indexed close lookup ───────────
    # For each ticker, build {date: close} for O(1) lookup
    ticker_date_close: dict[str, dict[date, float]] = {}
    for ticker, series in ticker_series.items():
        ticker_date_close[ticker] = {dt: close for dt, close in series}

    # ── Step 5: Compute breadth for each date ─────────────
    global_rows: list[tuple] = []
    sector_rows: list[tuple] = []

    for i, target_date in enumerate(target_dates):
        # Build rolling close windows: for each ticker, collect closes up to target_date
        # We need up to 200 days of history before target_date
        window_start_idx = max(0, trading_dates.index(target_date) - min_history - 50)
        window_dates = [d for d in trading_dates[window_start_idx:] if d <= target_date]

        # Build {ticker: [close_day1, ..., close_target_date]}
        all_closes: dict[str, list[float]] = {}
        for ticker, date_close in ticker_date_close.items():
            closes = [date_close[d] for d in window_dates if d in date_close]
            if closes:
                all_closes[ticker] = closes

        n_constituents = len(all_closes)
        if n_constituents < 100:
            continue

        # Global breadth (S5TH, S5FI, S5TW)
        for suffix, ma_len in MA_LENGTHS.items():
            pct = _calc_breadth(all_closes, ma_len)
            if pct is not None:
                global_rows.append((
                    target_date, f"S5{suffix}", TIMEFRAME,
                    pct, pct, pct, pct, n_constituents,
                    None, None,
                ))

        # Sector breadth (S5_XLK_TH, S5_XLK_FI, etc.)
        by_sector: dict[str, dict[str, list[float]]] = defaultdict(dict)
        for ticker, closes in all_closes.items():
            sector = sector_map.get(ticker)
            if sector:
                by_sector[sector][ticker] = closes

        for sector, sector_closes in by_sector.items():
            etf = CANONICAL_TO_ETF.get(sector)
            if not etf:
                continue

            n_sector = len(sector_closes)
            if n_sector < 10:
                continue

            for suffix, ma_len in MA_LENGTHS.items():
                pct = _calc_breadth(sector_closes, ma_len)
                if pct is not None:
                    indicator = f"S5_{etf}_{suffix}"
                    sector_rows.append((
                        target_date, indicator, TIMEFRAME,
                        pct, pct, pct, pct, n_sector,
                        None, None,
                    ))

        if (i + 1) % 100 == 0:
            logger.info(
                f"  Progress: {i + 1}/{len(target_dates)} dates "
                f"({len(global_rows)} global + {len(sector_rows)} sector bars)"
            )

    logger.info(
        f"Computed: {len(global_rows)} global bars + "
        f"{len(sector_rows)} sector bars"
    )

    if args.dry_run:
        logger.info("DRY RUN — skipping DB write")
        conn.close()
        return

    # ── Step 6: Write to vault ────────────────────────────
    all_rows = global_rows + sector_rows
    logger.info(f"Writing {len(all_rows)} breadth bars to vault (ON CONFLICT DO NOTHING)...")

    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO market.ohlcv_bars
                   (time, ticker, timeframe, open, high, low, close, volume, vwap, trade_count)
                   VALUES %s
                   ON CONFLICT (ticker, timeframe, time) DO NOTHING""",
                all_rows,
                page_size=2000,
            )
        conn.commit()

        # ── Step 7: Verify ────────────────────────────────
        with conn.cursor() as cur:
            # Global breadth stats
            cur.execute("""
                SELECT ticker, COUNT(*), MIN(time)::date, MAX(time)::date,
                       MIN(close), MAX(close), ROUND(AVG(close)::numeric, 1)
                FROM market.ohlcv_bars
                WHERE ticker IN ('S5TH', 'S5FI', 'S5TW')
                  AND timeframe = '1d'
                GROUP BY ticker
                ORDER BY ticker
            """)
            logger.info("\n✅ Global Breadth:")
            for ticker, count, min_dt, max_dt, min_v, max_v, avg_v in cur.fetchall():
                logger.info(
                    f"   {ticker}: {count} bars, {min_dt} → {max_dt}, "
                    f"range {min_v:.1f}–{max_v:.1f}, avg {avg_v}"
                )

            # Sector breadth stats
            cur.execute("""
                SELECT ticker, COUNT(*), MIN(time)::date, MAX(time)::date
                FROM market.ohlcv_bars
                WHERE ticker LIKE 'S5\\_%' ESCAPE '\\'
                  AND timeframe = '1d'
                GROUP BY ticker
                ORDER BY ticker
            """)
            sector_results = cur.fetchall()
            logger.info(f"\n✅ Sector Breadth: {len(sector_results)} indicator tickers")
            for ticker, count, min_dt, max_dt in sector_results:
                logger.info(f"   {ticker}: {count} bars ({min_dt} → {max_dt})")

    except Exception as e:
        conn.rollback()
        logger.error(f"Insert failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
