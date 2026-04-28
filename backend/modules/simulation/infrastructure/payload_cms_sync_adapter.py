"""
Payload CMS Sync Adapter — Dashboard Push Infrastructure
============================================================
Pushes StrategyProfiles, TradeSnapshots, and SimulationReports
to the Next.js/PayloadCMS REST API.

Payload owns the PostgreSQL schema — Python never writes SQL directly.
All data reaches Postgres through Payload's API.
"""
import json
import logging
import os
from typing import Any

from backend.modules.simulation.domain.ports.dashboard_sync_port import DashboardSyncPort

logger = logging.getLogger(__name__)


class PayloadCMSSyncAdapter(DashboardSyncPort):
    """Push simulation artifacts to PayloadCMS via REST."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.getenv("PAYLOAD_API_URL", "http://localhost:3000/api")

    def _post(self, collection: str, data: dict) -> bool:
        """POST data to a Payload collection."""
        try:
            import requests
            url = f"{self.base_url}/{collection}"
            resp = requests.post(
                url,
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if resp.status_code in (200, 201):
                logger.info(f"PayloadSync: {collection} pushed OK")
                return True
            else:
                logger.warning(f"PayloadSync: {collection} failed ({resp.status_code}): {resp.text[:200]}")
                return False
        except ImportError:
            logger.warning("PayloadSync: requests library not available")
            return False
        except Exception as e:
            logger.warning(f"PayloadSync: {collection} error: {e}")
            return False

    def sync_profile(self, profile: Any) -> bool:
        data = profile
        if hasattr(profile, "__dataclass_fields__"):
            from dataclasses import asdict
            data = asdict(profile)
        return self._post("strategy-profiles", data)

    def sync_snapshot(self, snapshot: Any) -> bool:
        data = snapshot
        if hasattr(snapshot, "__dataclass_fields__"):
            from dataclasses import asdict
            data = asdict(snapshot)
        return self._post("trade-snapshots", data)

    def sync_report(self, report: Any) -> bool:
        data = report
        if hasattr(report, "__dataclass_fields__"):
            from dataclasses import asdict
            data = asdict(report)
        return self._post("simulation-reports", data)

    def is_available(self) -> bool:
        try:
            import requests
            resp = requests.get(f"{self.base_url}/globals", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False
