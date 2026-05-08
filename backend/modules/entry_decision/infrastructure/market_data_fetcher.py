"""
Entry Decision — Market Data Adapter
======================================
Infrastructure adapter: reads all price data from the Neon Vault.
The hub receives pure DataFrames, never touches yfinance.
Implements EntryMarketDataPort.
"""
import logging
import pandas as pd
from datetime import date, timedelta
from typing import Optional

from backend.modules.entry_decision.domain.ports.market_data_port import EntryMarketDataPort

logger = logging.getLogger(__name__)


class MarketDataFetcher(EntryMarketDataPort):
    """Fetches price data, VIX, and SPY from the Neon Vault. Implements EntryMarketDataPort."""

    def __init__(self):
        self._spy_cache: Optional[pd.DataFrame] = None
        self._spy_cache_date: Optional[date] = None

    def _load_bars_from_vault(self, ticker: str) -> Optional[pd.DataFrame]:
        """Load OHLCV bars from the Neon Vault via TimescaleDataStore."""
        try:
            from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
            store = TimescaleDataStore()
            start_date = date.today() - timedelta(days=100)
            df = store.load_bars(ticker, "1d", start=start_date)
            store.close()
            if not df.empty:
                df.rename(columns={
                    "open": "Open", "high": "High", "low": "Low",
                    "close": "Close", "volume": "Volume"
                }, inplace=True)
                return df
        except Exception as e:
            logger.error(f"MarketDataFetcher: vault load error for {ticker}: {e}")
        return None

    def fetch_prices(self, ticker: str) -> Optional[pd.DataFrame]:
        """Load 3-month OHLCV for a ticker from the Neon Vault."""
        df = self._load_bars_from_vault(ticker)
        if df is None or df.empty:
            logger.warning(f"MarketDataFetcher: no vault data for {ticker}")
        return df

    def fetch_vix(self) -> float:
        """Read current VIX from the vault's macro/fred summary."""
        try:
            from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
            store = TimescaleDataStore()

            # Primary: macro/fred SUMMARY snapshot
            snapshot = store.load_mcp_snapshot("macro/fred", "SUMMARY")
            store.close()
            if snapshot and isinstance(snapshot, dict):
                vix_data = snapshot.get("VIX", {})
                if isinstance(vix_data, dict) and vix_data.get("close"):
                    return float(vix_data["close"])
        except Exception as e:
            logger.warning(f"MarketDataFetcher: vault VIX error: {e}")

        # Fallback: try the vix_close macro series
        try:
            from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
            store = TimescaleDataStore()
            df = store.load_macro("vix_close")
            store.close()
            if df is not None and not df.empty:
                return float(df['value'].iloc[-1])
        except Exception:
            pass

        return 17.0  # Safe default

    def calc_rs_vs_spy(self, prices: pd.DataFrame) -> float:
        """Calculate 20-day Relative Strength vs SPY. Uses internal cache."""
        try:
            today = date.today()
            if self._spy_cache is None or self._spy_cache_date != today:
                self._spy_cache = self._load_bars_from_vault("SPY")
                self._spy_cache_date = today

            spy = self._spy_cache
            if spy is not None and len(prices) >= 20 and len(spy) >= 20:
                stock_ret = float(prices['Close'].iloc[-1]) / float(prices['Close'].iloc[-20]) - 1
                spy_ret = float(spy['Close'].iloc[-1]) / float(spy['Close'].iloc[-20]) - 1
                return round((1 + stock_ret) / (1 + spy_ret), 4)
        except Exception:
            pass
        return 1.0
