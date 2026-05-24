"""
TickerProfileStore — Infrastructure Adapter for Per-Ticker Profiles
=====================================================================
Implements TickerProfilePort using Neon PostgreSQL (engine.ticker_profiles).

Stores profiles as JSONB blobs, read whole on load. This is intentional:
profiles are trained offline and consumed as complete units.

Clean Architecture: Infrastructure layer. Depends on domain port.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

from backend.modules.shared.domain.entities.ticker_profile import TickerProfile
from backend.modules.shared.domain.ports.ticker_profile_port import TickerProfilePort

logger = logging.getLogger(__name__)


class TickerProfileStore(TickerProfilePort):
    """PostgreSQL adapter for TickerProfile persistence.

    Uses engine.ticker_profiles table with JSONB storage.
    Connection reuse: accepts an external connection pool or DSN.
    """

    _TABLE = "engine.ticker_profiles"

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
        """Create the ticker_profiles table if it doesn't exist."""
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(f"""
            CREATE SCHEMA IF NOT EXISTS engine;

            CREATE TABLE IF NOT EXISTS {self._TABLE} (
                ticker       TEXT PRIMARY KEY,
                profile_json JSONB NOT NULL,
                trained_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                version      INT NOT NULL DEFAULT 1
            );
        """)
        conn.commit()
        cur.close()
        logger.info("TickerProfileStore: table ensured")

    def save_profile(self, profile: TickerProfile) -> None:
        """Save or update a ticker's calibrated profile."""
        conn = self._conn()
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        profile.trained_at = now

        profile_dict = profile.to_dict()
        profile_json = json.dumps(profile_dict)

        cur.execute(f"""
            INSERT INTO {self._TABLE} (ticker, profile_json, trained_at, version)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (ticker) DO UPDATE SET
                profile_json = EXCLUDED.profile_json,
                trained_at = EXCLUDED.trained_at,
                version = EXCLUDED.version
        """, (
            profile.ticker,
            profile_json,
            now,
            profile.version,
        ))
        conn.commit()
        cur.close()
        logger.info(f"TickerProfileStore: saved profile for {profile.ticker} "
                     f"(n={profile.n_observations}, v{profile.version})")

    def load_profile(self, ticker: str) -> Optional[TickerProfile]:
        """Load the calibrated profile for a ticker."""
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(f"""
            SELECT profile_json FROM {self._TABLE}
            WHERE ticker = %s
        """, (ticker.upper(),))
        row = cur.fetchone()
        cur.close()

        if not row:
            return None

        data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return TickerProfile.from_dict(data)

    def load_all_profiles(self) -> list[TickerProfile]:
        """Load all trained profiles."""
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(f"""
            SELECT profile_json FROM {self._TABLE}
            ORDER BY ticker
        """)
        rows = cur.fetchall()
        cur.close()

        profiles = []
        for row in rows:
            data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            profiles.append(TickerProfile.from_dict(data))
        return profiles

    def delete_profile(self, ticker: str) -> bool:
        """Delete a profile. Returns True if existed."""
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(f"""
            DELETE FROM {self._TABLE} WHERE ticker = %s
        """, (ticker.upper(),))
        deleted = cur.rowcount > 0
        conn.commit()
        cur.close()
        return deleted
