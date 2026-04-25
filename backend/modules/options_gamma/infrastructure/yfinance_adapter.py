"""
Options Gamma — yfinance Options Chain Adapter
===============================================
Infrastructure adapter: this is the ONLY file that touches yfinance.
Domain code in options_engine.py receives raw chain DataFrames.
"""
import logging
import pandas as pd
from typing import Optional, Tuple
from datetime import datetime, UTC

logger = logging.getLogger(__name__)


class YFinanceOptionsAdapter:
    """Fetches options chain data from yfinance."""

    def fetch_chain(self, symbol: str) -> dict:
        """
        Fetch options chain + current price from yfinance.
        
        Returns dict with:
          current_price, expiration, calls (DataFrame), puts (DataFrame)
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

            expiration = exps[0]
            chain = ticker.option_chain(expiration)

            return {
                "current_price": current_price,
                "expiration": expiration,
                "calls": chain.calls,
                "puts": chain.puts,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error(f"YFinanceOptionsAdapter: error for {symbol}: {e}")
            return {}

    def fetch_nearest_expiration(self, symbol: str) -> Optional[str]:
        """Fetch nearest expiration date string."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            exps = ticker.options
            return exps[0] if exps else None
        except Exception:
            return None
