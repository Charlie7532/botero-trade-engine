"""
Instrument Blacklist — PostgreSQL Adapter
==========================================
Implements InstrumentBlacklistPort using engine.instrument_blacklist table.
"""
import logging
import os
from datetime import datetime, UTC
from dateutil.relativedelta import relativedelta

import psycopg2
import psycopg2.pool

from backend.modules.execution.domain.ports.instrument_blacklist_port import InstrumentBlacklistPort

logger = logging.getLogger(__name__)


class PostgresBlacklistAdapter(InstrumentBlacklistPort):
    """PostgreSQL implementation of the instrument blacklist."""

    def __init__(self, dsn: str | None = None, pool=None):
        if pool is not None:
            self._pool = pool
            self._owns_pool = False
        else:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=2,
                dsn=dsn or os.environ.get("POSTGRES_URL", ""),
            )
            self._owns_pool = True

    def _conn(self):
        return self._pool.getconn()

    def _put(self, conn):
        self._pool.putconn(conn)

    def blacklist(
        self, ticker: str, department: str, reason: str, quarters: int = 4
    ) -> None:
        """Blacklist a ticker for N quarters."""
        until = datetime.now(UTC) + relativedelta(months=quarters * 3)
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO engine.instrument_blacklist
                       (ticker, department, reason, blacklisted_until)
                       VALUES (%s, %s, %s, %s)""",
                    (ticker, department, reason, until),
                )
            conn.commit()
            logger.warning(
                f"🚫 BLACKLISTED: {ticker} in {department} until {until.date()} "
                f"({quarters}Q) — {reason[:80]}"
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    def is_blacklisted(self, ticker: str, department: str) -> bool:
        """Check if a ticker is currently blacklisted."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COUNT(*) FROM engine.instrument_blacklist
                       WHERE ticker = %s AND department = %s
                         AND blacklisted_until > NOW()""",
                    (ticker, department),
                )
                return cur.fetchone()[0] > 0
        finally:
            self._put(conn)

    def get_blacklist(self, department: str) -> list[dict]:
        """Return all active blacklisted instruments for a department."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT ticker, reason, blacklisted_at, blacklisted_until
                       FROM engine.instrument_blacklist
                       WHERE department = %s AND blacklisted_until > NOW()
                       ORDER BY blacklisted_until DESC""",
                    (department,),
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            self._put(conn)

    def close(self):
        if self._owns_pool:
            self._pool.closeall()
