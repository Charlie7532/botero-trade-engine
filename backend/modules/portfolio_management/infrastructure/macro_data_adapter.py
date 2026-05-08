"""
Macro Data Adapter — Reads VIX and yield curve data from the Neon Vault.

Implements MacroDataPort for the portfolio_management domain.
All data is sourced from TimescaleDataStore (populated by the Vault Daemon).
"""
import logging

logger = logging.getLogger(__name__)


class VaultMacroAdapter:
    """
    Reads macro indicators (VIX, yield curve) from the Neon Vault.
    Data is captured daily by the Vault Daemon's vault_fred_data() task.
    """

    def fetch_vix(self) -> float:
        """Read current VIX from the vault's macro/fred summary."""
        try:
            from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
            store = TimescaleDataStore()
            snapshot = store.load_mcp_snapshot("macro/fred", "SUMMARY")
            store.close()
            if snapshot and isinstance(snapshot, dict):
                vix_data = snapshot.get("VIX", {})
                if isinstance(vix_data, dict) and vix_data.get("close"):
                    return float(vix_data["close"])
        except Exception as e:
            logger.warning(f"VaultMacroAdapter: Error reading VIX from vault: {e}")
        return 20.0  # Safe default

    def fetch_yield_spread(self) -> float:
        """Read yield curve spread (10Y - 3M) from the vault's macro/fred summary."""
        try:
            from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
            store = TimescaleDataStore()
            snapshot = store.load_mcp_snapshot("macro/fred", "SUMMARY")
            store.close()
            if snapshot and isinstance(snapshot, dict):
                y10 = snapshot.get("YIELD_10Y", {})
                y3m = snapshot.get("YIELD_3M", {})
                if isinstance(y10, dict) and isinstance(y3m, dict):
                    close_10y = y10.get("close", 0)
                    close_3m = y3m.get("close", 0)
                    if close_10y and close_3m:
                        return float(close_10y) - float(close_3m)
        except Exception as e:
            logger.warning(f"VaultMacroAdapter: Error reading yield spread from vault: {e}")
        return 0.5  # Safe default


class FREDMacroAdapter:
    """
    Parses macro data from FRED MCP responses.
    Wraps the existing FREDMacroIntelligence infrastructure.
    """

    def __init__(self):
        self._fred = None

    def _get_fred(self):
        if self._fred is None:
            from backend.modules.flow_intelligence.infrastructure.fred_adapter import FREDMacroIntelligence
            self._fred = FREDMacroIntelligence()
        return self._fred

    def parse_macro_snapshot(self, indicators_data: dict):
        """Parse raw FRED MCP data into a MacroSnapshot."""
        return self._get_fred().parse_macro_snapshot(indicators_data=indicators_data)
