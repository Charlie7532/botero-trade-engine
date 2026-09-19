"""
Unit tests for DXY METAR Service & Provider — 11th METAR Station
"""
import pytest
from backend.modules.entry_decision.domain.services.dxy_metar_service import (
    get_dxy_market_metar,
    DXYMarketMETAR,
    StrictDataPolicyError,
)


def test_dxy_metar_generation():
    """Verify DXY METAR generation from Neon Vault data."""
    try:
        metar = get_dxy_market_metar()
        assert isinstance(metar, DXYMarketMETAR)
        assert metar.issuer == "MarketHealthIntelligence.DXYLiquidityAdapter"
        assert metar.dxy_index_value > 50.0  # Real DXY index level
        assert len(metar.p_bull_vector) == 3
        assert len(metar.ev_net_vector) == 3
        assert isinstance(metar.action_code, str)  # Universal taxonomy (Rule 20)
        assert "📢 MARKET METAR — DXY US DOLLAR INDEX" in metar.format_cli_broadcast()
    except StrictDataPolicyError as e:
        pytest.skip(f"Vault data not available for DXY: {e}")

