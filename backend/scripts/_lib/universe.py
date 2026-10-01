"""
Canonical Universe Definition for EV Trainers, Benchmarks, and Backfills.
========================================================================
Central Single Source of Truth (SSOT) ensuring strict alignment across
channel_snapshots, zigzag_points, trainers, and benchmarks.

In accordance with Architectural Decision R1:
SPY and Sector/Market ETFs belong to the EV training universe.
"""
from typing import List


def get_canonical_universe(conn, min_bars: int = 250) -> List[str]:
    """
    Returns the canonical institutional universe:
    - Non-indicator assets (industry != 'INDICATOR' or NULL)
    - Stocks and ETFs (asset_type IN ('STOCK', 'ETF'))
    - Excludes internal synthetic trackers (NOT LIKE 'UW_%')
    - Valid ticker length (LENGTH <= 5)
    - Minimum daily bars threshold in market.ohlcv_bars
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT tm.ticker
            FROM market.ticker_metadata tm
            JOIN market.ohlcv_bars b ON b.ticker = tm.ticker AND b.timeframe = '1d'
            WHERE (tm.industry IS NULL OR UPPER(tm.industry) != 'INDICATOR')
              AND UPPER(tm.asset_type) IN ('STOCK', 'ETF')
              AND tm.ticker NOT LIKE 'UW_%%'
              AND LENGTH(tm.ticker) <= 5
            GROUP BY tm.ticker
            HAVING COUNT(b.time) >= %s
            ORDER BY tm.ticker
        """, (min_bars,))
        return [r[0] for r in cur.fetchall()]
