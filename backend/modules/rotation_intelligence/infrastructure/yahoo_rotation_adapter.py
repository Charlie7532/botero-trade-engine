"""
Yahoo Finance Rotation Adapter — RotationDataPort implementation.

Fetches ETF price/volume data via pre-fetched Yahoo Finance MCP data.
Per rule #7: adapters receive pre-fetched data.
"""
import logging
from typing import Any

from backend.modules.rotation_intelligence.domain.ports.rotation_data_port import (
    RotationDataPort,
)

logger = logging.getLogger(__name__)


class YahooRotationAdapter(RotationDataPort):
    """
    Implements RotationDataPort using Yahoo Finance MCP pre-fetched data.

    Receives data already fetched by the orchestration layer.
    """

    def __init__(self, mcp_data: dict[str, Any] | None = None):
        self._mcp_data = mcp_data or {}
        self._available = bool(self._mcp_data)

    def update_data(self, mcp_data: dict[str, Any]) -> None:
        """Update with fresh MCP data."""
        self._mcp_data = mcp_data
        self._available = bool(mcp_data)

    def fetch_etf_data(
        self, symbols: list[str], period: str = "3mo"
    ) -> dict[str, dict]:
        """
        Extract ETF data from pre-fetched MCP payload.

        Expected MCP data structure per symbol:
        {
            "symbol": {
                "prices": [float, ...],
                "volumes": [float, ...],
                "current": float
            }
        }
        """
        result = {}
        for symbol in symbols:
            data = self._mcp_data.get(symbol)
            if not data:
                logger.debug(f"No MCP data for {symbol}, skipping.")
                continue

            prices = data.get("prices", [])
            volumes = data.get("volumes", [])
            current = data.get("current", prices[-1] if prices else 0)

            if prices:
                result[symbol] = {
                    "prices": prices,
                    "volumes": volumes,
                    "current": current,
                }

        return result

    @property
    def is_available(self) -> bool:
        """Whether MCP data has been loaded."""
        return self._available
