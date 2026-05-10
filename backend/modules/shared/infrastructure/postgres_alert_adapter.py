"""
Alert & Health — PostgreSQL Adapter
======================================
Implements AlertPort and InstrumentHealthPort using Neon PostgreSQL.

Tables created on first use (idempotent):
  engine.alerts            — threshold-triggered alerts
  engine.instrument_health — progressive health degradation
"""
import json
import logging
import os
from datetime import datetime, UTC
from typing import Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool

from backend.modules.shared.domain.entities.alert_entities import Alert, InstrumentHealth
from backend.modules.shared.domain.ports.alert_port import AlertPort, InstrumentHealthPort

logger = logging.getLogger(__name__)


class PostgresAlertAdapter(AlertPort, InstrumentHealthPort):
    """Neon PostgreSQL adapter for alerts and instrument health."""

    def __init__(self, dsn: str | None = None, pool=None):
        if pool is not None:
            self._pool = pool
            self._owns_pool = False
        else:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=3,
                dsn=dsn or os.environ.get("POSTGRES_URL", ""),
            )
            self._owns_pool = True
        self._ensure_tables()

    def _conn(self):
        return self._pool.getconn()

    def _put(self, conn):
        self._pool.putconn(conn)

    def _ensure_tables(self):
        """Create tables if they don't exist (idempotent)."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE SCHEMA IF NOT EXISTS engine")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS engine.alerts (
                        id SERIAL PRIMARY KEY,
                        time TIMESTAMPTZ DEFAULT NOW(),
                        category TEXT NOT NULL,
                        severity TEXT NOT NULL DEFAULT 'info',
                        ticker TEXT NOT NULL DEFAULT 'MARKET',
                        title TEXT NOT NULL,
                        message TEXT,
                        source TEXT,
                        metric_name TEXT,
                        metric_value DOUBLE PRECISION,
                        previous_value DOUBLE PRECISION,
                        threshold DOUBLE PRECISION,
                        acknowledged BOOLEAN DEFAULT FALSE,
                        resolved BOOLEAN DEFAULT FALSE
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS engine.instrument_health (
                        ticker TEXT NOT NULL,
                        department TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'HEALTHY',
                        reasons JSONB DEFAULT '[]',
                        moat_risk INT DEFAULT 0,
                        margin_decay_pct DOUBLE PRECISION DEFAULT 0,
                        insider_signal TEXT DEFAULT 'neutral',
                        last_updated TIMESTAMPTZ DEFAULT NOW(),
                        PRIMARY KEY (ticker, department)
                    )
                """)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Alert table creation failed: {e}")
        finally:
            self._put(conn)

    # ── AlertPort implementation ─────────────────────────────

    def save_alert(self, alert: Alert) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO engine.alerts
                    (category, severity, ticker, title, message, source,
                     metric_name, metric_value, previous_value, threshold)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    alert.category, alert.severity, alert.ticker,
                    alert.title, alert.message, alert.source,
                    alert.metric_name, alert.metric_value,
                    alert.previous_value, alert.threshold,
                ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Alert save failed: {e}")
        finally:
            self._put(conn)

    def get_active_alerts(
        self,
        category: Optional[str] = None,
        ticker: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> list[Alert]:
        conn = self._conn()
        try:
            conditions = ["resolved = FALSE"]
            params = []
            if category:
                conditions.append("category = %s")
                params.append(category)
            if ticker:
                conditions.append("ticker = %s")
                params.append(ticker)
            if severity:
                conditions.append("severity = %s")
                params.append(severity)

            where = " AND ".join(conditions)
            params.append(limit)

            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"SELECT * FROM engine.alerts WHERE {where} "
                    f"ORDER BY time DESC LIMIT %s",
                    params,
                )
                rows = cur.fetchall()
                return [
                    Alert(
                        category=r["category"],
                        severity=r["severity"],
                        ticker=r["ticker"],
                        title=r["title"],
                        message=r.get("message", ""),
                        source=r.get("source", ""),
                        timestamp=r["time"].isoformat() if r.get("time") else "",
                        metric_name=r.get("metric_name"),
                        metric_value=r.get("metric_value"),
                        previous_value=r.get("previous_value"),
                        threshold=r.get("threshold"),
                        acknowledged=r.get("acknowledged", False),
                        resolved=r.get("resolved", False),
                    )
                    for r in rows
                ]
        finally:
            self._put(conn)

    def acknowledge_alert(self, alert_id: int) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE engine.alerts SET acknowledged = TRUE WHERE id = %s",
                    (alert_id,),
                )
            conn.commit()
        finally:
            self._put(conn)

    def resolve_alert(self, alert_id: int) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE engine.alerts SET resolved = TRUE WHERE id = %s",
                    (alert_id,),
                )
            conn.commit()
        finally:
            self._put(conn)

    # ── InstrumentHealthPort implementation ───────────────────

    def get_health(self, ticker: str, department: str) -> InstrumentHealth:
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM engine.instrument_health "
                    "WHERE ticker = %s AND department = %s",
                    (ticker, department),
                )
                row = cur.fetchone()
                if row:
                    reasons = row.get("reasons", [])
                    if isinstance(reasons, str):
                        reasons = json.loads(reasons)
                    return InstrumentHealth(
                        ticker=row["ticker"],
                        department=row["department"],
                        status=row["status"],
                        reasons=reasons,
                        moat_risk=row.get("moat_risk", 0),
                        margin_decay_pct=row.get("margin_decay_pct", 0.0),
                        insider_signal=row.get("insider_signal", "neutral"),
                        last_updated=row["last_updated"].isoformat() if row.get("last_updated") else "",
                    )
                return InstrumentHealth(ticker=ticker, department=department)
        finally:
            self._put(conn)

    def update_health(self, health: InstrumentHealth) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO engine.instrument_health
                    (ticker, department, status, reasons, moat_risk,
                     margin_decay_pct, insider_signal, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (ticker, department) DO UPDATE SET
                        status = EXCLUDED.status,
                        reasons = EXCLUDED.reasons,
                        moat_risk = EXCLUDED.moat_risk,
                        margin_decay_pct = EXCLUDED.margin_decay_pct,
                        insider_signal = EXCLUDED.insider_signal,
                        last_updated = NOW()
                """, (
                    health.ticker, health.department, health.status,
                    json.dumps(health.reasons), health.moat_risk,
                    health.margin_decay_pct, health.insider_signal,
                ))
            conn.commit()
            if health.status != "HEALTHY":
                logger.warning(
                    f"🏥 {health.ticker} [{health.department}]: "
                    f"health={health.status} (moat_risk={health.moat_risk}, "
                    f"reasons={health.reasons})"
                )
        except Exception as e:
            conn.rollback()
            logger.error(f"Health update failed for {health.ticker}: {e}")
        finally:
            self._put(conn)

    def get_wounded_or_worse(self, department: str) -> list[InstrumentHealth]:
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM engine.instrument_health "
                    "WHERE department = %s AND status IN ('WOUNDED', 'DEATH') "
                    "ORDER BY moat_risk DESC",
                    (department,),
                )
                results = []
                for row in cur.fetchall():
                    reasons = row.get("reasons", [])
                    if isinstance(reasons, str):
                        reasons = json.loads(reasons)
                    results.append(InstrumentHealth(
                        ticker=row["ticker"],
                        department=row["department"],
                        status=row["status"],
                        reasons=reasons,
                        moat_risk=row.get("moat_risk", 0),
                        margin_decay_pct=row.get("margin_decay_pct", 0.0),
                        insider_signal=row.get("insider_signal", "neutral"),
                        last_updated=row["last_updated"].isoformat() if row.get("last_updated") else "",
                    ))
                return results
        finally:
            self._put(conn)

    def close(self):
        if self._owns_pool:
            self._pool.closeall()
