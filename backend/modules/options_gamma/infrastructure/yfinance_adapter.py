"""
Options Gamma — Hybrid Vault + Live Options Chain Adapter
==========================================================
Infrastructure adapter: reads options chain data from the Neon Vault first.
Falls back to live yfinance fetch only if vault data is stale (>10 min).

This hybrid approach gives the best of both worlds:
- Normal operation: instant reads from Neon (no API latency/rate limits)
- Active entry evaluation: fresh data when vault snapshot is too old
"""
import logging
import pandas as pd
from typing import Optional
from datetime import datetime, UTC, timedelta

from backend.modules.options_gamma.domain.ports.options_data_port import OptionsDataPort

logger = logging.getLogger(__name__)

# Maximum age before triggering a live fetch
STALE_THRESHOLD = timedelta(minutes=10)


class YFinanceOptionsAdapter(OptionsDataPort):
    """Hybrid Vault-First options adapter. Implements OptionsDataPort."""

    def _load_from_vault(self, symbol: str) -> Optional[dict]:
        """Try to load options chain from the Neon Vault."""
        try:
            from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
            store = TimescaleDataStore()
            snapshot = store.load_mcp_latest("yahoo/options", symbol)
            store.close()

            if not snapshot or not isinstance(snapshot, dict):
                return None

            # Check freshness
            ts_str = snapshot.get("timestamp")
            if ts_str:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                age = datetime.now(UTC) - ts
                if age > STALE_THRESHOLD:
                    logger.debug(f"Vault options for {symbol} stale ({age}) — will try live")
                    return None

            # Reconstruct the chain
            calls_data = snapshot.get("calls", [])
            puts_data = snapshot.get("puts", [])
            if not calls_data and not puts_data:
                return None

            return {
                "current_price": snapshot.get("underlying_price", 0.0),
                "expiration": snapshot.get("expiration", ""),
                "calls": pd.DataFrame(calls_data) if calls_data else pd.DataFrame(),
                "puts": pd.DataFrame(puts_data) if puts_data else pd.DataFrame(),
                "timestamp": snapshot.get("timestamp", datetime.now(UTC).isoformat()),
                "source": "vault",
            }
        except Exception as e:
            logger.debug(f"Vault options load for {symbol}: {e}")
            return None

    def _fetch_live(self, symbol: str, expiration: Optional[str] = None) -> dict:
        """Live yfinance fetch — only used when vault is stale."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)

            hist = ticker.history(period="1d")
            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = hist.columns.get_level_values(0)
            if hist.empty:
                return {}

            current_price = float(hist['Close'].iloc[-1])

            exps = ticker.options
            if not exps:
                return {"current_price": current_price}

            exp = expiration if expiration and expiration in exps else exps[0]
            chain = ticker.option_chain(exp)

            logger.info(f"Options for {symbol}: live fetch (vault stale)")
            return {
                "current_price": current_price,
                "expiration": exp,
                "calls": chain.calls,
                "puts": chain.puts,
                "timestamp": datetime.now(UTC).isoformat(),
                "source": "live",
            }
        except Exception as e:
            logger.error(f"YFinanceOptionsAdapter live fetch for {symbol}: {e}")
            return {}

    def get_options_chain(self, symbol: str, expiration: Optional[str] = None) -> dict:
        """
        Fetch options chain + current price.
        Priority: Vault (if fresh) → Live yfinance (if stale).

        Returns dict with:
          current_price, expiration, calls (DataFrame), puts (DataFrame), timestamp
        Returns empty dict on failure.
        """
        # 1. Try vault first
        result = self._load_from_vault(symbol)
        if result:
            return result

        # 2. Fallback: live fetch
        return self._fetch_live(symbol, expiration)

    def get_expirations(self, symbol: str) -> list[str]:
        """Get available expiration dates — from vault snapshot."""
        try:
            from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
            store = TimescaleDataStore()
            snapshot = store.load_mcp_latest("yahoo/options", symbol)
            store.close()
            if snapshot and snapshot.get("expiration"):
                return [snapshot["expiration"]]
        except Exception:
            pass

        # Live fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            return list(ticker.options) if ticker.options else []
        except Exception:
            return []

    def get_nearest_expiration(self, symbol: str) -> Optional[str]:
        """Fetch nearest expiration date string."""
        exps = self.get_expirations(symbol)
        return exps[0] if exps else None

    def get_current_price(self, symbol: str) -> float:
        """Get current market price from the vault's OHLCV bars."""
        try:
            from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
            store = TimescaleDataStore()
            df = store.load_bars(symbol, "1d")
            store.close()
            if not df.empty:
                return float(df["close"].iloc[-1])
        except Exception:
            pass

        # Live fallback
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = hist.columns.get_level_values(0)
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
        except Exception:
            pass
        return 0.0
