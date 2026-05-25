"""
PostgresRegimeStateAdapter — Infrastructure for Regime State Persistence
==========================================================================
Implements RegimeStatePort using Neon PostgreSQL (market.regime_states).

Follows TickerProfileStore pattern:
  - psycopg2 with os.environ.get("POSTGRES_URL")
  - Connection reuse via _conn() helper
  - Atomic transactions for commit_transition

Clean Architecture: Infrastructure layer. Depends on domain port.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg2
import psycopg2.extras

from backend.modules.shared.domain.entities.state_snapshot import StateSnapshot
from backend.modules.shared.domain.ports.regime_state_port import RegimeStatePort

logger = logging.getLogger(__name__)


class PostgresRegimeStateAdapter(RegimeStatePort):
    """PostgreSQL adapter for regime state persistence.

    Uses market.regime_states table. Connection pattern matches
    TickerProfileStore (shared/infrastructure/).
    """

    _TABLE = "market.regime_states"

    def __init__(self, dsn: str | None = None):
        self._dsn = dsn or os.environ.get("POSTGRES_URL", "")
        self._conn_obj: Optional[psycopg2.extensions.connection] = None

    def _conn(self):
        if self._conn_obj is None or self._conn_obj.closed:
            self._conn_obj = psycopg2.connect(self._dsn)
        return self._conn_obj

    def close(self):
        if self._conn_obj and not self._conn_obj.closed:
            self._conn_obj.close()

    def ensure_table(self) -> None:
        """Create market.regime_states if it doesn't exist."""
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS market.regime_states (
                id             SERIAL PRIMARY KEY,
                key            TEXT NOT NULL,
                current_state  TEXT NOT NULL,
                previous_state TEXT,
                entered_at     TIMESTAMPTZ NOT NULL,
                closed_at      TIMESTAMPTZ,
                duration_bars  INT NOT NULL DEFAULT 1,
                trigger_event  TEXT,
                metadata       JSONB,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_regime_states_active
                ON market.regime_states (key)
                WHERE closed_at IS NULL;

            CREATE INDEX IF NOT EXISTS idx_regime_states_history
                ON market.regime_states (key, entered_at DESC, closed_at DESC NULLS FIRST);

            CREATE INDEX IF NOT EXISTS idx_regime_states_key_range
                ON market.regime_states (key, entered_at);
        """)
        conn.commit()
        cur.close()
        logger.info("PostgresRegimeStateAdapter: table ensured")

    # ── Read operations ──────────────────────────────────────

    def get_current(
        self, key: str, reference_date: Optional[datetime] = None,
    ) -> Optional[StateSnapshot]:
        """Get the active state for a key.

        Production (reference_date=None): returns the row with closed_at IS NULL.
        Backtest (reference_date set): returns the row that was active at that date.
        """
        conn = self._conn()
        cur = conn.cursor()

        if reference_date is None:
            # Production: get currently active state
            cur.execute(f"""
                SELECT key, current_state, previous_state, entered_at,
                       closed_at, duration_bars, trigger_event, metadata
                FROM {self._TABLE}
                WHERE key = %s AND closed_at IS NULL
                ORDER BY entered_at DESC
                LIMIT 1
            """, (key,))
        else:
            # Backtest: get state that was active at reference_date
            cur.execute(f"""
                SELECT key, current_state, previous_state, entered_at,
                       closed_at, duration_bars, trigger_event, metadata
                FROM {self._TABLE}
                WHERE key = %s
                  AND entered_at <= %s
                  AND (closed_at IS NULL OR closed_at > %s)
                ORDER BY entered_at DESC
                LIMIT 1
            """, (key, reference_date, reference_date))

        row = cur.fetchone()
        cur.close()

        if not row:
            return None

        return self._row_to_snapshot(row)

    def load_history(
        self, key: str, start: datetime, end: datetime,
    ) -> list[StateSnapshot]:
        """Load regime transition history for forensic analysis."""
        conn = self._conn()
        cur = conn.cursor()

        cur.execute(f"""
            SELECT key, current_state, previous_state, entered_at,
                   closed_at, duration_bars, trigger_event, metadata
            FROM {self._TABLE}
            WHERE key = %s AND entered_at >= %s AND entered_at <= %s
            ORDER BY entered_at ASC
        """, (key, start, end))

        rows = cur.fetchall()
        cur.close()

        return [self._row_to_snapshot(row) for row in rows]

    # ── Write operations ─────────────────────────────────────

    def commit_transition(
        self,
        key: str,
        next_state: str,
        trigger: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Atomically close current state and open next state.

        Executes within a single SQL transaction (BEGIN...COMMIT).
        If the process crashes mid-operation, the transaction rolls back
        and the key retains its previous active state.
        """
        conn = self._conn()
        ts = timestamp or datetime.now(timezone.utc)
        meta_json = json.dumps(metadata, default=str) if metadata else None

        try:
            cur = conn.cursor()

            # Step 1: Read current active state (for previous_state field)
            cur.execute(f"""
                SELECT current_state FROM {self._TABLE}
                WHERE key = %s AND closed_at IS NULL
                ORDER BY entered_at DESC
                LIMIT 1
            """, (key,))
            active_row = cur.fetchone()
            previous_state = active_row[0] if active_row else None

            # Step 2: Close current active state (if any)
            if active_row:
                cur.execute(f"""
                    UPDATE {self._TABLE}
                    SET closed_at = %s
                    WHERE key = %s AND closed_at IS NULL
                """, (ts, key))

            # Step 3: Insert new state
            cur.execute(f"""
                INSERT INTO {self._TABLE}
                    (key, current_state, previous_state, entered_at,
                     duration_bars, trigger_event, metadata)
                VALUES (%s, %s, %s, %s, 1, %s, %s)
            """, (key, next_state, previous_state, ts, trigger, meta_json))

            conn.commit()
            cur.close()

            logger.info(
                f"RegimeState: {key} transition "
                f"{previous_state or '(none)'}→{next_state} "
                f"trigger={trigger}"
            )
        except Exception:
            conn.rollback()
            raise

    def increment_duration(self, key: str) -> None:
        """Increment duration_bars by 1 for the active state.

        Called daily by daemon for states that did NOT transition.
        No-op if no active state exists for the key.
        """
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(f"""
                UPDATE {self._TABLE}
                SET duration_bars = duration_bars + 1
                WHERE key = %s AND closed_at IS NULL
            """, (key,))
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            raise

    # ── Batch operations (for backfill) ──────────────────────

    def bulk_insert_transitions(
        self, transitions: list[dict[str, Any]],
    ) -> int:
        """Bulk insert historical transitions for backfill.

        Each dict must have: key, current_state, previous_state,
        entered_at, closed_at, duration_bars, trigger_event.

        Returns number of rows inserted.
        """
        if not transitions:
            return 0

        conn = self._conn()
        try:
            rows = [
                (
                    t["key"], t["current_state"], t.get("previous_state"),
                    t["entered_at"], t.get("closed_at"),
                    t.get("duration_bars", 1), t.get("trigger_event"),
                    json.dumps(t["metadata"], default=str) if t.get("metadata") else None,
                )
                for t in transitions
            ]

            cur = conn.cursor()
            psycopg2.extras.execute_values(
                cur,
                f"""INSERT INTO {self._TABLE}
                    (key, current_state, previous_state, entered_at,
                     closed_at, duration_bars, trigger_event, metadata)
                    VALUES %s
                    ON CONFLICT DO NOTHING""",
                rows,
                page_size=500,
            )
            inserted = cur.rowcount
            conn.commit()
            cur.close()

            logger.info(f"RegimeState: bulk inserted {inserted} transitions")
            return inserted
        except Exception:
            conn.rollback()
            raise

    # ── Internal helpers ─────────────────────────────────────

    @staticmethod
    def _row_to_snapshot(row: tuple) -> StateSnapshot:
        """Convert a DB row tuple to StateSnapshot."""
        meta = row[7]
        if isinstance(meta, str):
            meta = json.loads(meta)
        return StateSnapshot(
            key=row[0],
            current_state=row[1],
            previous_state=row[2],
            entered_at=row[3],
            closed_at=row[4],
            duration_bars=row[5],
            trigger_event=row[6],
            metadata=meta,
        )
