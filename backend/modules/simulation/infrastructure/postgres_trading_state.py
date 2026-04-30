"""
PostgreSQL Trading State — Dual-Mode Adapter
================================================
Implements TradingStatePort with two access patterns:
  - READS: Direct SQL to payload.* schema (fast, bulk)
  - WRITES: REST API to Payload CMS (preserves lifecycle hooks)

Replaces PayloadCMSSyncAdapter.
"""
import logging
import os
from typing import Optional

import psycopg2
import psycopg2.pool
import requests

from backend.modules.simulation.domain.ports.trading_state_port import (
    TradingStatePort,
    InstrumentRecord,
)

logger = logging.getLogger(__name__)


class PostgresTradingState(TradingStatePort):
    """Dual-mode adapter: SQL reads from payload.*, REST writes to Payload API."""

    def __init__(
        self,
        dsn: str | None = None,
        api_url: str | None = None,
        api_key: str | None = None,
    ):
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=3,
            dsn=dsn or os.environ.get("POSTGRES_URL", ""),
        )
        self._api_url = api_url or os.getenv("PAYLOAD_API_URL", "http://localhost:3000/api")
        self._api_key = api_key or os.getenv("PAYLOAD_API_KEY", "")

    # ── Connection helpers ────────────────────────────────

    def _conn(self):
        return self._pool.getconn()

    def _put(self, conn):
        self._pool.putconn(conn)

    def close(self):
        """Release all connections."""
        self._pool.closeall()

    # ── READS: Direct SQL to payload.* ───────────────────

    def get_instrument_universe(self) -> list[InstrumentRecord]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, ticker, name,
                              COALESCE(gics_sector, '') AS sector,
                              COALESCE(instrument_type, '') AS instrument_type
                       FROM payload.instruments
                       WHERE is_active = true
                       ORDER BY ticker"""
                )
                return [InstrumentRecord(*row) for row in cur.fetchall()]
        finally:
            self._put(conn)

    def get_active_regime(self) -> Optional[dict]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, phase, start_date, confidence
                       FROM payload.regime_phases
                       WHERE status = 'active'
                       ORDER BY start_date DESC
                       LIMIT 1"""
                )
                row = cur.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "phase": row[1],
                        "start_date": str(row[2]) if row[2] else None,
                        "confidence": row[3],
                    }
                return None
        finally:
            self._put(conn)

    def get_calibration_profiles(self, category: str) -> list[dict]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT * FROM payload.calibration_profiles
                       WHERE category = %s AND status = 'active'""",
                    (category,),
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            self._put(conn)

    # ── WRITES: REST API to Payload (lifecycle hooks) ────

    def _rest_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"users API-Key {self._api_key}"
        return headers

    def _rest_post(self, collection: str, data: dict) -> dict:
        """POST to Payload REST API. Raises on failure."""
        url = f"{self._api_url}/{collection}"
        resp = requests.post(url, json=data, headers=self._rest_headers(), timeout=10)
        if resp.status_code not in (200, 201):
            logger.warning(f"REST POST {collection} failed ({resp.status_code}): {resp.text[:200]}")
            resp.raise_for_status()
        return resp.json()

    def save_calibration_profile(self, profile: dict) -> str:
        result = self._rest_post("calibration-profiles", profile)
        doc_id = str(result.get("doc", {}).get("id", ""))
        logger.info(f"TradingState: calibration profile saved → {doc_id}")
        return doc_id

    def save_screening_results(self, results: list[dict]) -> int:
        saved = 0
        for result in results:
            try:
                self._rest_post("candidate-screenings", result)
                saved += 1
            except Exception as e:
                logger.warning(f"TradingState: screening save failed: {e}")
        logger.info(f"TradingState: {saved}/{len(results)} screenings saved")
        return saved

    def save_trade_snapshot(self, snapshot: dict) -> str:
        result = self._rest_post("trade-snapshots", snapshot)
        doc_id = str(result.get("doc", {}).get("id", ""))
        logger.info(f"TradingState: trade snapshot saved → {doc_id}")
        return doc_id
