"""
Unit tests for DXY METAR Service & Provider — 11th METAR Station
"""
import pytest
from backend.modules.entry_decision.domain.services.dxy_metar_service import (
    get_dxy_market_metar,
    DXYMarketMETAR,
    StrictDataPolicyError,
)
from backend.daemons.vault_providers.dxy_provider import DXYProvider
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore


def test_dxy_metar_generation():
    """Verify DXY METAR generation from Neon Vault data."""
    try:
        metar = get_dxy_market_metar()
        assert isinstance(metar, DXYMarketMETAR)
        assert metar.issuer == "MarketHealthIntelligence.DXYLiquidityAdapter"
        assert metar.dxy_index_value > 50.0  # Real DXY index level
        assert len(metar.p_bull_vector) == 3
        assert len(metar.ev_net_vector) == 3
        assert metar.operational_guidance.startswith("STK_")
        assert "📢 MARKET METAR — DXY US DOLLAR INDEX" in metar.format_cli_broadcast()
    except StrictDataPolicyError as e:
        pytest.skip(f"Vault data not available for DXY: {e}")


def test_dxy_provider_execution():
    """Verify DXY Vault Provider execution and registration."""
    provider = DXYProvider()
    assert provider.name == "dxy_metar"
    assert "dxy" in provider.categories

    store = TimescaleDataStore()
    try:
        res = provider.run_full(store)
        assert res["status"] in ("ok", "skipped")
        if res["status"] == "ok":
            assert "metar_id" in res
            assert "dxy_value" in res
    finally:
        store.close()
