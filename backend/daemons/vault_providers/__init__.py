"""
Vault Providers — Protocol & Registry
=========================================
Each VaultProvider handles one category of data ingestion.
The daemon orchestrator calls run_full() during scheduled cycles,
and run_ticker() for on-demand VRR requests.

Provider categories match vault.refresh_queue categories:
    ohlcv, breadth, vix, cboe, macro, fred, finnhub,
    fundamental, yahoo, uw, portfolio, sec, guru_picks,
    insider, fear_greed
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)


@runtime_checkable
class VaultProvider(Protocol):
    """Base protocol for all vault data providers."""

    name: str
    """Human-readable provider name (e.g. 'ohlcv', 'breadth')."""

    categories: list[str]
    """Categories this provider handles (matches refresh_queue.category)."""

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        """Run full scheduled update cycle.

        Returns dict with at least {"status": "ok"|"skipped"|"error"}.
        """
        ...

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        """Update a SINGLE ticker on-demand (for VRR requests).

        Returns dict with at least {"status": "ok"|"skipped"|"error"}.
        Not all providers support per-ticker refresh (e.g. breadth requires
        all tickers). In that case, fall back to run_full().
        """
        ...


# Provider registry — populated by each provider module on import
_REGISTRY: dict[str, VaultProvider] = {}


def register_provider(provider: VaultProvider) -> None:
    """Register a provider instance in the global registry."""
    for cat in provider.categories:
        _REGISTRY[cat] = provider
    logger.debug(f"Registered VaultProvider: {provider.name} → {provider.categories}")


def get_provider(category: str) -> VaultProvider | None:
    """Look up the provider responsible for a given category."""
    return _REGISTRY.get(category)


def all_providers() -> dict[str, VaultProvider]:
    """Return the full category→provider mapping."""
    return dict(_REGISTRY)
