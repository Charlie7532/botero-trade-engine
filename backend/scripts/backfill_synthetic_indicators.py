"""
Backfill script for synthetic METAR indicators.
Computes full historical series from ETF components already in the Vault
and persists as pseudo-OHLCV tickers.

Run ONCE to populate history. After that, the daily daemon keeps them updated.

Usage:
    cd /root/botero-trade
    source backend/.venv/bin/activate
    python backend/scripts/backfill_synthetic_indicators.py
"""
import sys
sys.path.insert(0, "backend")

import pandas as pd
import numpy as np
import logging
from datetime import datetime, UTC

from modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_ROTATION_WINDOW = 252


from psycopg2.extras import execute_batch


def _bulk_insert(store: TimescaleDataStore, ticker: str, df_values: pd.Series, sector: str) -> int:
    """Helper to bulk insert single-value indicator series into market.ohlcv_bars."""
    existing = store.load_bars(ticker, "1d")
    existing_dates = set(existing.index.date) if existing is not None and len(existing) > 0 else set()
    logger.info(f"  Already in Vault: {len(existing_dates)} bars")

    new_rows = [(ts, float(val)) for ts, val in df_values.items() if ts.date() not in existing_dates]
    if not new_rows:
        logger.info(f"  ✅ {ticker}: 0 new bars to insert")
        return 0

    records = [
        (ticker, "1d", ts, val, val, val, val, 0)
        for ts, val in new_rows
    ]

    conn = store._conn()
    try:
        cur = conn.cursor()
        query = """
            INSERT INTO market.ohlcv_bars (ticker, timeframe, time, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, timeframe, time) DO UPDATE
            SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close, volume = EXCLUDED.volume;
        """
        execute_batch(cur, query, records)
        conn.commit()
    finally:
        store._put(conn)

    store.upsert_ticker_metadata(
        ticker=ticker,
        sector=sector,
        industry="INDICATOR",
        market_cap_bucket=None,
    )
    logger.info(f"  ✅ {ticker}: {len(records)} new bars inserted via bulk execution")
    return len(records)


def backfill_credit_ratio(store: TimescaleDataStore) -> int:
    """Backfill CREDIT_RATIO = HYG / LQD (pure corporate default spread)."""
    logger.info("═══ Backfilling CREDIT_RATIO (HYG/LQD) ═══")

    hyg = store.load_bars("HYG", "1d")["close"].rename("hyg")
    lqd = store.load_bars("LQD", "1d")["close"].rename("lqd")

    m = pd.concat([hyg, lqd], axis=1).dropna()
    credit_ratio = m["hyg"] / m["lqd"]

    logger.info(f"  HYG: {len(hyg)} bars | LQD: {len(lqd)} bars | Aligned: {len(m)} bars")
    logger.info(f"  Range: {m.index.min().date()} → {m.index.max().date()}")

    return _bulk_insert(store, "CREDIT_RATIO", credit_ratio, "Credit")


def backfill_yield_spread(store: TimescaleDataStore) -> int:
    """Backfill YIELD_SPREAD = TNX - IRX."""
    logger.info("═══ Backfilling YIELD_SPREAD (TNX-IRX) ═══")

    tnx = store.load_bars("TNX", "1d")["close"].rename("tnx")
    irx = store.load_bars("IRX", "1d")["close"].rename("irx")

    m = pd.concat([tnx, irx], axis=1).dropna()
    yield_spread = m["tnx"] - m["irx"]

    logger.info(f"  TNX: {len(tnx)} bars | IRX: {len(irx)} bars | Aligned: {len(m)} bars")
    logger.info(f"  Range: {m.index.min().date()} → {m.index.max().date()}")

    return _bulk_insert(store, "YIELD_SPREAD", yield_spread, "Yields")


def backfill_rotation_index(store: TimescaleDataStore) -> int:
    """Backfill ROTATION_INDEX = z(XLY/XLP) + z(XLK/XLU)."""
    logger.info("═══ Backfilling ROTATION_INDEX ═══")

    xly = store.load_bars("XLY", "1d")["close"].rename("xly")
    xlp = store.load_bars("XLP", "1d")["close"].rename("xlp")
    xlk = store.load_bars("XLK", "1d")["close"].rename("xlk")
    xlu = store.load_bars("XLU", "1d")["close"].rename("xlu")

    m = pd.concat([xly, xlp, xlk, xlu], axis=1).dropna().sort_index()

    r1 = m["xly"] / m["xlp"]
    r2 = m["xlk"] / m["xlu"]
    z1 = (r1 - r1.rolling(_ROTATION_WINDOW, min_periods=20).mean()) / r1.rolling(_ROTATION_WINDOW, min_periods=20).std()
    z2 = (r2 - r2.rolling(_ROTATION_WINDOW, min_periods=20).mean()) / r2.rolling(_ROTATION_WINDOW, min_periods=20).std()
    rotation = (z1 + z2).fillna(0.0).dropna()

    logger.info(f"  Components: XLY={len(xly)}, XLP={len(xlp)}, XLK={len(xlk)}, XLU={len(xlu)}")
    logger.info(f"  Rotation series: {len(rotation)} bars")
    logger.info(f"  Range: {rotation.index.min().date()} → {rotation.index.max().date()}")

    return _bulk_insert(store, "ROTATION_INDEX", rotation, "Rotation")


def main():
    store = TimescaleDataStore()

    total = 0
    total += backfill_credit_ratio(store)
    total += backfill_yield_spread(store)
    total += backfill_rotation_index(store)

    logger.info(f"\n{'='*60}")
    logger.info(f"✅ Backfill complete: {total} total bars inserted across 3 indicators")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
