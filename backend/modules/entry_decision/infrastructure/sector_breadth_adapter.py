"""
Vault Sector Breadth Adapter — Infrastructure Implementation
==============================================================
Reads S5 breadth data and ETF prices exclusively from the Vault
(Neon PostgreSQL via TimescaleDataStore). No external API calls.

Implements: SectorBreadthDataPort (domain/ports/)
"""
import logging
from typing import Optional

import pandas as pd

from backend.modules.entry_decision.domain.ports.sector_breadth_port import (
    SectorBreadthDataPort,
)
from backend.modules.shared.infrastructure.timescale_data_store import (
    TimescaleDataStore,
)
from backend.modules.shared.domain.constants.sectors import (
    SECTOR_ETFS,
    SECTOR_BREADTH_TICKERS,
    SECTOR_VOLUME_BREADTH_TICKERS as _SV5_TICKERS,
)

logger = logging.getLogger(__name__)

# Finviz sector names → sector ETF symbol
_SECTOR_TO_ETF: dict[str, str] = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Financial Services": "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Cyclical": "XLY",
    "Consumer Staples": "XLP",
    "Consumer Defensive": "XLP",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Basic Materials": "XLB",
    "Materials": "XLB",
    "Communication Services": "XLC",
}

# Tier mapping from empirical validation (s5_backtest_signals)
_TIER_MAP: dict[str, int] = {
    "XLP": 1, "XLV": 1, "XLU": 1, "XLRE": 1, "XLB": 1,  # Defensive
    "XLE": 2, "XLF": 2, "XLC": 2,                         # Mixed
    "XLK": 3, "XLY": 3, "XLI": 3,                         # Cyclical
}


class VaultSectorBreadthAdapter(SectorBreadthDataPort):
    """Reads S5 breadth data and ETF prices from the Vault."""

    def __init__(self, store: TimescaleDataStore):
        self._store = store
        self._sector_cache: dict[str, str] = {}
        self._bars_cache: dict[str, pd.DataFrame] = {}

    def get_sector_for_ticker(self, ticker: str) -> Optional[str]:
        """Lookup sector ETF from market.ticker_metadata."""
        if ticker in self._sector_cache:
            return self._sector_cache[ticker]

        # If the ticker IS a sector ETF, return itself
        if ticker in SECTOR_ETFS:
            self._sector_cache[ticker] = ticker
            return ticker

        conn = None
        try:
            conn = self._store._conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT sector FROM market.ticker_metadata WHERE ticker = %s",
                (ticker,),
            )
            row = cur.fetchone()

            if row and row[0]:
                etf = _SECTOR_TO_ETF.get(row[0])
                if etf:
                    self._sector_cache[ticker] = etf
                    return etf
                logger.debug(
                    f"SectorBreadth: Unknown sector mapping for '{row[0]}' (ticker={ticker})"
                )
        except Exception as e:
            logger.debug(f"SectorBreadth: Metadata lookup failed for {ticker}: {e}")
        finally:
            if conn:
                self._store._put(conn)

        return None

    def get_s5_fi_value(self, sector_etf: str) -> Optional[float]:
        """Returns latest S5_FI close value for a sector."""
        fi_ticker = SECTOR_BREADTH_TICKERS.get(sector_etf, {}).get("intermediate")
        if not fi_ticker:
            return None
        return self._latest_close(fi_ticker)

    def get_s5_th_value(self, sector_etf: str) -> Optional[float]:
        """Returns latest S5_TH close value for a sector."""
        th_ticker = SECTOR_BREADTH_TICKERS.get(sector_etf, {}).get("structural")
        if not th_ticker:
            return None
        return self._latest_close(th_ticker)

    def get_s5_tw_value(self, sector_etf: str) -> Optional[float]:
        """Returns latest S5_TW close value for a sector."""
        tw_ticker = SECTOR_BREADTH_TICKERS.get(sector_etf, {}).get("tactical")
        if not tw_ticker:
            return None
        return self._latest_close(tw_ticker)

    def get_s5_tw_prev_value(self, sector_etf: str) -> Optional[float]:
        """Returns previous day's S5_TW close value for a sector."""
        tw_ticker = SECTOR_BREADTH_TICKERS.get(sector_etf, {}).get("tactical")
        if not tw_ticker:
            return None
        try:
            df = self._load_bars_cached(tw_ticker)
            if df is None or len(df) < 2:
                return None
            return float(df["close"].iloc[-2])
        except Exception as e:
            logger.debug(f"SectorBreadth: Previous close failed for {tw_ticker}: {e}")
            return None

    def get_market_s5_fi(self) -> Optional[float]:
        """Returns latest S5FI (market-wide breadth)."""
        return self._latest_close("S5FI")

    def get_s5_fi_history(self, ticker: str, lookback: int = 10) -> list[float]:
        """Returns last N close values. ticker can be S5_XLK_FI or S5FI."""
        try:
            df = self._load_bars_cached(ticker)
            if df is None or df.empty:
                return []
            closes = df["close"].astype(float).tail(lookback + 5)
            return closes.tolist()[-lookback:]
        except Exception as e:
            logger.debug(f"SectorBreadth: History load failed for {ticker}: {e}")
            return []

    def is_etf_above_ma200(self, sector_etf: str) -> bool:
        """Check if sector ETF price is above its 200-DMA."""
        try:
            df = self._load_bars_cached(sector_etf)
            if df is None or len(df) < 200:
                return True  # Default to BULL if insufficient data
            close = df["close"].astype(float)
            ma200 = close.rolling(200).mean().iloc[-1]
            current = close.iloc[-1]
            return bool(current > ma200)
        except Exception as e:
            logger.debug(f"SectorBreadth: MA200 check failed for {sector_etf}: {e}")
            return True  # Default to BULL

    def get_sector_tier(self, sector_etf: str) -> int:
        """Returns tier for threshold calibration."""
        return _TIER_MAP.get(sector_etf, 2)

    def clear_cache(self) -> None:
        """Clear bars cache between evaluation batches."""
        self._bars_cache.clear()

    def _load_bars_cached(self, ticker: str) -> Optional[pd.DataFrame]:
        """Load bars with per-session cache. Eliminates redundant Vault queries."""
        if ticker in self._bars_cache:
            return self._bars_cache[ticker]
        try:
            df = self._store.load_bars(ticker, "1d")
            if df is not None:
                self._bars_cache[ticker] = df
            return df
        except Exception as e:
            logger.debug(f"SectorBreadth: load_bars failed for {ticker}: {e}")
            return None

    def _latest_close(self, ticker: str) -> Optional[float]:
        """Get the most recent close value for a ticker."""
        try:
            df = self._load_bars_cached(ticker)
            if df is None or df.empty:
                return None
            return float(df["close"].iloc[-1])
        except Exception as e:
            logger.debug(f"SectorBreadth: Latest close failed for {ticker}: {e}")
            return None

    # ── S5V (Volume Breadth) ────────────────────────────────

    def get_sv5_fi_value(self, sector_etf: str) -> Optional[float]:
        fi_ticker = _SV5_TICKERS.get(sector_etf, {}).get("intermediate")
        if not fi_ticker:
            return None
        return self._latest_close(fi_ticker)

    def get_sv5_th_value(self, sector_etf: str) -> Optional[float]:
        th_ticker = _SV5_TICKERS.get(sector_etf, {}).get("structural")
        if not th_ticker:
            return None
        return self._latest_close(th_ticker)

    def get_sv5_tw_value(self, sector_etf: str) -> Optional[float]:
        tw_ticker = _SV5_TICKERS.get(sector_etf, {}).get("tactical")
        if not tw_ticker:
            return None
        return self._latest_close(tw_ticker)

    def get_sv5_tw_prev_value(self, sector_etf: str) -> Optional[float]:
        tw_ticker = _SV5_TICKERS.get(sector_etf, {}).get("tactical")
        if not tw_ticker:
            return None
        try:
            df = self._load_bars_cached(tw_ticker)
            if df is None or len(df) < 2:
                return None
            return float(df["close"].iloc[-2])
        except Exception as e:
            logger.debug(f"SectorBreadth: SV5 prev close failed for {tw_ticker}: {e}")
            return None

    def get_market_sv5_fi(self) -> Optional[float]:
        return self._latest_close("SV5FI")

    # ── Multi-scale history ─────────────────────────────────

    def get_s5_history_by_scale(
        self, sector_etf: str, scale: str, lookback: int = 25,
    ) -> list[float]:
        ticker = SECTOR_BREADTH_TICKERS.get(sector_etf, {}).get(scale, "")
        if not ticker:
            return []
        try:
            df = self._load_bars_cached(ticker)
            if df is None or df.empty:
                return []
            closes = df["close"].astype(float).tail(lookback + 5)
            return closes.tolist()[-lookback:]
        except Exception as e:
            logger.debug(f"SectorBreadth: History by scale failed for {ticker}: {e}")
            return []

