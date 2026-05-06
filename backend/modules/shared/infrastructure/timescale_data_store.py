"""
TimescaleDB Data Store — Time-Series Infrastructure
======================================================
Implements TimeSeriesPort with TimescaleDB hypertables.
Replaces ParquetDataStore.

Tables used (schema: market):
  - market.ohlcv_bars      (hypertable)
  - market.macro_data       (hypertable)
  - market.mcp_snapshots    (hypertable, JSONB)
"""
import json
import logging
import os
from datetime import date
from typing import Any, Optional

import pandas as pd
import psycopg2
import psycopg2.extras
import psycopg2.pool

from backend.modules.shared.domain.ports.time_series_port import TimeSeriesPort

logger = logging.getLogger(__name__)


class TimescaleDataStore(TimeSeriesPort):
    """TimescaleDB adapter for all time-series data."""

    def __init__(self, dsn: str | None = None, min_conn: int = 1, max_conn: int = 5):
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=min_conn,
            maxconn=max_conn,
            dsn=dsn or os.environ.get("POSTGRES_URL", ""),
        )

    # ── Connection helpers ────────────────────────────────

    def _conn(self):
        return self._pool.getconn()

    def _put(self, conn):
        self._pool.putconn(conn)

    def close(self):
        """Release all connections."""
        self._pool.closeall()

    # ── OHLCV Bars ────────────────────────────────────────

    def save_bars(self, ticker: str, tf: str, df: pd.DataFrame) -> None:
        if df.empty:
            return

        conn = self._conn()
        try:
            rows = []
            for ts, row in df.iterrows():
                rows.append((
                    ts, ticker.upper(), tf,
                    float(row["open"]), float(row["high"]),
                    float(row["low"]), float(row["close"]),
                    int(row.get("volume", 0)),
                    float(row["vwap"]) if "vwap" in row and pd.notna(row.get("vwap")) else None,
                    int(row["trade_count"]) if "trade_count" in row and pd.notna(row.get("trade_count")) else None,
                ))

            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO market.ohlcv_bars
                       (time, ticker, timeframe, open, high, low, close, volume, vwap, trade_count)
                       VALUES %s
                       ON CONFLICT (ticker, timeframe, time) DO NOTHING""",
                    rows,
                    page_size=1000,
                )
            conn.commit()
            logger.info(f"TimescaleDB: {ticker}/{tf} — inserted {len(rows)} bars")
        except Exception as e:
            conn.rollback()
            logger.error(f"TimescaleDB: {ticker}/{tf} save_bars failed: {e}")
            raise
        finally:
            self._put(conn)

    def load_bars(
        self, ticker: str, tf: str,
        start: Optional[date] = None, end: Optional[date] = None,
    ) -> pd.DataFrame:
        conn = self._conn()
        try:
            query = (
                "SELECT time, open, high, low, close, volume, vwap, trade_count "
                "FROM market.ohlcv_bars "
                "WHERE ticker = %s AND timeframe = %s"
            )
            params: list = [ticker.upper(), tf]

            if start:
                query += " AND time >= %s"
                params.append(start)
            if end:
                query += " AND time <= %s"
                params.append(end)

            query += " ORDER BY time"

            df = pd.read_sql(query, conn, params=params, index_col="time", parse_dates=["time"])
            return df
        finally:
            self._put(conn)

    def bars_last_date(self, ticker: str, tf: str) -> Optional[date]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT MAX(time)::date FROM market.ohlcv_bars "
                    "WHERE ticker = %s AND timeframe = %s",
                    (ticker.upper(), tf),
                )
                row = cur.fetchone()
                return row[0] if row and row[0] else None
        finally:
            self._put(conn)

    # ── Macro Data ────────────────────────────────────────

    def save_macro(self, name: str, df: pd.DataFrame) -> None:
        if df.empty:
            return

        conn = self._conn()
        try:
            rows = []
            for ts, row in df.iterrows():
                # Support both single-column and multi-column DataFrames
                if len(row) == 1:
                    rows.append((ts, name, float(row.iloc[0])))
                else:
                    # Multi-column: save each column as a separate series
                    for col in df.columns:
                        if pd.notna(row[col]):
                            rows.append((ts, f"{name}_{col}" if len(df.columns) > 1 else name, float(row[col])))

            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO market.macro_data (time, name, value)
                       VALUES %s
                       ON CONFLICT DO NOTHING""",
                    rows,
                    page_size=1000,
                )
            conn.commit()
            logger.info(f"TimescaleDB: macro/{name} — inserted {len(rows)} points")
        except Exception as e:
            conn.rollback()
            logger.error(f"TimescaleDB: macro/{name} save failed: {e}")
            raise
        finally:
            self._put(conn)

    def load_macro(self, name: str) -> Optional[pd.DataFrame]:
        conn = self._conn()
        try:
            df = pd.read_sql(
                "SELECT time, value FROM market.macro_data "
                "WHERE name = %s ORDER BY time",
                conn,
                params=[name],
                index_col="time",
                parse_dates=["time"],
            )
            return df if not df.empty else None
        finally:
            self._put(conn)

    # ── MCP Snapshots ─────────────────────────────────────

    def save_mcp_snapshot(self, category: str, ticker: str, data: Any, timestamp: str = None) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                if timestamp:
                    cur.execute(
                        """INSERT INTO market.mcp_snapshots (time, category, ticker, data)
                           VALUES (%s, %s, %s, %s)""",
                        (timestamp, category, ticker.upper(), json.dumps(data, default=str)),
                    )
                else:
                    cur.execute(
                        """INSERT INTO market.mcp_snapshots (category, ticker, data)
                           VALUES (%s, %s, %s)""",
                        (category, ticker.upper(), json.dumps(data, default=str)),
                    )
            conn.commit()
            logger.debug(f"TimescaleDB: mcp/{category}/{ticker} — snapshot saved")
        except Exception as e:
            conn.rollback()
            logger.error(f"TimescaleDB: mcp/{category}/{ticker} save failed: {e}")
            raise
        finally:
            self._put(conn)

    def load_mcp_snapshot(self, category: str, ticker: str, dt: str) -> Optional[Any]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT data FROM market.mcp_snapshots
                       WHERE category = %s AND ticker = %s
                       AND time::date = %s::date
                       ORDER BY time DESC LIMIT 1""",
                    (category, ticker.upper(), dt),
                )
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            self._put(conn)

    def load_mcp_range(
        self, category: str, ticker: str,
        start: str, end: str,
    ) -> list[tuple[str, Any]]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT time::date::text, data FROM market.mcp_snapshots
                       WHERE category = %s AND ticker = %s
                       AND time::date >= %s::date AND time::date <= %s::date
                       ORDER BY time""",
                    (category, ticker.upper(), start, end),
                )
                return [(row[0], row[1]) for row in cur.fetchall()]
        finally:
            self._put(conn)
