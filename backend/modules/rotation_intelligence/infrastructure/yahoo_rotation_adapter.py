"""
Yahoo Finance Rotation Adapter — RotationDataPort implementation.

Primary: pre-fetched MCP data.
Fallback: direct yfinance fetch when MCP data is unavailable.
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
    yfinance direct fetch when MCP data is missing.
    """

    def __init__(self, mcp_data: dict[str, Any] | None = None):
        self._mcp_data = mcp_data or {}
        self._available = True  # Always available via yfinance fallback

    def update_data(self, mcp_data: dict[str, Any]) -> None:
        """Update with fresh MCP data."""
        self._mcp_data = mcp_data

    def fetch_etf_data(
        self, symbols: list[str], period: str = "3mo"
    ) -> dict[str, dict]:
        """
        Extract ETF data from pre-fetched MCP payload.
        Falls back to Neon DB, then yfinance direct fetch.
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

        # 2. Try Neon DB
        if missing:
            still_missing = []
            try:
                from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
                from datetime import date, timedelta
                store = TimescaleDataStore()
                start_date = date.today() - timedelta(days=100) # approx 3mo
                for symbol in missing:
                    df = store.load_bars(symbol, "1d", start=start_date)
                    if not df.empty and len(df) >= 20:
                        result[symbol] = {
                            "prices": df["close"].values.tolist(),
                            "volumes": df["volume"].values.tolist(),
                            "current": float(df["close"].iloc[-1]),
                        }
                    else:
                        still_missing.append(symbol)
                store.close()
            except Exception as e:
                logger.debug(f"DB rotation fetch failed: {e}")
                still_missing = missing
            
            missing = still_missing

        # 3. Fallback: yfinance direct fetch for missing symbols
        if missing:
            result.update(self._fetch_yfinance(missing, period))

        return result

    def _fetch_yfinance(
        self, symbols: list[str], period: str = "3mo"
    ) -> dict[str, dict]:
        """Direct yfinance fetch as fallback."""
        try:
            import yfinance as yf
        except ImportError:
            logger.error("yfinance not installed — cannot fetch rotation data")
            return {}

        result = {}
        try:
            data = yf.download(
                symbols, period=period, progress=False, threads=True
            )
            if data is None or data.empty:
                return result

            for symbol in symbols:
                try:
                    if len(symbols) > 1:
                        close = data["Close"][symbol].dropna()
                        vol = data["Volume"][symbol].dropna()
                    else:
                        close = data["Close"].dropna()
                        vol = data["Volume"].dropna()

                    if len(close) < 20:
                        continue

                    result[symbol] = {
                        "prices": close.values.tolist(),
                        "volumes": vol.values.tolist(),
                        "current": float(close.iloc[-1]),
                    }
                except Exception as e:
                    logger.debug(f"Error extracting {symbol}: {e}")
        except Exception as e:
            logger.error(f"yfinance batch download failed: {e}")

        if result:
            logger.info(
                f"Rotation fallback: fetched {len(result)}/{len(symbols)} ETFs via yfinance"
            )
        return result

    @property
    def is_available(self) -> bool:
        """Always available via yfinance fallback."""
        return True
