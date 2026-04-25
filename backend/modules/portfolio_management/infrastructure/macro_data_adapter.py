"""
Macro Data Adapter — Fetches VIX and yield curve data from external sources.

Implements MacroDataPort for the portfolio_management domain.
"""
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class YFinanceMacroAdapter:
    """
    Fetches macro indicators (VIX, yield curve) via yfinance.
    Used as a fallback when FRED MCP data is not available.
    """

    def fetch_vix(self) -> float:
        """Download current VIX level."""
        try:
            import yfinance as yf
            vix_data = yf.download("^VIX", period="5d", progress=False)
            if not vix_data.empty:
                if isinstance(vix_data.columns, pd.MultiIndex):
                    vix_data.columns = vix_data.columns.get_level_values(0)
                return float(vix_data['Close'].iloc[-1])
        except Exception as e:
            logger.warning(f"YFinanceMacroAdapter: Error fetching VIX: {e}")
        return 20.0  # Safe default

    def fetch_yield_spread(self) -> float:
        """Download yield curve spread (10Y - 13W T-Bill)."""
        try:
            import yfinance as yf
            tny = yf.download("^TNX", period="5d", progress=False)
            twy = yf.download("^IRX", period="5d", progress=False)

            if not tny.empty and not twy.empty:
                if isinstance(tny.columns, pd.MultiIndex):
                    tny.columns = tny.columns.get_level_values(0)
                if isinstance(twy.columns, pd.MultiIndex):
                    twy.columns = twy.columns.get_level_values(0)
                return float(tny['Close'].iloc[-1] - twy['Close'].iloc[-1])
        except Exception as e:
            logger.warning(f"YFinanceMacroAdapter: Error fetching yield spread: {e}")
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
            from backend.infrastructure.data_providers.fred_macro_intelligence import FREDMacroIntelligence
            self._fred = FREDMacroIntelligence()
        return self._fred

    def parse_macro_snapshot(self, indicators_data: dict):
        """Parse raw FRED MCP data into a MacroSnapshot."""
        return self._get_fred().parse_macro_snapshot(indicators_data=indicators_data)
