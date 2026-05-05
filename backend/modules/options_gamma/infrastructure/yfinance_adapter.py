"""
Options Gamma — yfinance Options Chain Adapter
===============================================
Infrastructure adapter: this is the ONLY file that touches yfinance.
Domain code receives raw chain DataFrames via the OptionsDataPort interface.
"""
import logging
import pandas as pd
from typing import Optional
from datetime import datetime, UTC

from backend.modules.options_gamma.domain.ports.options_data_port import OptionsDataPort

logger = logging.getLogger(__name__)


class YFinanceOptionsAdapter(OptionsDataPort):
    """Fetches options chain data from yfinance. Implements OptionsDataPort."""

    def get_options_chain(self, symbol: str, expiration: Optional[str] = None) -> dict:
        """
        Fetch options chain + current price from yfinance.

        Returns dict with:
          current_price, expiration, calls (DataFrame), puts (DataFrame), timestamp
        Returns empty dict on failure.
        """
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)

            # Current price
            hist = ticker.history(period="1d")
            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = hist.columns.get_level_values(0)
            if hist.empty:
                return {}

            current_price = float(hist['Close'].iloc[-1])

            # Expirations
            exps = ticker.options
            if not exps:
                return {"current_price": current_price}

            exp = expiration if expiration and expiration in exps else exps[0]
            chain = ticker.option_chain(exp)

            return {
                "current_price": current_price,
                "expiration": exp,
                "calls": chain.calls,
                "puts": chain.puts,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error(f"YFinanceOptionsAdapter: error for {symbol}: {e}")
            return {}

    def get_expirations(self, symbol: str) -> list[str]:
        """Get all available expiration dates for the symbol."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            return list(ticker.options) if ticker.options else []
        except Exception:
            return []

    def get_nearest_expiration(self, symbol: str) -> Optional[str]:
        """Fetch nearest expiration date string."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            exps = ticker.options
            return exps[0] if exps else None
        except Exception:
            return None

    def get_current_price(self, symbol: str) -> float:
        """Get the current market price for the underlying."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = hist.columns.get_level_values(0)
            if hist.empty:
                return 0.0
            return float(hist['Close'].iloc[-1])
        except Exception:
            return 0.0
