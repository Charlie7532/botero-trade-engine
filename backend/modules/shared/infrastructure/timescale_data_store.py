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
from backend.modules.shared.domain.ports.channel_snapshot_port import ChannelSnapshotPort
from backend.modules.simulation.domain.ports.ml_data_port import MLDataPort

logger = logging.getLogger(__name__)


class TimescaleDataStore(TimeSeriesPort, MLDataPort, ChannelSnapshotPort):
    """TimescaleDB adapter for all time-series data."""

    def __init__(self, dsn: str | None = None, min_conn: int = 1, max_conn: int = 5):
        self._dsn = dsn or os.environ.get("POSTGRES_URL", "")
        if not self._dsn:
            # Auto-load .env if POSTGRES_URL is missing from environment.
            # Prevents socket errors when callers forget load_dotenv().
            try:
                from dotenv import load_dotenv
                load_dotenv()
                self._dsn = os.environ.get("POSTGRES_URL", "")
            except ImportError:
                pass
        if not self._dsn:
            raise RuntimeError(
                "POSTGRES_URL not set. Ensure .env is loaded or pass dsn= explicitly."
            )
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

    def load_bars_freshness(
        self, ticker: str, tf: str,
    ) -> tuple[Optional[date], bool]:
        """Check freshness of the latest bar for a ticker.

        Returns:
            (last_bar_date, is_stale) using market_schedule trading-day awareness.
            Returns (None, True) if no bars exist.
        """
        last_dt = self.bars_last_date(ticker, tf)
        if not last_dt:
            return None, True

        from backend.modules.shared.domain.rules.market_schedule import is_data_stale
        stale = is_data_stale(last_dt, asset_type="INDICATOR")
        return last_dt, stale

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

    def load_mcp_latest_with_age(
        self, category: str, ticker: str,
    ) -> tuple[Optional[Any], Optional['timedelta']]:
        """Load the most recent MCP snapshot WITH its age.

        Returns:
            (data, age) where age is timedelta since the snapshot was saved.
            (None, None) if no snapshot exists.
        """
        from datetime import timedelta  # noqa: F811
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT data, NOW() - time AS age
                       FROM market.mcp_snapshots
                       WHERE category = %s AND ticker = %s
                       ORDER BY time DESC LIMIT 1""",
                    (category, ticker.upper()),
                )
                row = cur.fetchone()
                if row:
                    return row[0], row[1]  # data, timedelta
                return None, None
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

    def upsert_ohlcv_bar_candle(
        self, ticker: str, timeframe: str, time,
        score: float, volume: int = 0,
    ) -> None:
        """Insert or UPDATE an OHLCV bar, building a real candle progressively.

        First insert of the day: open=high=low=close=score.
        Subsequent updates: high=MAX(existing, new), low=MIN(existing, new),
        close=latest score. Open is preserved (first reading of the day).
        Volume increments as a read counter (proxy for candle confidence).
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO market.ohlcv_bars
                       (time, ticker, timeframe, open, high, low, close, volume)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (ticker, timeframe, time) DO UPDATE SET
                         high = GREATEST(market.ohlcv_bars.high, EXCLUDED.high),
                         low = LEAST(market.ohlcv_bars.low, EXCLUDED.low),
                         close = EXCLUDED.close,
                         volume = market.ohlcv_bars.volume + 1""",
                    (time, ticker.upper(), timeframe,
                     score, score, score, score, volume),
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(
                f"TimescaleDB: upsert_ohlcv_bar_candle {ticker}/{timeframe} failed: {e}"
            )
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

                # 2. Insert Label (y) — includes forensic fields
                cur.execute(
                    """INSERT INTO engine.ml_labels
                         (feature_id, label, return_pct, bars_held, exit_time, geometry_used,
                          max_adverse_excursion_pct, max_favorable_excursion_pct,
                          post_exit_max_pct, post_exit_hit_target,
                          post_exit_bars_to_target, stop_was_sweep)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (feature_id) DO UPDATE SET
                         label = EXCLUDED.label,
                         return_pct = EXCLUDED.return_pct,
                         bars_held = EXCLUDED.bars_held,
                         exit_time = EXCLUDED.exit_time,
                         geometry_used = EXCLUDED.geometry_used,
                         max_adverse_excursion_pct = EXCLUDED.max_adverse_excursion_pct,
                         max_favorable_excursion_pct = EXCLUDED.max_favorable_excursion_pct,
                         post_exit_max_pct = EXCLUDED.post_exit_max_pct,
                         post_exit_hit_target = EXCLUDED.post_exit_hit_target,
                         post_exit_bars_to_target = EXCLUDED.post_exit_bars_to_target,
                         stop_was_sweep = EXCLUDED.stop_was_sweep""",
                    (
                        str(label_record["feature_id"]),
                        int(label_record["label"]),
                        float(label_record["return_pct"]),
                        int(label_record["bars_held"]),
                        label_record["exit_time"],
                        json.dumps(label_record["geometry_used"]),
                        float(label_record.get("max_adverse_excursion_pct", 0)),
                        float(label_record.get("max_favorable_excursion_pct", 0)),
                        float(label_record.get("post_exit_max_pct", 0)),
                        bool(label_record.get("post_exit_hit_target", False)),
                        int(label_record.get("post_exit_bars_to_target", 0)),
                        bool(label_record.get("stop_was_sweep", False)),
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
                    r["exit_time"], json.dumps(r["geometry_used"]),
                    float(r.get("max_adverse_excursion_pct", 0)),
                    float(r.get("max_favorable_excursion_pct", 0)),
                    float(r.get("post_exit_max_pct", 0)),
                    bool(r.get("post_exit_hit_target", False)),
                    int(r.get("post_exit_bars_to_target", 0)),
                    bool(r.get("stop_was_sweep", False)),
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
                         (feature_id, label, return_pct, bars_held, exit_time, geometry_used,
                          max_adverse_excursion_pct, max_favorable_excursion_pct,
                          post_exit_max_pct, post_exit_hit_target,
                          post_exit_bars_to_target, stop_was_sweep)
                       VALUES %s
                       ON CONFLICT (feature_id) DO UPDATE SET
                         label = EXCLUDED.label,
                         return_pct = EXCLUDED.return_pct,
                         bars_held = EXCLUDED.bars_held,
                         exit_time = EXCLUDED.exit_time,
                         geometry_used = EXCLUDED.geometry_used,
                         max_adverse_excursion_pct = EXCLUDED.max_adverse_excursion_pct,
                         max_favorable_excursion_pct = EXCLUDED.max_favorable_excursion_pct,
                         post_exit_max_pct = EXCLUDED.post_exit_max_pct,
                         post_exit_hit_target = EXCLUDED.post_exit_hit_target,
                         post_exit_bars_to_target = EXCLUDED.post_exit_bars_to_target,
                         stop_was_sweep = EXCLUDED.stop_was_sweep""",
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
                        n_entries, win_rate, ceiling_sharpe, floor_sharpe, profit_factor,
                        avg_return_pct, total_return_pct, max_drawdown_pct,
                        avg_bars_held, avg_bars_to_loss, pct_loss_hit, pct_time_hit,
                        geometry_json, viable, grade, calibrated_at
                    ) VALUES (
                        %(ticker)s, %(timeframe)s, %(signal_name)s, %(department)s,
                        %(n_entries)s, %(win_rate)s, %(ceiling_sharpe)s, %(floor_sharpe)s, %(profit_factor)s,
                        %(avg_return_pct)s, %(total_return_pct)s, %(max_drawdown_pct)s,
                        %(avg_bars_held)s, %(avg_bars_to_loss)s, %(pct_loss_hit)s, %(pct_time_hit)s,
                        %(geometry_json)s, %(viable)s, %(grade)s, NOW()
                    )
                    ON CONFLICT (ticker, timeframe, signal_name) DO UPDATE SET
                        department = EXCLUDED.department,
                        n_entries = EXCLUDED.n_entries,
                        win_rate = EXCLUDED.win_rate,
                        ceiling_sharpe = EXCLUDED.ceiling_sharpe,
                        floor_sharpe = EXCLUDED.floor_sharpe,
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

    # ── Channel Snapshots ─────────────────────────────────

    _CS_COLUMNS = (
        "ticker", "timeframe", "timestamp", "schema_version",
        "tide_window", "current_window", "wave_window",
        "sigma_tide", "sigma_current", "sigma_wave",
        "reg_value_tide", "reg_value_current", "reg_value_wave",
        "residual_std_tide", "residual_std_current", "residual_std_wave",
        "vwap_sigma_tide", "vwap_sigma_current", "vwap_sigma_wave",
        "vwap_tide", "vwap_current", "vwap_wave",
        "tide_slope", "current_slope", "wave_slope",
        "tide_accel", "current_accel", "wave_accel",
        "conj_wave_current", "conj_wave_tide", "conj_current_tide",
        "spread_tide_current", "spread_tide_wave", "spread_current_wave",
        "vwap_spread_tide_current", "vwap_spread_tide_wave", "vwap_spread_current_wave",
        "fear_level", "fear_label", "regime",
        "wave_flip", "wave_flip_direction",
        "vol_up_down_ratio",
        "below_all_vwaps", "above_all_vwaps",
        "tension_tide", "tension_current", "tension_wave",
        "compression_ratio",
        "rsi_value", "rsi_divergence_strength", "rsi_conviction",
        "kalman_velocity", "vol_adj_delta",
        "geo_state_norm", "geo_velocity_align", "geo_exit_align",
        "geo_accel_align", "geo_phase_angle",
        "vol_surge", "w_duration",
    )

    def ensure_channel_snapshots_table(self) -> None:
        """Create engine.channel_snapshots if it doesn't exist."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE SCHEMA IF NOT EXISTS engine;")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS engine.channel_snapshots (
                        ticker          TEXT NOT NULL,
                        timeframe       TEXT NOT NULL DEFAULT '1d',
                        timestamp       TIMESTAMPTZ NOT NULL,
                        schema_version  SMALLINT NOT NULL DEFAULT 1,
                        computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        tide_window     SMALLINT,
                        current_window  SMALLINT,
                        wave_window     SMALLINT,
                        sigma_tide      DOUBLE PRECISION,
                        sigma_current   DOUBLE PRECISION,
                        sigma_wave      DOUBLE PRECISION,
                        reg_value_tide  DOUBLE PRECISION,
                        reg_value_current DOUBLE PRECISION,
                        reg_value_wave  DOUBLE PRECISION,
                        residual_std_tide DOUBLE PRECISION,
                        residual_std_current DOUBLE PRECISION,
                        residual_std_wave DOUBLE PRECISION,
                        vwap_sigma_tide DOUBLE PRECISION,
                        vwap_sigma_current DOUBLE PRECISION,
                        vwap_sigma_wave DOUBLE PRECISION,
                        vwap_tide       DOUBLE PRECISION,
                        vwap_current    DOUBLE PRECISION,
                        vwap_wave       DOUBLE PRECISION,
                        tide_slope      DOUBLE PRECISION,
                        current_slope   DOUBLE PRECISION,
                        wave_slope      DOUBLE PRECISION,
                        tide_accel      DOUBLE PRECISION,
                        current_accel   DOUBLE PRECISION,
                        wave_accel      DOUBLE PRECISION,
                        conj_wave_current  DOUBLE PRECISION,
                        conj_wave_tide     DOUBLE PRECISION,
                        conj_current_tide  DOUBLE PRECISION,
                        spread_tide_current  DOUBLE PRECISION,
                        spread_tide_wave     DOUBLE PRECISION,
                        spread_current_wave  DOUBLE PRECISION,
                        vwap_spread_tide_current DOUBLE PRECISION,
                        vwap_spread_tide_wave    DOUBLE PRECISION,
                        vwap_spread_current_wave DOUBLE PRECISION,
                        fear_level      SMALLINT,
                        fear_label      TEXT,
                        regime          TEXT,
                        wave_flip       BOOLEAN,
                        wave_flip_direction SMALLINT,
                        vol_up_down_ratio DOUBLE PRECISION,
                        below_all_vwaps BOOLEAN,
                        above_all_vwaps BOOLEAN,
                        tension_tide         DOUBLE PRECISION,
                        tension_current      DOUBLE PRECISION,
                        tension_wave         DOUBLE PRECISION,
                        compression_ratio    DOUBLE PRECISION,
                        rsi_value            DOUBLE PRECISION,
                        rsi_divergence_strength DOUBLE PRECISION,
                        rsi_conviction       DOUBLE PRECISION,
                        kalman_velocity      DOUBLE PRECISION,
                        vol_adj_delta        DOUBLE PRECISION,
                        geo_state_norm       DOUBLE PRECISION,
                        geo_velocity_align   DOUBLE PRECISION,
                        geo_exit_align       DOUBLE PRECISION,
                        geo_accel_align      DOUBLE PRECISION,
                        geo_phase_angle      DOUBLE PRECISION,
                        PRIMARY KEY (ticker, timeframe, timestamp)
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cs_extreme
                    ON engine.channel_snapshots (ticker, sigma_tide)
                    WHERE sigma_tide < -2.0;
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cs_spread
                    ON engine.channel_snapshots (ticker, spread_tide_current);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cs_regime
                    ON engine.channel_snapshots (ticker, regime, timestamp);
                """)
                # ── Migration: add new columns to existing tables ──
                for col in (
                    "tension_tide", "tension_current", "tension_wave",
                    "compression_ratio",
                    "rsi_value", "rsi_divergence_strength", "rsi_conviction",
                    "kalman_velocity", "vol_adj_delta",
                    "geo_state_norm", "geo_velocity_align", "geo_exit_align",
                    "geo_accel_align", "geo_phase_angle",
                    "vol_surge",
                ):
                    cur.execute(f"""
                        ALTER TABLE engine.channel_snapshots
                        ADD COLUMN IF NOT EXISTS {col} DOUBLE PRECISION;
                    """)
                # w_duration is INTEGER, handle separately
                cur.execute("""
                    ALTER TABLE engine.channel_snapshots
                    ADD COLUMN IF NOT EXISTS w_duration INTEGER;
                """)
            conn.commit()
            logger.info("engine.channel_snapshots table ensured.")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create channel_snapshots table: {e}")
            raise
        finally:
            self._put(conn)

    def save_snapshots_batch(
        self,
        ticker: str,
        timeframe: str,
        timestamps: list,
        snapshots: list,
        schema_version: int = 1,
    ) -> int:
        """Batch upsert ChannelSnapshot rows. Idempotent via ON CONFLICT DO UPDATE."""
        if not snapshots:
            return 0
        conn = self._conn()
        try:
            rows = []
            for ts, snap in zip(timestamps, snapshots):
                d = snap.to_dict()
                # Convert numpy types to native Python (psycopg2 can't adapt numpy.bool/int64/float64)
                for k, v in d.items():
                    if hasattr(v, 'item'):
                        d[k] = v.item()
                rows.append((
                    ticker.upper(), timeframe, ts, schema_version,
                    d.get("tide_window"), d.get("current_window"), d.get("wave_window"),
                    d.get("sigma_tide"), d.get("sigma_current"), d.get("sigma_wave"),
                    d.get("reg_value_tide"), d.get("reg_value_current"), d.get("reg_value_wave"),
                    d.get("residual_std_tide"), d.get("residual_std_current"), d.get("residual_std_wave"),
                    d.get("vwap_sigma_tide"), d.get("vwap_sigma_current"), d.get("vwap_sigma_wave"),
                    d.get("vwap_tide"), d.get("vwap_current"), d.get("vwap_wave"),
                    d.get("tide_slope"), d.get("current_slope"), d.get("wave_slope"),
                    d.get("tide_accel"), d.get("current_accel"), d.get("wave_accel"),
                    d.get("conj_wave_current"), d.get("conj_wave_tide"), d.get("conj_current_tide"),
                    d.get("spread_tide_current"), d.get("spread_tide_wave"), d.get("spread_current_wave"),
                    d.get("vwap_spread_tide_current"), d.get("vwap_spread_tide_wave"),
                    d.get("vwap_spread_current_wave"),
                    d.get("fear_level"), d.get("fear_label"), d.get("regime"),
                    d.get("wave_flip"), d.get("wave_flip_direction"),
                    d.get("vol_up_down_ratio"),
                    d.get("below_all_vwaps"), d.get("above_all_vwaps"),
                    d.get("tension_tide"), d.get("tension_current"), d.get("tension_wave"),
                    d.get("compression_ratio"),
                    d.get("rsi_value"), d.get("rsi_divergence_strength"),
                    d.get("rsi_conviction"),
                    d.get("kalman_velocity"), d.get("vol_adj_delta"),
                    d.get("geo_state_norm"), d.get("geo_velocity_align"),
                    d.get("geo_exit_align"),
                    d.get("geo_accel_align"), d.get("geo_phase_angle"),
                    d.get("vol_surge"), d.get("w_duration"),
                ))

            cols = ", ".join(self._CS_COLUMNS)
            update_cols = [c for c in self._CS_COLUMNS if c not in ("ticker", "timeframe", "timestamp")]
            set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
            set_clause += ", computed_at = NOW()"

            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    f"""INSERT INTO engine.channel_snapshots ({cols})
                       VALUES %s
                       ON CONFLICT (ticker, timeframe, timestamp)
                       DO UPDATE SET {set_clause}""",
                    rows,
                    page_size=500,
                )
            conn.commit()
            n = len(rows)
            logger.info(f"channel_snapshots: {ticker}/{timeframe} — upserted {n} rows")
            return n
        except Exception as e:
            conn.rollback()
            logger.error(f"channel_snapshots: {ticker}/{timeframe} save failed: {e}")
            raise
        finally:
            self._put(conn)

    def load_snapshots(
        self,
        ticker: str,
        timeframe: str = "1d",
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> pd.DataFrame:
        """Load snapshots as DataFrame with timestamp index."""
        conn = self._conn()
        try:
            query = "SELECT * FROM engine.channel_snapshots WHERE ticker = %s AND timeframe = %s"
            params: list = [ticker.upper(), timeframe]
            if start:
                query += " AND timestamp >= %s"
                params.append(start)
            if end:
                query += " AND timestamp <= %s"
                params.append(end)
            query += " ORDER BY timestamp"

            df = pd.read_sql(query, self.engine, params=tuple(params), parse_dates=["timestamp"])
            if not df.empty:
                df.set_index("timestamp", inplace=True)
            return df
        finally:
            self._put(conn)

    def load_snapshot_at(self, ticker: str, timestamp, timeframe: str = "1d"):
        """Load a single ChannelSnapshot at a specific timestamp."""
        from backend.modules.shared.domain.entities.channel_snapshot import ChannelSnapshot

        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM engine.channel_snapshots
                    WHERE ticker = %s AND timeframe = %s AND timestamp = %s
                """, (ticker.upper(), timeframe, timestamp))
                row = cur.fetchone()
                if not row:
                    return None
                d = dict(row)
                return ChannelSnapshot(**{
                    k: d[k] for k in ChannelSnapshot.__dataclass_fields__
                    if k in d and d[k] is not None
                })
        finally:
            self._put(conn)

    def count_snapshots(self, ticker: str, timeframe: str = "1d") -> int:
        """Count existing snapshots for a ticker."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM engine.channel_snapshots WHERE ticker = %s AND timeframe = %s",
                    (ticker.upper(), timeframe),
                )
                return cur.fetchone()[0]
        finally:
            self._put(conn)

    # ─── Signal Tape ────────────────────────────────────────────────────

    def ensure_signal_tape_table(self) -> None:
        """Create engine.signal_tape if it doesn't exist."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE SCHEMA IF NOT EXISTS engine;")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS engine.signal_tape (
                        ticker          TEXT NOT NULL,
                        timestamp       TIMESTAMPTZ NOT NULL,
                        bar_index       INT,

                        -- 8 Head Probabilities (raw, uncut)
                        p_long_entry       DOUBLE PRECISION,
                        p_swing_exit       DOUBLE PRECISION,
                        p_pullback_depth   DOUBLE PRECISION,
                        p_trend_reversal   DOUBLE PRECISION,
                        p_short_entry      DOUBLE PRECISION,
                        p_short_cover      DOUBLE PRECISION,
                        p_bounce_height    DOUBLE PRECISION,
                        p_trend_recovery   DOUBLE PRECISION,

                        -- Core Features (snapshot at decision time)
                        sigma_tide      DOUBLE PRECISION,
                        sigma_current   DOUBLE PRECISION,
                        sigma_wave      DOUBLE PRECISION,
                        tide_slope      DOUBLE PRECISION,
                        current_slope   DOUBLE PRECISION,
                        wave_slope      DOUBLE PRECISION,
                        kalman_velocity DOUBLE PRECISION,
                        rsi_value       DOUBLE PRECISION,
                        fear_level      SMALLINT,
                        compression_ratio DOUBLE PRECISION,
                        vol_up_down_ratio DOUBLE PRECISION,
                        regime          TEXT,
                        vol_regime      TEXT,

                        -- Precursor Derivatives (bar-over-bar deltas)
                        d_sigma_wave         DOUBLE PRECISION,
                        d_kalman_velocity    DOUBLE PRECISION,
                        d_rsi_value          DOUBLE PRECISION,
                        d_compression_ratio  DOUBLE PRECISION,
                        d_fear_level         DOUBLE PRECISION,
                        d_vol_up_down_ratio  DOUBLE PRECISION,
                        d_tide_slope         DOUBLE PRECISION,
                        d_wave_accel         DOUBLE PRECISION,

                        -- Derived Features (Forensic Phase 1)
                        slope_decel_wave     DOUBLE PRECISION,
                        slope_decel_current  DOUBLE PRECISION,
                        sigma_divergence     DOUBLE PRECISION,
                        complacency_index    DOUBLE PRECISION,
                        rsi_extreme_zone     SMALLINT,
                        rsi_trap_zone        SMALLINT,
                        rsi_bearish_div      SMALLINT,

                        -- Regression-Based Barriers (informative, not decisional)
                        barrier_reg_profit   DOUBLE PRECISION,
                        barrier_reg_stop     DOUBLE PRECISION,
                        expected_return      DOUBLE PRECISION,

                        -- Forward Returns (REAL, for signal evaluation)
                        fwd_return_5d        DOUBLE PRECISION,
                        fwd_return_10d       DOUBLE PRECISION,
                        fwd_return_20d       DOUBLE PRECISION,
                        fwd_max_dd_5d        DOUBLE PRECISION,
                        fwd_max_runup_5d     DOUBLE PRECISION,
                        fwd_max_dd_10d       DOUBLE PRECISION,
                        fwd_max_runup_10d    DOUBLE PRECISION,

                        -- Optimal Point (post-hoc, for phase offset measurement)
                        bars_to_local_min_10d  INT,
                        bars_to_local_max_10d  INT,
                        local_min_pct          DOUBLE PRECISION,
                        local_max_pct          DOUBLE PRECISION,

                        -- SwingGate Decision (A = baseline, B = ML-modulated)
                        decision_a    TEXT,
                        conviction_a  DOUBLE PRECISION,
                        decision_b    TEXT,
                        conviction_b  DOUBLE PRECISION,

                        PRIMARY KEY (ticker, timestamp)
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_st_ticker_regime
                    ON engine.signal_tape (ticker, regime, timestamp);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_st_decisions
                    ON engine.signal_tape (ticker, decision_a, decision_b);
                """)
            conn.commit()
            logger.info("engine.signal_tape table ensured.")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create signal_tape table: {e}")
            raise
        finally:
            self._put(conn)

    def save_signal_tape_batch(
        self,
        ticker: str,
        rows: list[dict],
        batch_size: int = 500,
    ) -> int:
        """Upsert a batch of signal tape rows.

        Each dict in `rows` must have at least 'timestamp' plus any
        subset of signal_tape columns.
        """
        if not rows:
            return 0

        COLUMNS = [
            'ticker', 'timestamp', 'bar_index',
            'p_long_entry', 'p_swing_exit', 'p_pullback_depth', 'p_trend_reversal',
            'p_short_entry', 'p_short_cover', 'p_bounce_height', 'p_trend_recovery',
            'sigma_tide', 'sigma_current', 'sigma_wave',
            'tide_slope', 'current_slope', 'wave_slope',
            'kalman_velocity', 'rsi_value', 'fear_level',
            'compression_ratio', 'vol_up_down_ratio', 'regime', 'vol_regime',
            'd_sigma_wave', 'd_kalman_velocity', 'd_rsi_value',
            'd_compression_ratio', 'd_fear_level', 'd_vol_up_down_ratio',
            'd_tide_slope', 'd_wave_accel',
            'slope_decel_wave', 'slope_decel_current', 'sigma_divergence',
            'complacency_index', 'rsi_extreme_zone', 'rsi_trap_zone', 'rsi_bearish_div',
            'barrier_reg_profit', 'barrier_reg_stop', 'expected_return',
            'fwd_return_5d', 'fwd_return_10d', 'fwd_return_20d',
            'fwd_max_dd_5d', 'fwd_max_runup_5d',
            'fwd_max_dd_10d', 'fwd_max_runup_10d',
            'bars_to_local_min_10d', 'bars_to_local_max_10d',
            'local_min_pct', 'local_max_pct',
            'decision_a', 'conviction_a', 'decision_b', 'conviction_b',
        ]

        update_cols = [c for c in COLUMNS if c not in ('ticker', 'timestamp')]
        update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)

        placeholders = ", ".join(["%s"] * len(COLUMNS))
        sql = f"""
            INSERT INTO engine.signal_tape ({", ".join(COLUMNS)})
            VALUES ({placeholders})
            ON CONFLICT (ticker, timestamp) DO UPDATE SET {update_clause}
        """

        total = 0
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    values = []
                    for row in batch:
                        row['ticker'] = ticker.upper()
                        vals = tuple(row.get(c) for c in COLUMNS)
                        values.append(vals)

                    psycopg2.extras.execute_batch(cur, sql, values, page_size=100)
                    total += len(batch)
                    logger.info(f"signal_tape: {ticker}/1d — upserted {len(batch)} rows")

            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"signal_tape batch failed for {ticker}: {e}")
            raise
        finally:
            self._put(conn)

        return total

    def load_signal_tape(
        self,
        ticker: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Load signal tape for a ticker, optionally filtered by date range."""
        q = "SELECT * FROM engine.signal_tape WHERE ticker = %s"
        params: list = [ticker.upper()]
        if start:
            q += " AND timestamp >= %s"
            params.append(start)
        if end:
            q += " AND timestamp <= %s"
            params.append(end)
        q += " ORDER BY timestamp"

        return pd.read_sql(q, self.engine, params=params, index_col="timestamp")

