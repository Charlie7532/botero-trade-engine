"""
Entry Decision — Market Data Adapter
======================================
Infrastructure adapter: all yfinance downloads live HERE.
The hub receives pure DataFrames, never touches yfinance.
Implements EntryMarketDataPort.
"""
import logging
import pandas as pd
from datetime import date
from typing import Optional

from backend.modules.entry_decision.domain.ports.market_data_port import EntryMarketDataPort

logger = logging.getLogger(__name__)


class MarketDataFetcher(EntryMarketDataPort):
    """Fetches price data, VIX, and SPY from yfinance. Implements EntryMarketDataPort."""

    def __init__(self):
        self._spy_cache: Optional[pd.DataFrame] = None
        self._spy_cache_date: Optional[date] = None

    def fetch_prices(self, ticker: str) -> Optional[pd.DataFrame]:
        """Download 3-month OHLCV for a ticker. Tries Neon DB first, falls back to yf."""
        try:
            from backend.modules.simulation.infrastructure.timescale_data_store import TimescaleDataStore
            from datetime import timedelta
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
            logger.debug(f"MarketDataFetcher: DB load error for {ticker}: {e}")

        try:
            import yfinance as yf
            data = yf.download(ticker, period='3mo', interval='1d', progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            return data if not data.empty else None
        except Exception as e:
            logger.error(f"MarketDataFetcher: price download error for {ticker}: {e}")
            return None

    def fetch_vix(self) -> float:
        """Get current VIX level. Tries Neon DB first, falls back to yf."""
        try:
            from backend.modules.simulation.infrastructure.timescale_data_store import TimescaleDataStore
            store = TimescaleDataStore()
            df = store.load_macro("vix_close")
            store.close()
            if df is not None and not df.empty:
                return float(df['value'].iloc[-1])
        except Exception:
            pass

        try:
            import yfinance as yf
            vix_data = yf.download('^VIX', period='5d', interval='1d', progress=False)
            if isinstance(vix_data.columns, pd.MultiIndex):
                vix_data.columns = vix_data.columns.get_level_values(0)
            return float(vix_data['Close'].iloc[-1]) if not vix_data.empty else 17.0
        except Exception:
            return 17.0

    def calc_rs_vs_spy(self, prices: pd.DataFrame) -> float:
        """Calculate 20-day Relative Strength vs SPY. Uses internal cache/DB."""
        try:
            today = date.today()
            if self._spy_cache is None or self._spy_cache_date != today:
                df = None
                try:
                    from backend.modules.simulation.infrastructure.timescale_data_store import TimescaleDataStore
                    from datetime import timedelta
                    store = TimescaleDataStore()
                    db_spy = store.load_bars("SPY", "1d", start=today - timedelta(days=100))
                    store.close()
                    if not db_spy.empty:
                        db_spy.rename(columns={
                            "open": "Open", "high": "High", "low": "Low", 
                            "close": "Close", "volume": "Volume"
                        }, inplace=True)
                        df = db_spy
                except Exception:
                    pass

                if df is None or df.empty:
                    import yfinance as yf
                    spy = yf.download('SPY', period='3mo', interval='1d', progress=False)
                    if isinstance(spy.columns, pd.MultiIndex):
                        spy.columns = spy.columns.get_level_values(0)
                    df = spy

                self._spy_cache = df
                self._spy_cache_date = today

            spy = self._spy_cache
            if len(prices) >= 20 and len(spy) >= 20:
                stock_ret = float(prices['Close'].iloc[-1]) / float(prices['Close'].iloc[-20]) - 1
                spy_ret = float(spy['Close'].iloc[-1]) / float(spy['Close'].iloc[-20]) - 1
                return round((1 + stock_ret) / (1 + spy_ret), 4)
        except Exception:
            pass
        return 1.0
