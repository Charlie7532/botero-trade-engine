"""
Dashboard Sync Port — PayloadCMS Push Interface
==================================================
Decouples the simulation module from the Next.js/PayloadCMS frontend.
Python pushes profiles and snapshots via REST to maintain Payload's
schema ownership over PostgreSQL.

Implementor: payload_cms_sync_adapter.py (Phase 2)
"""
from abc import ABC, abstractmethod
from typing import Any


class DashboardSyncPort(ABC):
    """Port for pushing simulation artifacts to the dashboard."""

    @abstractmethod
    def sync_profile(self, profile: Any) -> bool:
        """
        Push a StrategyProfile to the dashboard.

        Returns True if sync succeeded, False otherwise.
        Failures should be logged but never block trading operations.
        """

    @abstractmethod
    def sync_snapshot(self, snapshot: Any) -> bool:
        """
        Push a TradeSnapshot to the dashboard.

        Returns True if sync succeeded.
        """

    @abstractmethod
    def sync_report(self, report: Any) -> bool:
        """
        Push a simulation/backtest report to the dashboard.

        Returns True if sync succeeded.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the dashboard API is reachable."""
