#!/usr/bin/env python3
"""
Backfill engine.zigzag_points — Full S&P 500 Universe
======================================================
Extends the existing 17-ticker zigzag table to all 505 stocks.
Uses the CANONICAL zigzag algorithm (High/Low, not close-only)
matching rebuild_zigzag_canonical.py exactly.

Levels: 0.025 (2.5%), 0.05 (5%), 0.075 (7.5%).
Existing data is preserved — only new (ticker, level) combos are inserted.

Usage (background):
  nohup bash -c 'PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
    backend/scripts/backfill_zigzag_points.py' \
    > /tmp/backfill_zigzag.log 2>&1 &
"""
import os, sys, time, logging
from pathlib import Path
from datetime import timezone

import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
from dotenv import load_dotenv
load_dotenv(root_dir / ".env")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════
MIN_BARS = 250
ZIGZAG_LEVELS = [0.025, 0.05, 0.075]
BATCH_SIZE = 500


# ═══════════════════════════════════════════════════════════════
# CANONICAL ZIGZAG — exact copy from rebuild_zigzag_canonical.py
# Uses High for peaks, Low for valleys, close for confirmation.
# DO NOT MODIFY without updating rebuild_zigzag_canonical.py too.
# ═══════════════════════════════════════════════════════════════
def zigzag_canonical(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                     min_pct: float = 0.05):
    """Canonical zigzag — High for peaks, Low for valleys, no backtrack.

    Confirmation: close crossing the threshold from the candidate extreme.
    - MAX confirmed when close drops below candidate_high * (1 - min_pct)
    - MIN confirmed when close rises above candidate_low * (1 + min_pct)

    After confirmation, the next candidate starts at the current bar.
    Returns list of (index, 'MIN'|'MAX', price) tuples.
    """
    n = len(close)
    if n < 2:
        return []

    pts = []

    # Determine initial direction from first 20 bars
    init_high_idx, init_high_val = 0, high[0]
    init_low_idx, init_low_val = 0, low[0]
    for i in range(1, min(20, n)):
        if high[i] > init_high_val:
            init_high_idx, init_high_val = i, high[i]
        if low[i] < init_low_val:
            init_low_idx, init_low_val = i, low[i]

    if init_high_idx < init_low_idx:
        direction = 1  # Price went up first → start looking for MAX
    else:
        direction = -1

    cand_high_idx, cand_high_val = 0, high[0]
    cand_low_idx, cand_low_val = 0, low[0]

    for i in range(1, n):
        if direction == 1:  # Trending up — looking for MAX
            if high[i] > cand_high_val:
                cand_high_idx, cand_high_val = i, high[i]

            if close[i] < cand_high_val * (1 - min_pct):
                pts.append((cand_high_idx, 'MAX', cand_high_val))
                direction = -1
                cand_low_idx, cand_low_val = i, low[i]

        elif direction == -1:  # Trending down — looking for MIN
            if low[i] < cand_low_val:
                cand_low_idx, cand_low_val = i, low[i]

            if close[i] > cand_low_val * (1 + min_pct):
                pts.append((cand_low_idx, 'MIN', cand_low_val))
                direction = 1
                cand_high_idx, cand_high_val = i, high[i]

    return pts


# ═══════════════════════════════════════════════════════════════
# Universe & DB helpers
# ═══════════════════════════════════════════════════════════════
def get_stock_universe(store: TimescaleDataStore) -> list[str]:
    """Get S&P 500 stock universe from Vault."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT tm.ticker
                FROM market.ticker_metadata tm
                JOIN market.ohlcv_bars b ON b.ticker = tm.ticker AND b.timeframe = '1d'
                WHERE tm.asset_type = 'STOCK'
                  AND tm.sector NOT IN ('Breadth','Options Flow','Sentiment','Commodities',
                                        'Fixed Income','Currency','Yields','International',
                                        'Broad Market','Volatility')
                  AND tm.ticker NOT LIKE 'UW_%%'
                  AND tm.industry NOT IN ('ETF','INDICATOR','Breadth Index','Equity Index')
                  AND LENGTH(tm.ticker) <= 5
                GROUP BY tm.ticker
                HAVING COUNT(b.time) >= %s
                ORDER BY tm.ticker
            """, (MIN_BARS,))
            return [r[0] for r in cur.fetchall()]
    finally:
        store._put(conn)


def get_existing_combos(store: TimescaleDataStore) -> set[tuple[str, float]]:
    """Get (ticker, min_swing_pct) combos already in the table."""
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT ticker, min_swing_pct FROM engine.zigzag_points")
            return {(r[0], float(r[1])) for r in cur.fetchall()}
    finally:
        store._put(conn)


def process_ticker(store: TimescaleDataStore, ticker: str, level: float):
    """Compute canonical zigzag pivots for one ticker at one level.

    Returns list of row tuples ready for INSERT.
    """
    ohlc = store.load_bars(ticker, "1d")
    if ohlc is None or len(ohlc) < MIN_BARS:
        return []

    close = ohlc["close"].values.astype(float)
    high = ohlc["high"].values.astype(float)
    low = ohlc["low"].values.astype(float)

    pts = zigzag_canonical(high, low, close, level)

    if len(pts) < 2:
        return []

    ts = ohlc.index

    rows = []
    for i, (bar_idx, tp_type, price) in enumerate(pts):
        # Swing metrics from previous pivot
        if i > 0:
            prev_idx, _, prev_price = pts[i - 1]
            swing_return = (price - prev_price) / prev_price
            swing_days = bar_idx - prev_idx
            swing_speed = swing_return / swing_days if swing_days > 0 else 0
        else:
            swing_return = 0
            swing_days = 0
            swing_speed = 0

        try:
            bar_ts = ts[bar_idx]
            if hasattr(bar_ts, 'to_pydatetime'):
                bar_ts = bar_ts.to_pydatetime()
            if bar_ts.tzinfo is None:
                bar_ts = bar_ts.replace(tzinfo=timezone.utc)
        except (IndexError, KeyError):
            continue

        rows.append((
            ticker, bar_ts, tp_type, float(price),
            level, float(swing_return), int(swing_days), float(swing_speed)
        ))

    return rows


def _insert_batch(conn, rows):
    """Bulk insert rows into engine.zigzag_points."""
    if not rows:
        return
    with conn.cursor() as cur:
        from psycopg2.extras import execute_values
        execute_values(
            cur,
            """INSERT INTO engine.zigzag_points
               (ticker, timestamp, tp_type, price, min_swing_pct,
                swing_return, swing_days, swing_speed)
               VALUES %s
               ON CONFLICT DO NOTHING""",
            rows,
            template="(%s, %s, %s, %s, %s, %s, %s, %s)",
        )
    conn.commit()


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
def main():
    t0 = time.time()
    store = TimescaleDataStore()

    # 1. Universe
    tickers = get_stock_universe(store)
    logger.info(f"Stock universe: {len(tickers)} tickers")

    # 2. Existing data
    existing = get_existing_combos(store)
    logger.info(f"Existing (ticker, level) combos: {len(existing)}")

    # 3. Work list — skip what's already in DB
    work = []
    for ticker in tickers:
        for level in ZIGZAG_LEVELS:
            if (ticker, level) not in existing:
                work.append((ticker, level))

    new_tickers = len(set(t for t, _ in work))
    logger.info(f"New combos to process: {len(work)} ({new_tickers} tickers × up to 3 levels)")

    if not work:
        logger.info("Nothing to do — all combos already exist.")
        store.close()
        return

    # 4. Process
    total_rows = 0
    processed = 0
    failed = 0
    batch_rows = []

    conn = store._conn()

    for i, (ticker, level) in enumerate(work):
        try:
            rows = process_ticker(store, ticker, level)
            batch_rows.extend(rows)
            total_rows += len(rows)
            processed += 1

            # Flush batch
            if len(batch_rows) >= BATCH_SIZE:
                _insert_batch(conn, batch_rows)
                batch_rows = []

            if (i + 1) % 75 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                eta = (len(work) - i - 1) / rate
                logger.info(
                    f"  Progress: {i+1}/{len(work)} combos "
                    f"({processed} ok, {failed} failed) "
                    f"| {total_rows:,} pivots "
                    f"| {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining"
                )
        except Exception as e:
            failed += 1
            logger.warning(f"  ⚠️  {ticker}@{level} failed: {e}")

    # Flush remaining
    if batch_rows:
        _insert_batch(conn, batch_rows)

    store._put(conn)

    # 5. Verify
    final = get_existing_combos(store)
    store.close()

    elapsed = time.time() - t0
    logger.info(
        f"✅ Backfill complete: {processed}/{len(work)} combos, "
        f"{total_rows:,} pivots inserted in {elapsed:.0f}s"
    )
    logger.info(f"   Total combos in DB: {len(final)} (was {len(existing)})")


if __name__ == "__main__":
    main()
