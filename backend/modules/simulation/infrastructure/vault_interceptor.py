"""
Vault Interceptor — Transparent Data Capture
================================================
Decorator pattern that wraps UWDataBridge and GuruFocusAdapter to
automatically vault raw data without modifying existing modules.

Usage:
    bridge = UWDataBridge()
    store = ParquetDataStore()
    interceptor = VaultInterceptor(bridge, store)

    # Same API as UWDataBridge, but data is vaulted transparently
    alerts = interceptor.fetch_and_vault_flow("NVDA")
"""
import logging
from typing import Any, Optional

from backend.modules.simulation.domain.ports.time_series_port import TimeSeriesPort

logger = logging.getLogger(__name__)


class VaultInterceptor:
    """
    Transparent interceptor that vaults raw MCP data.

    Wraps any data bridge and captures responses to the vault
    before returning them to the caller unchanged.
    """

    def __init__(self, store: TimeSeriesPort):
        self.store = store

    # ── UW Flow Interception ──────────────────────────────

    def intercept_flow_alerts(self, ticker: str, alerts: list[dict]) -> list[dict]:
        """Vault flow alerts and return them unchanged."""
        if alerts:
            self.store.save_mcp_snapshot("flow/alerts", ticker, alerts)
        return alerts

    def intercept_spy_flow(self, spy_ticks: list[dict]) -> list[dict]:
        """Vault SPY net-prem ticks and return them unchanged."""
        if spy_ticks:
            self.store.save_mcp_snapshot("flow/spy", "SPY", spy_ticks)
        return spy_ticks

    def intercept_market_tide(self, tide_data: list[dict]) -> list[dict]:
        """Vault market tide data and return it unchanged."""
        if tide_data:
            self.store.save_mcp_snapshot("flow/tide", "MARKET", tide_data)
        return tide_data

    def intercept_darkpool(self, ticker: str, prints: list[dict]) -> list[dict]:
        """Vault darkpool prints and return them unchanged."""
        if prints:
            self.store.save_mcp_snapshot("flow/darkpool", ticker, prints)
        return prints

    def intercept_gex(self, ticker: str, gex_data: dict) -> dict:
        """Vault GEX data and return it unchanged."""
        if gex_data:
            self.store.save_mcp_snapshot("flow/gex", ticker, gex_data)
        return gex_data

    def intercept_sentiment(self, sentiment: dict) -> dict:
        """Vault market sentiment and return it unchanged."""
        if sentiment:
            self.store.save_mcp_snapshot("flow/sentiment", "MARKET", sentiment)
        return sentiment

    # ── GuruFocus Interception ────────────────────────────

    def intercept_qgarp(self, ticker: str, scorecard: Any) -> Any:
        """Vault QGARP scorecard and return it unchanged."""
        data = scorecard
        if hasattr(scorecard, "raw_data"):
            data = scorecard.raw_data or {}
        if hasattr(scorecard, "__dataclass_fields__"):
            from dataclasses import asdict
            data = asdict(scorecard)
        if data:
            self.store.save_mcp_snapshot("fundamental/qgarp", ticker, data)
        return scorecard

    def intercept_risk_matrix(self, ticker: str, risk: Any) -> Any:
        """Vault RiskMatrix5D and return it unchanged."""
        data = risk
        if hasattr(risk, "__dataclass_fields__"):
            from dataclasses import asdict
            data = asdict(risk)
        if data:
            self.store.save_mcp_snapshot("fundamental/risk", ticker, data)
        return risk

    def intercept_insider(self, ticker: str, insider: Any) -> Any:
        """Vault InsiderConviction and return it unchanged."""
        data = insider
        if hasattr(insider, "__dataclass_fields__"):
            from dataclasses import asdict
            data = asdict(insider)
        if data:
            self.store.save_mcp_snapshot("fundamental/insider", ticker, data)
        return insider

    # ── Convenience: Vault a complete UW fetch_all result ─

    def intercept_uw_bundle(self, uw_data: dict, tickers: list[str] | None = None) -> dict:
        """
        Intercept a complete UWDataBridge.fetch_all() result.

        Args:
            uw_data: Dict with spy_ticks, flow_alerts, tide_data, etc.
            tickers: Optional list of tickers to extract per-ticker alerts.

        Returns:
            Same dict, unchanged. Side effect: all data vaulted.
        """
        self.intercept_spy_flow(uw_data.get("spy_ticks", []))
        self.intercept_market_tide(uw_data.get("tide_data", []))

        # Per-ticker alert extraction
        all_alerts = uw_data.get("flow_alerts", [])
        if tickers and all_alerts:
            for ticker in tickers:
                ticker_alerts = [a for a in all_alerts if a.get("ticker") == ticker]
                if ticker_alerts:
                    self.intercept_flow_alerts(ticker, ticker_alerts)

        return uw_data

    # ── Macro Data Interception ───────────────────────────

    def intercept_breadth(self, breadth_data: dict) -> dict:
        """Vault breadth data and return it unchanged."""
        if breadth_data:
            self.store.save_mcp_snapshot("macro/breadth", "MARKET", breadth_data)
        return breadth_data
