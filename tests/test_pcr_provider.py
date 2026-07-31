"""
Unit tests for CBOE Equity Put/Call Ratio (PCR) Vault Provider (Production Daemon Pipeline)
"""
import pytest
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.daemons.vault_providers.pcr_provider import PCRProvider


def test_pcr_provider_registration():
    """Verify that PCRProvider registers under pcr category."""
    provider = PCRProvider()
    assert provider.name == "pcr"
    assert "pcr" in provider.categories


def test_pcr_provider_execution():
    """Verify that PCRProvider runs against Neon Vault and stores MCP snapshot."""
    store = TimescaleDataStore()
    try:
        provider = PCRProvider()
        result = provider.run_full(store)
        assert result["status"] in ("ok", "skipped")
        if result["status"] == "ok":
            assert "state_key" in result
            assert "divergence_regime" in result
            assert "operational_guidance" in result

            # Verify MCP snapshot persistence
            snapshot = store.load_mcp_latest("pcr/notam", "MARKET")
            assert snapshot is not None
            assert isinstance(snapshot, dict)
            assert snapshot["issuer"] == "MarketHealthIntelligence.PCROptionsAdapter"
    finally:
        store.close()
