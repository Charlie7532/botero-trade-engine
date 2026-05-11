"""
Remaining Vault Providers — Consolidated
============================================
Lightweight provider wrappers for the remaining daemon functions.
Each delegates to the existing vault_* function in data_vault_daemon.py,
adding run_ticker() support for VRR on-demand requests.

These will be used by drain_refresh_queue() to handle on-demand requests.
The full-cycle (run_full) still delegates to the original functions.
"""
import logging

from backend.daemons.vault_providers import register_provider
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)


class VIXProvider:
    """VIX live snapshots — runs every cycle (no daily skip)."""
    name = "vix"
    categories = ["vix"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        from backend.daemons.data_vault_daemon import vault_vix_live
        return vault_vix_live(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        return self.run_full(store)


class CBOEProvider:
    """CBOE indices — SKEW + VVIX from CBOE CDN."""
    name = "cboe"
    categories = ["cboe", "skew", "vvix"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        from backend.daemons.data_vault_daemon import vault_cboe_indices
        return vault_cboe_indices(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        return self.run_full(store)


class FREDProvider:
    """FRED macro indicators."""
    name = "fred"
    categories = ["fred"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        from backend.daemons.data_vault_daemon import vault_fred_macro
        return vault_fred_macro(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        return self.run_full(store)


class MarketIndicesProvider:
    """Market indices — SPX, DXY, TNX, Gold, Oil via yfinance."""
    name = "market_indices"
    categories = ["macro"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        from backend.daemons.data_vault_daemon import vault_market_indices
        return vault_market_indices(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        return self.run_full(store)


class FearGreedProvider:
    """CNN Fear & Greed index."""
    name = "fear_greed"
    categories = ["fear_greed"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        from backend.daemons.data_vault_daemon import vault_fear_greed
        return vault_fear_greed(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        return self.run_full(store)


class PortfolioProvider:
    """Portfolio data from connected brokers."""
    name = "portfolio"
    categories = ["portfolio"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        from backend.daemons.data_vault_daemon import vault_portfolio_data
        return vault_portfolio_data(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        return self.run_full(store)


class FinnhubProvider:
    """Finnhub earnings, insider data."""
    name = "finnhub"
    categories = ["finnhub", "earnings"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        from backend.daemons.data_vault_daemon import vault_finnhub_data
        tickers = kwargs.get("tickers", [])
        return vault_finnhub_data(store, tickers)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        from backend.daemons.data_vault_daemon import vault_finnhub_data
        return vault_finnhub_data(store, [ticker])


class SECProvider:
    """SEC 8-K filings."""
    name = "sec"
    categories = ["sec"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        from backend.daemons.data_vault_daemon import vault_sec_8k_filings
        return vault_sec_8k_filings(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        return self.run_full(store)


class GuruFocusProvider:
    """GuruFocus fundamental screening."""
    name = "gurufocus"
    categories = ["fundamental"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        from backend.daemons.data_vault_daemon import vault_gurufocus_screening
        tickers = kwargs.get("tickers", [])
        return vault_gurufocus_screening(store, tickers)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        from backend.daemons.data_vault_daemon import vault_gurufocus_screening
        return vault_gurufocus_screening(store, [ticker])


class YahooProvider:
    """Yahoo Finance fallback data + options chains."""
    name = "yahoo"
    categories = ["yahoo", "options"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        # Yahoo needs VaultInterceptor, not just store
        from backend.daemons.data_vault_daemon import vault_yahoo_data, VaultInterceptor
        interceptor = kwargs.get("interceptor") or VaultInterceptor(store)
        tickers = kwargs.get("tickers", [])
        return vault_yahoo_data(interceptor, tickers)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        from backend.daemons.data_vault_daemon import vault_yahoo_data, VaultInterceptor
        interceptor = VaultInterceptor(store)
        return vault_yahoo_data(interceptor, [ticker])


class UWProvider:
    """Unusual Whales institutional flow."""
    name = "uw"
    categories = ["flow"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        from backend.daemons.data_vault_daemon import vault_uw_data, VaultInterceptor
        interceptor = kwargs.get("interceptor") or VaultInterceptor(store)
        return vault_uw_data(interceptor)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        # UW is market-wide, not per-ticker
        return self.run_full(store)


class GuruPicksProvider:
    """Guru picks from GuruFocus."""
    name = "guru_picks"
    categories = ["guru_picks"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        from backend.daemons.data_vault_daemon import vault_guru_picks
        return vault_guru_picks(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        return self.run_full(store)


class InsiderProvider:
    """Insider activity from Finnhub."""
    name = "insider"
    categories = ["insider"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> dict:
        from backend.daemons.data_vault_daemon import vault_insider_activity
        return vault_insider_activity(store)

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> dict:
        return self.run_full(store)


# ── Auto-register all providers ──
for _cls in [
    VIXProvider, CBOEProvider, FREDProvider, MarketIndicesProvider,
    FearGreedProvider, PortfolioProvider, FinnhubProvider, SECProvider,
    GuruFocusProvider, YahooProvider, UWProvider, GuruPicksProvider,
    InsiderProvider,
]:
    register_provider(_cls())
