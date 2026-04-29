"""
Payload Instruments Adapter — REST API client for Payload CMS collections.

Implements InstrumentRepoPort by making HTTP requests to the Next.js Payload API.
Collections: instruments, regime-phases, calibration-profiles, candidate-screenings, trade-snapshots.

This adapter NEVER imports Payload or Next.js — it uses plain HTTP requests.
"""
import logging
import os
from datetime import datetime, UTC
from typing import Optional

import requests

from backend.modules.portfolio_management.domain.ports.instrument_repo_port import (
    InstrumentRepoPort,
    InstrumentRecord,
    RegimePhaseRecord,
    CalibrationRecord,
)

logger = logging.getLogger(__name__)

PAYLOAD_BASE_URL = os.getenv("PAYLOAD_API_URL", "http://localhost:3000/api")


class PayloadInstrumentsAdapter(InstrumentRepoPort):
    """
    REST adapter for Payload CMS instrument lifecycle collections.

    All operations go through Payload's REST API:
        GET    /api/{collection}?where[field][equals]=value
        POST   /api/{collection}
        PATCH  /api/{collection}/{id}
    """

    def __init__(self, base_url: str = None, api_key: str = None):
        self.base_url = (base_url or PAYLOAD_BASE_URL).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Payload API Key auth (if configured)
        key = api_key or os.getenv("PAYLOAD_API_KEY", "")
        if key:
            self.session.headers["Authorization"] = f"users API-Key {key}"

    # ─── Instruments ─────────────────────────────────────────

    def get_instrument(self, ticker: str) -> Optional[InstrumentRecord]:
        """Get instrument by ticker."""
        resp = self._get("instruments", {"where[ticker][equals]": ticker})
        docs = resp.get("docs", [])
        if not docs:
            return None
        return self._to_instrument(docs[0])

    def upsert_instrument(self, record: InstrumentRecord) -> InstrumentRecord:
        """Create or update an instrument."""
        existing = self.get_instrument(record.ticker)
        payload = self._from_instrument(record)

        if existing and existing.id:
            result = self._patch(f"instruments/{existing.id}", payload)
        else:
            result = self._post("instruments", payload)

        return self._to_instrument(result.get("doc", result))

    def list_instruments(self, universe: str = None, active_only: bool = True) -> list[InstrumentRecord]:
        """List instruments, optionally filtered."""
        params = {"limit": 500}
        if universe:
            params["where[universe][equals]"] = universe
        if active_only:
            params["where[isActive][equals]"] = "true"
        resp = self._get("instruments", params)
        return [self._to_instrument(doc) for doc in resp.get("docs", [])]

    # ─── Regime Phases ──────────────────────────────────────

    def get_active_regime(self, instrument_id: str, level: str) -> Optional[RegimePhaseRecord]:
        """Get active (unclosed) regime phase."""
        resp = self._get("regime-phases", {
            "where[instrument][equals]": instrument_id,
            "where[level][equals]": level,
            "where[closedAt][exists]": "false",
            "sort": "-detectedAt",
            "limit": 1,
        })
        docs = resp.get("docs", [])
        if not docs:
            return None
        return self._to_regime(docs[0])

    def create_regime_phase(self, record: RegimePhaseRecord) -> RegimePhaseRecord:
        """Create a new regime phase. Closes the previous active one first."""
        # Close previous active phase at this level
        active = self.get_active_regime(record.instrument_id, record.level)
        if active and active.id:
            self.close_regime_phase(active.id, record.detected_at or datetime.now(UTC))

        payload = {
            "instrument": record.instrument_id,
            "level": record.level,
            "phase": record.phase,
            "detectedAt": record.detected_at.isoformat() if record.detected_at else datetime.now(UTC).isoformat(),
            "triggerSignal": record.trigger_signal,
            "vixAtDetection": record.vix_at_detection,
            "breadthAtDetection": record.breadth_at_detection,
        }
        if active and active.id:
            payload["previousPhase"] = active.id

        result = self._post("regime-phases", payload)
        return self._to_regime(result.get("doc", result))

    def close_regime_phase(self, phase_id: str, closed_at: datetime) -> None:
        """Close a regime phase."""
        self._patch(f"regime-phases/{phase_id}", {
            "closedAt": closed_at.isoformat(),
        })

    # ─── Calibration Profiles ───────────────────────────────

    def get_active_calibration(self, instrument_id: str, category: str) -> Optional[CalibrationRecord]:
        """Get active calibration."""
        resp = self._get("calibration-profiles", {
            "where[instrument][equals]": instrument_id,
            "where[category][equals]": category,
            "where[status][equals]": "active",
            "sort": "-trainedAt",
            "limit": 1,
        })
        docs = resp.get("docs", [])
        if not docs:
            return None
        return self._to_calibration(docs[0])

    def create_calibration(self, record: CalibrationRecord) -> CalibrationRecord:
        """Create a new calibration profile."""
        payload = {
            "instrument": record.instrument_id,
            "category": record.category,
            "signals": record.signals,
            "compositeSharpe": record.composite_sharpe,
            "winRate": record.win_rate,
            "status": record.status,
            "trainedAt": datetime.now(UTC).isoformat(),
        }
        if record.market_regime_id:
            payload["marketRegime"] = record.market_regime_id
        if record.sector_regime_id:
            payload["sectorRegime"] = record.sector_regime_id
        if record.instrument_regime_id:
            payload["instrumentRegime"] = record.instrument_regime_id
        if record.warm_start_from_id:
            payload["warmStartFrom"] = record.warm_start_from_id
        if record.warm_start_delta:
            payload["warmStartDelta"] = record.warm_start_delta

        result = self._post("calibration-profiles", payload)
        return self._to_calibration(result.get("doc", result))

    def invalidate_calibrations(self, instrument_id: str, invalidated_by_regime_id: str) -> int:
        """Invalidate all active calibrations for an instrument."""
        resp = self._get("calibration-profiles", {
            "where[instrument][equals]": instrument_id,
            "where[status][equals]": "active",
            "limit": 100,
        })
        docs = resp.get("docs", [])
        now = datetime.now(UTC).isoformat()
        for doc in docs:
            self._patch(f"calibration-profiles/{doc['id']}", {
                "status": "invalidated",
                "invalidatedBy": invalidated_by_regime_id,
                "invalidatedAt": now,
            })
        count = len(docs)
        if count:
            logger.info(f"Invalidated {count} calibrations for instrument {instrument_id}")
        return count

    def find_historical_calibration(
        self, instrument_id: str, market_phase: str, sector_phase: str
    ) -> Optional[CalibrationRecord]:
        """Find best historical calibration for warm-start under similar regime."""
        # Query calibrations that were trained under similar regime conditions
        # We need to look at the regime phases associated with each calibration
        resp = self._get("calibration-profiles", {
            "where[instrument][equals]": instrument_id,
            "sort": "-compositeSharpe",
            "limit": 20,
            "depth": 2,  # Populate regime relationships
        })
        docs = resp.get("docs", [])

        for doc in docs:
            # Check if market and sector regime phases match
            mr = doc.get("marketRegime")
            sr = doc.get("sectorRegime")
            if isinstance(mr, dict) and isinstance(sr, dict):
                if mr.get("phase") == market_phase and sr.get("phase") == sector_phase:
                    return self._to_calibration(doc)

        return None

    # ─── HTTP helpers ───────────────────────────────────────

    def _get(self, collection: str, params: dict = None) -> dict:
        """GET request to Payload REST API."""
        try:
            resp = self.session.get(f"{self.base_url}/{collection}", params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Payload GET /{collection} failed: {e}")
            return {"docs": []}

    def _post(self, collection: str, data: dict) -> dict:
        """POST request to Payload REST API."""
        try:
            resp = self.session.post(f"{self.base_url}/{collection}", json=data, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Payload POST /{collection} failed: {e}")
            return {}

    def _patch(self, path: str, data: dict) -> dict:
        """PATCH request to Payload REST API."""
        try:
            resp = self.session.patch(f"{self.base_url}/{path}", json=data, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Payload PATCH /{path} failed: {e}")
            return {}

    # ─── Mapping helpers ────────────────────────────────────

    @staticmethod
    def _to_instrument(doc: dict) -> InstrumentRecord:
        return InstrumentRecord(
            id=doc.get("id"),
            ticker=doc.get("ticker", ""),
            name=doc.get("name", ""),
            instrument_type=doc.get("instrumentType", "stock"),
            gics_sector=doc.get("gicsSector", ""),
            universe=doc.get("universe", "sp500"),
            is_active=doc.get("isActive", True),
            last_fundamentals=doc.get("lastFundamentals"),
            fundamentals_updated_at=None,  # Parse if needed
            next_earnings_date=None,
        )

    @staticmethod
    def _from_instrument(record: InstrumentRecord) -> dict:
        payload = {
            "ticker": record.ticker,
            "name": record.name,
            "instrumentType": record.instrument_type,
            "isActive": record.is_active,
        }
        if record.gics_sector:
            payload["gicsSector"] = record.gics_sector
        if record.universe:
            payload["universe"] = record.universe
        if record.last_fundamentals:
            payload["lastFundamentals"] = record.last_fundamentals
        if record.fundamentals_updated_at:
            payload["fundamentalsUpdatedAt"] = record.fundamentals_updated_at.isoformat()
        if record.next_earnings_date:
            payload["nextEarningsDate"] = record.next_earnings_date.isoformat()
        return payload

    @staticmethod
    def _to_regime(doc: dict) -> RegimePhaseRecord:
        return RegimePhaseRecord(
            id=doc.get("id"),
            instrument_id=doc.get("instrument") if isinstance(doc.get("instrument"), str) else doc.get("instrument", {}).get("id", ""),
            level=doc.get("level", "market"),
            phase=doc.get("phase", "accumulation"),
            detected_at=None,
            closed_at=None,
            trigger_signal=doc.get("triggerSignal", ""),
            vix_at_detection=doc.get("vixAtDetection", 0.0),
            breadth_at_detection=doc.get("breadthAtDetection", 0.0),
        )

    @staticmethod
    def _to_calibration(doc: dict) -> CalibrationRecord:
        return CalibrationRecord(
            id=doc.get("id"),
            instrument_id=doc.get("instrument") if isinstance(doc.get("instrument"), str) else doc.get("instrument", {}).get("id", ""),
            category=doc.get("category", "core_hohn"),
            market_regime_id=doc.get("marketRegime") if isinstance(doc.get("marketRegime"), str) else (doc.get("marketRegime") or {}).get("id"),
            sector_regime_id=doc.get("sectorRegime") if isinstance(doc.get("sectorRegime"), str) else (doc.get("sectorRegime") or {}).get("id"),
            signals=doc.get("signals", []),
            composite_sharpe=doc.get("compositeSharpe", 0.0),
            win_rate=doc.get("winRate", 0.0),
            status=doc.get("status", "active"),
            warm_start_from_id=doc.get("warmStartFrom") if isinstance(doc.get("warmStartFrom"), str) else (doc.get("warmStartFrom") or {}).get("id"),
            warm_start_delta=doc.get("warmStartDelta"),
        )
