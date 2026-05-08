"""
Vault Rotation Adapter — RotationDataPort implementation.

Primary: pre-fetched MCP data.
Fallback: Neon Vault (TimescaleDataStore) — NO external API calls.
"""
import logging
from typing import Any

import pandas as pd

from backend.modules.rotation_intelligence.domain.ports.rotation_data_port import (
    RotationDataPort,
)

logger = logging.getLogger(__name__)


class YahooRotationAdapter(RotationDataPort):
    """
    Implements RotationDataPort.

    Uses pre-fetched MCP data when available, falls back to
    Neon Vault (TimescaleDataStore) for historical price data.
    No direct external API calls.
    """

    def __init__(self, mcp_data: dict[str, Any] | None = None):
        self._mcp_data = mcp_data or {}
        self._available = True

    def update_data(self, mcp_data: dict[str, Any]) -> None:
        """Update with fresh MCP data."""
        self._mcp_data = mcp_data

    def fetch_etf_data(
        self, symbols: list[str], period: str = "3mo"
    ) -> dict[str, dict]:
        """
        Extract ETF data from pre-fetched MCP payload.
        Falls back to Neon DB for any missing symbols.
        """
        result = {}
        missing = []

        # 1. Try MCP data first
        for symbol in symbols:
            data = self._mcp_data.get(symbol)
            if data:
                prices = data.get("prices", [])
                volumes = data.get("volumes", [])
                current = data.get("current", prices[-1] if prices else 0)
                if prices:
                    result[symbol] = {
                        "prices": prices,
                        "volumes": volumes,
                        "current": current,
                    }
                    continue
            missing.append(symbol)

        # 2. Fallback: Neon Vault
        if missing:
            try:
                from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
                from datetime import date, timedelta
                store = TimescaleDataStore()
                start_date = date.today() - timedelta(days=200)  # ~6mo
                for symbol in missing:
                    df = store.load_bars(symbol, "1d", start=start_date)
                    if not df.empty and len(df) >= 20:
                        result[symbol] = {
                            "prices": df["close"].values.tolist(),
                            "volumes": df["volume"].values.tolist(),
                            "current": float(df["close"].iloc[-1]),
                        }
                store.close()
            except Exception as e:
                logger.warning(f"Vault rotation fetch failed: {e}")

        fetched_from_vault = len(result) - (len(symbols) - len(missing))
        if fetched_from_vault > 0:
            logger.info(
                f"Rotation: {len(result)}/{len(symbols)} ETFs "
                f"(MCP={len(symbols) - len(missing)}, Vault={fetched_from_vault})"
            )

        return result

    @property
    def is_available(self) -> bool:
        """Always available via Neon Vault."""
        return True
