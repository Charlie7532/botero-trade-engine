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
from sqlalchemy import create_engine as _create_engine

from backend.modules.shared.domain.ports.time_series_port import TimeSeriesPort
from backend.modules.simulation.domain.ports.ml_data_port import MLDataPort

logger = logging.getLogger(__name__)


class TimescaleDataStore(TimeSeriesPort, MLDataPort):
    """TimescaleDB adapter for all time-series data."""

    def __init__(self, dsn: str | None = None, min_conn: int = 1, max_conn: int = 5):
        self._dsn = dsn or os.environ.get("POSTGRES_URL", "")
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=min_conn,
            maxconn=max_conn,
            dsn=self._dsn,
        )
        self._sa_engine = None  # Lazy SQLAlchemy engine for pd.read_sql

    # ── Connection helpers ────────────────────────────────

    def _conn(self):
        return self._pool.getconn()

    def _put(self, conn):
        self._pool.putconn(conn)

    def close(self):
        """Release all connections."""
        self._pool.closeall()
        if self._sa_engine:
            self._sa_engine.dispose()

    @property
    def engine(self):
        """Lazy SQLAlchemy engine for pd.read_sql (avoids deprecation warning)."""
        if self._sa_engine is None:
            self._sa_engine = _create_engine(self._dsn)
        return self._sa_engine

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

            df = pd.read_sql(query, self.engine, params=tuple(params), index_col="time", parse_dates=["time"])
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
        try:
            df = pd.read_sql(
                "SELECT time, value FROM market.macro_data "
                "WHERE name = %s ORDER BY time",
                self.engine,
                params=[name],
                index_col="time",
                parse_dates=["time"],
            )
            return df if not df.empty else None
        except Exception:
            return None

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

    def load_mcp_latest(self, category: str, ticker: str) -> Optional[Any]:
        """Load the most recent MCP snapshot regardless of date."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT data FROM market.mcp_snapshots
                       WHERE category = %s AND ticker = %s
                       ORDER BY time DESC LIMIT 1""",
                    (category, ticker.upper()),
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

    def load_indicator_history(
        self, category: str, ticker: str, field_path: str, days: int = 90,
    ) -> list[tuple[str, float]]:
        """
        Extract a time-series of a specific JSON field from mcp_snapshots.

        Args:
            category: Snapshot category (e.g. "macro/fred")
            ticker: Snapshot ticker (e.g. "SUMMARY")
            field_path: Dot-notation path into JSON data.
                        Examples: "VIX.close", "score", "VVIX.close"
            days: Number of days to look back.

        Returns:
            [(date_str, float_value), ...] chronologically ordered.
            Rows where the field is missing or non-numeric are skipped.
        """
        from datetime import date, timedelta
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=days)).isoformat()

        raw = self.load_mcp_range(category, ticker, start, end)
        result = []
        parts = field_path.split(".")

        for dt, data in raw:
            try:
                val = data
                for part in parts:
                    val = val[part]
                result.append((dt, float(val)))
            except (KeyError, TypeError, ValueError):
                continue

        # Deduplicate by date (keep last per day)
        seen = {}
        for dt, val in result:
            seen[dt] = val
        return sorted(seen.items())

    def load_all_latest_closes(self, days: int = 200, sp500_only: bool = False) -> dict[str, list[float]]:
        """
        Load last N days of close prices for tickers in OHLCV.
        Used for S5TH/S5TW/S5FI breadth calculation.

        Args:
            days: Number of calendar days of history to load.
            sp500_only: If True, only include tickers with index_membership containing 'SP500'
                        and asset_type = 'STOCK'. This ensures breadth is calculated from
                        actual S&P 500 constituents, not ETFs/indices/indicators.

        Returns:
            {ticker: [close_day1, close_day2, ...]} chronologically ordered.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                if sp500_only:
                    cur.execute(
                        """SELECT b.ticker, b.time::date, b.close
                           FROM market.ohlcv_bars b
                           JOIN market.ticker_metadata m ON b.ticker = m.ticker
                           WHERE b.timeframe = '1d'
                           AND b.time >= NOW() - INTERVAL '%s days'
                           AND m.asset_type = 'STOCK'
                           AND 'SP500' = ANY(m.index_membership)
                           ORDER BY b.ticker, b.time""",
                        (days,),
                    )
                else:
                    cur.execute(
                        """SELECT ticker, time::date, close
                           FROM market.ohlcv_bars
                           WHERE timeframe = '1d'
                           AND time >= NOW() - INTERVAL '%s days'
                           ORDER BY ticker, time""",
                        (days,),
                    )
                result: dict[str, list[float]] = {}
                for ticker, dt, close in cur.fetchall():
                    if close is not None:
                        result.setdefault(ticker, []).append(float(close))
                return result
        finally:
            self._put(conn)

    def upsert_ohlcv_bar(
        self, ticker: str, timeframe: str, time,
        open: float, high: float, low: float, close: float, volume: int = 0,
    ) -> None:
        """Insert a single OHLCV bar, skip if already exists."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO market.ohlcv_bars
                       (time, ticker, timeframe, open, high, low, close, volume)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (ticker, timeframe, time) DO NOTHING""",
                    (time, ticker.upper(), timeframe, open, high, low, close, volume),
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"TimescaleDB: upsert_ohlcv_bar {ticker}/{timeframe} failed: {e}")
        finally:
            self._put(conn)

    # ── Ticker Metadata ───────────────────────────────────

    def load_sector_map(self) -> dict[str, str]:
        """Load {ticker: sector} mapping from ticker_metadata.

        Returns empty dict if table doesn't exist yet.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT ticker, sector FROM market.ticker_metadata
                       WHERE sector IS NOT NULL AND sector != 'Unknown'"""
                )
                return {row[0]: row[1] for row in cur.fetchall()}
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            return {}
        finally:
            self._put(conn)

    def upsert_ticker_metadata(
        self, ticker: str, sector: str,
        industry: str | None = None, market_cap_bucket: str | None = None,
    ) -> None:
        """Insert or update sector/industry metadata for a ticker."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO market.ticker_metadata
                         (ticker, sector, industry, market_cap_bucket)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (ticker) DO UPDATE SET
                         sector = EXCLUDED.sector,
                         industry = EXCLUDED.industry,
                         market_cap_bucket = EXCLUDED.market_cap_bucket,
                         updated_at = NOW()""",
                    (ticker.upper(), sector, industry, market_cap_bucket),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    def load_sp500_closes_by_sector(
        self, days: int = 250,
    ) -> tuple[dict[str, dict[str, list[float]]], dict[str, str]]:
        """
        Load SP500 closes grouped by sector for sector breadth calculation.

        Returns:
            Tuple of:
              - {sector: {ticker: [close_day1, ...]}} grouped by sector
              - {ticker: sector} flat sector map
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT b.ticker, m.sector, b.time::date, b.close
                       FROM market.ohlcv_bars b
                       JOIN market.ticker_metadata m ON b.ticker = m.ticker
                       WHERE b.timeframe = '1d'
                         AND b.time >= NOW() - INTERVAL '%s days'
                         AND m.asset_type = 'STOCK'
                         AND 'SP500' = ANY(m.index_membership)
                         AND m.sector IS NOT NULL
                       ORDER BY b.ticker, b.time""",
                    (days,),
                )
                by_sector: dict[str, dict[str, list[float]]] = {}
                sector_map: dict[str, str] = {}
                for ticker, sector, dt, close in cur.fetchall():
                    if close is not None:
                        sector_map[ticker] = sector
                        by_sector.setdefault(sector, {}).setdefault(ticker, []).append(float(close))
                return by_sector, sector_map
        finally:
            self._put(conn)

    # ── ML Data Lake (Forensics) ──────────────────────────

    def save_ml_feature_and_label(
        self,
        feature_record: dict[str, Any],
        label_record: dict[str, Any]
    ) -> None:
        """
        Guarda un par (X, y) en las tablas engine.ml_features y engine.ml_labels.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                # 1. Insert Feature (X)
                cur.execute(
                    """INSERT INTO engine.ml_features
                         (id, ticker, timeframe, signal_name, signal_time, features)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (id) DO UPDATE SET
                         features = EXCLUDED.features""",
                    (
                        str(feature_record["id"]),
                        feature_record["ticker"],
                        feature_record["timeframe"],
                        feature_record["signal_name"],
                        feature_record["signal_time"],
                        json.dumps(feature_record["features"])
                    )
                )

                # 2. Insert Label (y)
                cur.execute(
                    """INSERT INTO engine.ml_labels
                         (feature_id, label, return_pct, bars_held, exit_time, geometry_used)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (feature_id) DO UPDATE SET
                         label = EXCLUDED.label,
                         return_pct = EXCLUDED.return_pct,
                         bars_held = EXCLUDED.bars_held,
                         exit_time = EXCLUDED.exit_time,
                         geometry_used = EXCLUDED.geometry_used""",
                    (
                        str(label_record["feature_id"]),
                        int(label_record["label"]),
                        float(label_record["return_pct"]),
                        int(label_record["bars_held"]),
                        label_record["exit_time"],
                        json.dumps(label_record["geometry_used"])
                    )
                )
            conn.commit()
            logger.debug(f"ML Data Lake: Saved feature/label {feature_record['id']} for {feature_record['ticker']}")
        except Exception as e:
            conn.rollback()
            logger.error(f"ML Data Lake: Save failed: {e}")
            raise
        finally:
            self._put(conn)

    def save_ml_batch(
        self,
        feature_records: list[dict[str, Any]],
        label_records: list[dict[str, Any]]
    ) -> None:
        """
        Batch insert features + labels using execute_values.
        Reduces Neon round-trips from 2×N to 2 (one per table).
        """
        if not feature_records:
            return

        conn = self._conn()
        try:
            feat_rows = [
                (
                    str(r["id"]), r["ticker"], r["timeframe"],
                    r["signal_name"], r["signal_time"],
                    json.dumps(r["features"])
                )
                for r in feature_records
            ]

            label_rows = [
                (
                    str(r["feature_id"]), int(r["label"]),
                    float(r["return_pct"]), int(r["bars_held"]),
                    r["exit_time"], json.dumps(r["geometry_used"])
                )
                for r in label_records
            ]

            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO engine.ml_features
                         (id, ticker, timeframe, signal_name, signal_time, features)
                       VALUES %s
                       ON CONFLICT (id) DO UPDATE SET features = EXCLUDED.features""",
                    feat_rows,
                    page_size=500,
                )
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO engine.ml_labels
                         (feature_id, label, return_pct, bars_held, exit_time, geometry_used)
                       VALUES %s
                       ON CONFLICT (feature_id) DO UPDATE SET
                         label = EXCLUDED.label,
                         return_pct = EXCLUDED.return_pct,
                         bars_held = EXCLUDED.bars_held,
                         exit_time = EXCLUDED.exit_time,
                         geometry_used = EXCLUDED.geometry_used""",
                    label_rows,
                    page_size=500,
                )
            conn.commit()
            logger.info(f"ML Data Lake: Batch saved {len(feat_rows)} feature/label pairs")
        except Exception as e:
            conn.rollback()
            logger.error(f"ML Data Lake: Batch save failed: {e}")
            raise
        finally:
            self._put(conn)

    # ── SIGNAL PROFILES (Alpha Passport) ─────────────────────

    def save_signal_profile(self, profile: dict[str, Any]) -> None:
        """Upsert a signal profile to engine.signal_profiles."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO engine.signal_profiles (
                        ticker, timeframe, signal_name, department,
                        n_entries, win_rate, ceiling_sharpe, profit_factor,
                        avg_return_pct, total_return_pct, max_drawdown_pct,
                        avg_bars_held, avg_bars_to_loss, pct_loss_hit, pct_time_hit,
                        geometry_json, viable, grade, calibrated_at
                    ) VALUES (
                        %(ticker)s, %(timeframe)s, %(signal_name)s, %(department)s,
                        %(n_entries)s, %(win_rate)s, %(ceiling_sharpe)s, %(profit_factor)s,
                        %(avg_return_pct)s, %(total_return_pct)s, %(max_drawdown_pct)s,
                        %(avg_bars_held)s, %(avg_bars_to_loss)s, %(pct_loss_hit)s, %(pct_time_hit)s,
                        %(geometry_json)s, %(viable)s, %(grade)s, NOW()
                    )
                    ON CONFLICT (ticker, timeframe, signal_name) DO UPDATE SET
                        department = EXCLUDED.department,
                        n_entries = EXCLUDED.n_entries,
                        win_rate = EXCLUDED.win_rate,
                        ceiling_sharpe = EXCLUDED.ceiling_sharpe,
                        profit_factor = EXCLUDED.profit_factor,
                        avg_return_pct = EXCLUDED.avg_return_pct,
                        total_return_pct = EXCLUDED.total_return_pct,
                        max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                        avg_bars_held = EXCLUDED.avg_bars_held,
                        avg_bars_to_loss = EXCLUDED.avg_bars_to_loss,
                        pct_loss_hit = EXCLUDED.pct_loss_hit,
                        pct_time_hit = EXCLUDED.pct_time_hit,
                        geometry_json = EXCLUDED.geometry_json,
                        viable = EXCLUDED.viable,
                        grade = EXCLUDED.grade,
                        calibrated_at = NOW()
                """, profile)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Signal profile save failed for {profile.get('ticker')}/{profile.get('signal_name')}: {e}")
            raise
        finally:
            self._put(conn)

    def load_signal_profiles(self, ticker: str, timeframe: str) -> list[dict[str, Any]]:
        """Load all signal profiles for a ticker/timeframe pair."""
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM engine.signal_profiles
                    WHERE ticker = %s AND timeframe = %s
                    ORDER BY ceiling_sharpe DESC
                """, (ticker, timeframe))
                return [dict(row) for row in cur.fetchall()]
        finally:
            self._put(conn)

