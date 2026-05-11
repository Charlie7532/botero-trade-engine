"""
TradingView CSV Importer — Historical Data Seeding
====================================================
Imports all CSV files from DataTradingView/ into market.ohlcv_bars
and market.macro_data (for ADL series).

TradingView exports use unix timestamps (seconds) and OHLC columns.
Indicators without volume get volume=0 (generic rule for INDICATOR/INDEX).

Usage:
    python -m backend.scripts.import_tradingview
"""
import logging
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Base directory for TV exports
TV_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "DataTradingView")

# ── File mapping: (relative_path, vault_ticker, timeframe, has_adl) ──
FILE_MAP = [
    # Breadth
    ("breadth/INDEX_S5TH, 1D.csv",      "S5TH", "1d",  False),
    ("breadth/INDEX_S5TW, 1D.csv",      "S5TW", "1d",  False),
    ("breadth/INDEX_S5FI, 1D.csv",      "S5FI", "1d",  False),
    # Volatility
    ("volatility/TVC_VIX, 1D.csv",      "VIX",  "1d",  False),
    ("volatility/TVC_VIX, 60.csv",      "VIX",  "1h",  False),
    ("volatility/TVC_VIX, 15.csv",      "VIX",  "15m", False),
    ("volatility/CBOE_DLY_VIX, 5.csv",  "VIX",  "5m",  False),
    ("volatility/CBOE_DLY_VVIX, 1D.csv","VVIX", "1d",  False),
    ("volatility/CBOE_DLY_VVIX, 60.csv","VVIX", "1h",  False),
    ("volatility/CBOE_DLY_VVIX, 15.csv","VVIX", "15m", False),
    ("volatility/INDEX_TRIN, 1D.csv",   "TRIN", "1d",  False),
    # Indices
    ("indices/SP_SPX, 1D (1).csv",      "SPX",  "1d",  True),
    ("indices/TVC_NDQ, 1D.csv",         "NDQ",  "1d",  True),
    ("indices/TVC_DXY, 1D.csv",         "DXY",  "1d",  False),
    ("indices/TVC_TNX, 1D.csv",         "TNX",  "1d",  False),
    # Options
    ("options/USI_PCCE, 1D.csv",        "PCCE", "1d",  False),
    ("options/USI_PCCE, 60.csv",        "PCCE", "1h",  False),
    ("options/USI_PCCE, 15.csv",        "PCCE", "15m", False),
    ("options/CBOE_DLY_SKEW, 1D.csv",   "SKEW", "1d",  False),
]


def parse_tv_csv(filepath: str) -> pd.DataFrame:
    """Parse a TradingView CSV export.

    Converts unix timestamps to UTC datetimes and normalizes columns.
    """
    df = pd.read_csv(filepath)

    # Convert unix timestamp to UTC datetime
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)

    # Normalize column names
    rename = {}
    for col in df.columns:
        lc = col.strip().lower()
        if lc == "advance decline line":
            rename[col] = "adl"
        elif lc == "volume":
            rename[col] = "volume"
    if rename:
        df = df.rename(columns=rename)

    return df


def import_ohlcv(conn, df: pd.DataFrame, ticker: str, timeframe: str) -> int:
    """Insert OHLCV bars into market.ohlcv_bars. Returns rows inserted."""
    rows = []
    for _, r in df.iterrows():
        vol = 0
        if "volume" in df.columns:
            v = r.get("volume")
            vol = int(v) if pd.notna(v) and v != "" else 0
        rows.append((
            r["time"],
            ticker,
            timeframe,
            float(r["open"]),
            float(r["high"]),
            float(r["low"]),
            float(r["close"]),
            vol,
        ))

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO market.ohlcv_bars
               (time, ticker, timeframe, open, high, low, close, volume)
               VALUES %s
               ON CONFLICT DO NOTHING""",
            rows,
            template="(%s, %s, %s, %s, %s, %s, %s, %s)",
            page_size=1000,
        )
    conn.commit()

    # Count how many were actually inserted
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM market.ohlcv_bars WHERE ticker = %s AND timeframe = %s",
            (ticker, timeframe),
        )
        total = cur.fetchone()[0]
    return total


def import_adl(conn, df: pd.DataFrame, ticker: str) -> int:
    """Import Advance-Decline Line into market.macro_data."""
    if "adl" not in df.columns:
        return 0

    name = f"{ticker.lower()}_adl"
    rows = []
    for _, r in df.iterrows():
        val = r.get("adl")
        if pd.notna(val):
            rows.append((r["time"], name, float(val)))

    if not rows:
        return 0

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO market.macro_data (time, name, value)
               VALUES %s
               ON CONFLICT DO NOTHING""",
            rows,
            template="(%s, %s, %s)",
            page_size=1000,
        )
    conn.commit()
    return len(rows)


def main():
    dsn = os.environ.get("POSTGRES_URL")
    if not dsn:
        logger.error("POSTGRES_URL not set")
        sys.exit(1)

    conn = psycopg2.connect(dsn)

    total_bars = 0
    total_adl = 0

    print(f"\n{'='*70}")
    print("TRADINGVIEW DATA IMPORT")
    print(f"{'='*70}\n")

    for relpath, ticker, timeframe, has_adl in FILE_MAP:
        filepath = os.path.join(TV_DIR, relpath)
        if not os.path.exists(filepath):
            logger.warning(f"⚠️  File not found: {relpath}")
            continue

        df = parse_tv_csv(filepath)
        csv_rows = len(df)

        # Import OHLCV
        db_total = import_ohlcv(conn, df, ticker, timeframe)
        total_bars += csv_rows
        logger.info(f"✅ {ticker}/{timeframe}: {csv_rows} CSV rows → {db_total} total in vault")

        # Import ADL if present
        if has_adl:
            adl_count = import_adl(conn, df, ticker)
            total_adl += adl_count
            if adl_count:
                logger.info(f"   📊 ADL: {adl_count} rows → macro_data")

    print(f"\n{'='*70}")
    print(f"IMPORT COMPLETE")
    print(f"  Total OHLCV bars processed: {total_bars:,}")
    print(f"  Total ADL rows:             {total_adl:,}")
    print(f"{'='*70}")

    conn.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
