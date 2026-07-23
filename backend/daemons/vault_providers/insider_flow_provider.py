"""
Insider Flow Provider — Vault Data Provider
==============================================
Concentrates corporate insider transaction ingestion (Finnhub / GuruFocus)
into the Data Vault (Neon PostgreSQL).

Persists data to mcp_snapshot("fundamental/insider", ticker).
Execution order: Runs during fundamental refresh cycles.
"""
import logging
from typing import Dict, Any

from backend.daemons.vault_providers import register_provider, VaultProvider
from backend.daemons.data_vault_daemon import _already_vaulted_today
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

logger = logging.getLogger(__name__)


class InsiderFlowProvider:
    """Vault provider for Corporate Insider Activity (Finnhub/GuruFocus)."""

    name = "insider_flow"
    categories = ["insider", "fundamental/insider"]

    def run_full(self, store: TimescaleDataStore, **kwargs) -> Dict[str, Any]:
        """Runs full scheduled update cycle for key tickers."""
        tickers = kwargs.get("tickers", ["XLK", "XLV", "XLF", "XLE", "SPY"])
        updated = 0

        for ticker in tickers:
            res = self.run_ticker(store, ticker)
            if res.get("status") == "ok":
                updated += 1

        return {"status": "ok", "updated_count": updated}

    def run_ticker(self, store: TimescaleDataStore, ticker: str) -> Dict[str, Any]:
        """Update insider data for a single ticker."""
        if _already_vaulted_today(store, "fundamental/insider", ticker):
            return {"status": "skipped", "reason": "already_today"}

        try:
            # Concentrated Ingestion: try Finnhub adapter, fallback to snapshot
            from backend.modules.flow_intelligence.infrastructure.finnhub_api import FinnhubIntelligence
            finnhub = FinnhubIntelligence()
            data = finnhub.get_insider_activity(ticker)

            if data and data.get("signal"):
                store.save_mcp_snapshot("fundamental/insider", ticker, data)
                logger.info(f"🏛️ Vaulted Insider Flow for {ticker}: {data.get('signal')}")
                return {"status": "ok", "ticker": ticker, "signal": data.get("signal")}
            else:
                return {"status": "skipped", "reason": "no_data"}
        except Exception as e:
            logger.warning(f"⚠️ InsiderFlowProvider error for {ticker}: {e}")
            return {"status": "error", "reason": str(e)}


provider = InsiderFlowProvider()
register_provider(provider)
