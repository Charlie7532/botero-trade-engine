"""
Backfill Breadth History — Vectorized version
=============================================
Computes S5TH/S5FI/S5TW (global), S5VTH/S5VFI/S5VTW (volume),
and 66 sector breadth indicators from OHLCV history in the vault.

Uses pandas rolling windows for ~100x speedup vs the loop-based version.

Usage:
    python -m backend.scripts.backfill_breadth_history
    python -m backend.scripts.backfill_breadth_history --start 2021-01-01
"""
import argparse
import logging
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
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
VOL_MA_LENGTHS = {"VTH": 200, "VFI": 50, "VTW": 20}
TIMEFRAME = "1d"

# Finviz sector names → canonical GICS names
FINVIZ_TO_CANONICAL = {
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Financial Services": "Financials",
    "Financial": "Financials",
    "Basic Materials": "Materials",
}

# Canonical sector → ETF
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


def _vectorized_breadth(close_df: pd.DataFrame, ma_length: int) -> pd.Series:
    """Vectorized: % of columns (tickers) above their rolling MA, per row (date)."""
    ma = close_df.rolling(window=ma_length, min_periods=ma_length).mean()
    above = (close_df > ma) & ma.notna() & (ma > 0)
    eligible = ma.notna() & (ma > 0)
    n_above = above.sum(axis=1)
    n_total = eligible.sum(axis=1)
    pct = (n_above / n_total * 100).round(1)
    pct[n_total < 10] = np.nan  # Need at least 10 tickers
    return pct, n_total


def main():
    parser = argparse.ArgumentParser(
        description="Backfill breadth history from OHLCV vault data (vectorized)"
    )
    parser.add_argument(
        "--start", type=str, default=None,
        help="Start date (YYYY-MM-DD). Default: after 200 trading days.",
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
            SELECT b.ticker, m.sector, b.time::date, b.close, b.volume
            FROM market.ohlcv_bars b
            JOIN market.ticker_metadata m ON b.ticker = m.ticker
            WHERE b.timeframe = '1d'
              AND m.asset_type = 'STOCK'
              AND 'SP500' = ANY(m.index_membership)
              AND m.sector IS NOT NULL
            ORDER BY b.time
        """)
        raw_rows = cur.fetchall()
    conn.close()

    if not raw_rows:
        logger.error("No SP500 OHLCV data found in vault")
        sys.exit(1)

    # ── Step 2: Build DataFrame ──────────────
    logger.info(f"Building DataFrame from {len(raw_rows):,} rows...")
    df = pd.DataFrame(raw_rows, columns=["ticker", "sector", "date", "close", "volume"])
    df["sector"] = df["sector"].map(_canonicalize)
    df["date"] = pd.to_datetime(df["date"])

    # Build sector map (ticker -> sector)
    sector_map = df.drop_duplicates("ticker").set_index("ticker")["sector"].to_dict()

    # Pivot to wide: dates × tickers
    close_wide = df.pivot_table(index="date", columns="ticker", values="close")
    vol_wide = df.pivot_table(index="date", columns="ticker", values="volume")

    n_dates = len(close_wide)
    n_tickers = len(close_wide.columns)
    logger.info(
        f"Matrix: {n_dates:,} dates × {n_tickers} tickers "
        f"({close_wide.index[0].date()} → {close_wide.index[-1].date()})"
    )

    # ── Step 3: Determine start date ─────────────
    min_history = 200
    if args.start:
        start_date = pd.Timestamp(args.start)
    else:
        start_date = close_wide.index[min_history] if n_dates > min_history else close_wide.index[-1]

    logger.info(f"Backfill from: {start_date.date()}")

    # ── Step 4: Compute global breadth (vectorized) ─────────────
    all_rows: list[tuple] = []

    # Count non-null tickers per date (for constituent count)
    logger.info("Computing global price breadth...")
    for suffix, ma_len in MA_LENGTHS.items():
        pct_series, n_total = _vectorized_breadth(close_wide, ma_len)
        mask = pct_series.index >= start_date
        for dt, pct, n in zip(pct_series.index[mask], pct_series[mask], n_total[mask]):
            if pd.notna(pct) and n >= 100:
                p = float(pct)
                all_rows.append((
                    dt.date(), f"S5{suffix}", TIMEFRAME,
                    p, p, p, p, int(n), None, None,
                ))

    logger.info(f"  → {len(all_rows):,} global price breadth bars")

    logger.info("Computing global volume breadth...")
    vol_count_before = len(all_rows)
    for suffix, ma_len in VOL_MA_LENGTHS.items():
        pct_series, n_total = _vectorized_breadth(vol_wide, ma_len)
        mask = pct_series.index >= start_date
        for dt, pct, n in zip(pct_series.index[mask], pct_series[mask], n_total[mask]):
            if pd.notna(pct) and n >= 100:
                p = float(pct)
                all_rows.append((
                    dt.date(), f"S5{suffix}", TIMEFRAME,
                    p, p, p, p, int(n), None, None,
                ))
    logger.info(f"  → {len(all_rows) - vol_count_before:,} global volume breadth bars")

    # ── Step 5: Compute sector breadth (vectorized per sector) ─────────────
    logger.info("Computing sector breadth...")
    sector_count = 0
    for sector, etf in CANONICAL_TO_ETF.items():
        sector_tickers = [t for t, s in sector_map.items() if s == sector]
        if len(sector_tickers) < 10:
            continue

        sector_close = close_wide[
            [t for t in sector_tickers if t in close_wide.columns]
        ]
        sector_vol = vol_wide[
            [t for t in sector_tickers if t in vol_wide.columns]
        ]

        # Price breadth
        for suffix, ma_len in MA_LENGTHS.items():
            pct_series, n_total = _vectorized_breadth(sector_close, ma_len)
            mask = pct_series.index >= start_date
            for dt, pct, n in zip(pct_series.index[mask], pct_series[mask], n_total[mask]):
                if pd.notna(pct):
                    p = float(pct)
                    all_rows.append((
                        dt.date(), f"S5_{etf}_{suffix}", TIMEFRAME,
                        p, p, p, p, int(n), None, None,
                    ))
                    sector_count += 1

        # Volume breadth
        for suffix, ma_len in VOL_MA_LENGTHS.items():
            pct_series, n_total = _vectorized_breadth(sector_vol, ma_len)
            mask = pct_series.index >= start_date
            for dt, pct, n in zip(pct_series.index[mask], pct_series[mask], n_total[mask]):
                if pd.notna(pct):
                    p = float(pct)
                    all_rows.append((
                        dt.date(), f"S5_{etf}_{suffix}", TIMEFRAME,
                        p, p, p, p, int(n), None, None,
                    ))
                    sector_count += 1

        logger.info(f"  {etf}: {len(sector_tickers)} tickers, {sector_count:,} total sector bars so far")

    logger.info(f"Total computed: {len(all_rows):,} breadth bars")

    if args.dry_run:
        logger.info("DRY RUN — skipping DB write")
        return

    # ── Step 6: Write to vault (chunked) ──────────────
    BATCH_SIZE = 10_000
    total_batches = (len(all_rows) + BATCH_SIZE - 1) // BATCH_SIZE
    logger.info(
        f"Writing {len(all_rows):,} bars in {total_batches} batches "
        f"(ON CONFLICT DO NOTHING)..."
    )

    written_total = 0
    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(all_rows))
        batch = all_rows[start:end]

        batch_conn = psycopg2.connect(dsn)
        try:
            with batch_conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO market.ohlcv_bars
                       (time, ticker, timeframe, open, high, low, close, volume, vwap, trade_count)
                       VALUES %s
                       ON CONFLICT (ticker, timeframe, time) DO NOTHING""",
                    batch,
                    page_size=2000,
                )
            batch_conn.commit()
            written_total += len(batch)
            if (batch_idx + 1) % 10 == 0 or batch_idx == total_batches - 1:
                logger.info(
                    f"  Batch {batch_idx + 1}/{total_batches}: "
                    f"{written_total:,}/{len(all_rows):,} rows written"
                )
        except Exception as e:
            batch_conn.rollback()
            logger.error(f"Batch {batch_idx + 1} failed: {e}")
            raise
        finally:
            batch_conn.close()

    # ── Step 7: Verify ────────────────────────────────
    verify_conn = psycopg2.connect(dsn)
    try:
        with verify_conn.cursor() as cur:
            cur.execute("""
                SELECT ticker, COUNT(*), MIN(time)::date, MAX(time)::date,
                       MIN(close), MAX(close), ROUND(AVG(close)::numeric, 1)
                FROM market.ohlcv_bars
                WHERE ticker IN ('S5TH', 'S5FI', 'S5TW', 'S5VTH', 'S5VFI', 'S5VTW')
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

            # Duplicate check
            cur.execute("""
                SELECT COUNT(*) FROM (
                    SELECT ticker, time FROM market.ohlcv_bars
                    WHERE ticker LIKE 'S5%%' AND timeframe = '1d'
                    GROUP BY ticker, time HAVING COUNT(*) > 1
                ) d
            """)
            dup_count = cur.fetchone()[0]
            if dup_count == 0:
                logger.info("\n✅ Zero duplicates confirmed")
            else:
                logger.warning(f"\n⚠️  {dup_count} duplicates found!")

    finally:
        verify_conn.close()

    logger.info(f"\n🎉 DONE: {written_total:,} breadth bars written to vault")


if __name__ == "__main__":
    main()
