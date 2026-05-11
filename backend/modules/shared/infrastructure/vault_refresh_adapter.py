"""
Vault Refresh Adapter — Infrastructure
==========================================
PostgreSQL-backed implementation of VaultRefreshPort.
Uses vault.refresh_queue table for request management.
"""
import logging
from datetime import datetime, UTC

from backend.modules.shared.domain.ports.vault_refresh_port import (
    VaultRefreshPort, RefreshRequest, RefreshStatus,
)

logger = logging.getLogger(__name__)

# Priority ordering for drain queries
_PRIORITY_ORDER = {"urgent": 0, "normal": 1, "low": 2}


class VaultRefreshAdapter(VaultRefreshPort):
    """PostgreSQL-backed vault refresh queue."""

    def __init__(self, store):
        """Accept a TimescaleDataStore (or any object with _conn/_put)."""
        self._store = store

    def request_refresh(self, request: RefreshRequest) -> int:
        """Enqueue a refresh request. Deduplicates pending requests."""
        conn = self._store._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO vault.refresh_queue
                        (ticker, category, priority, requested_by)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (ticker, category) WHERE status = 'pending'
                    DO UPDATE SET
                        priority = CASE
                            WHEN EXCLUDED.priority = 'urgent' THEN 'urgent'
                            ELSE vault.refresh_queue.priority
                        END,
                        requested_at = NOW()
                    RETURNING id
                """, (request.ticker, request.category,
                      request.priority, request.requested_by))
                row = cur.fetchone()
                conn.commit()
                req_id = row[0] if row else -1
                logger.info(
                    f"📥 Refresh requested: {request.ticker}/{request.category} "
                    f"priority={request.priority} by={request.requested_by} id={req_id}"
                )
                return req_id
        finally:
            self._store._put(conn)

    def check_freshness(
        self, ticker: str, category: str, max_age_hours: int = 24,
    ) -> bool:
        """Check if the most recent successful refresh is within max_age_hours."""
        conn = self._store._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT completed_at FROM vault.refresh_queue
                    WHERE ticker = %s AND category = %s AND status = 'done'
                    ORDER BY completed_at DESC LIMIT 1
                """, (ticker, category))
                row = cur.fetchone()
                if not row or row[0] is None:
                    return False
                age_hours = (datetime.now(UTC) - row[0]).total_seconds() / 3600
                return age_hours < max_age_hours
        finally:
            self._store._put(conn)

    def pending_requests(self, limit: int = 50) -> list[RefreshStatus]:
        """Get pending requests ordered by priority (urgent first) then time."""
        conn = self._store._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, ticker, category, status, requested_at,
                           completed_at, error
                    FROM vault.refresh_queue
                    WHERE status = 'pending'
                    ORDER BY
                        CASE priority
                            WHEN 'urgent' THEN 0
                            WHEN 'normal' THEN 1
                            WHEN 'low' THEN 2
                        END,
                        requested_at ASC
                    LIMIT %s
                """, (limit,))
                return [
                    RefreshStatus(
                        request_id=r[0], ticker=r[1], category=r[2],
                        status=r[3], requested_at=r[4],
                        completed_at=r[5], error=r[6],
                    )
                    for r in cur.fetchall()
                ]
        finally:
            self._store._put(conn)

    def mark_processing(self, request_id: int) -> None:
        """Mark a request as being processed."""
        conn = self._store._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE vault.refresh_queue SET status = 'processing' WHERE id = %s",
                    (request_id,)
                )
                conn.commit()
        finally:
            self._store._put(conn)

    def mark_done(self, request_id: int) -> None:
        """Mark a request as completed."""
        conn = self._store._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE vault.refresh_queue SET status = 'done', "
                    "completed_at = NOW() WHERE id = %s",
                    (request_id,)
                )
                conn.commit()
        finally:
            self._store._put(conn)

    def mark_failed(self, request_id: int, error: str) -> None:
        """Mark a request as failed."""
        conn = self._store._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE vault.refresh_queue SET status = 'failed', "
                    "completed_at = NOW(), error = %s WHERE id = %s",
                    (error, request_id)
                )
                conn.commit()
        finally:
            self._store._put(conn)
