"""
Unit tests for CBOE Volatility of Volatility Index (VVIX) Market METAR Service
"""
import pytest
from backend.modules.entry_decision.domain.services.vvix_metar_service import (
    get_vvix_market_metar,
    MarketMETAR,
    StrictDataPolicyError
)

def test_vvix_market_metar_generation():
    """Verify that get_vvix_market_metar generates a valid METAR."""
    metar = get_vvix_market_metar()
    assert isinstance(metar, MarketMETAR)
    assert metar.timestamp_utc.endswith("Z")
    assert metar.metar_id.startswith("METAR-VVIX-")
    assert metar.issuer == "MarketHealthIntelligence.VVIXVolatilityAdapter"

def test_vvix_market_metar_strict_data_policy():
    """Verify Strict Data Policy for requested invalid date."""
    with pytest.raises(StrictDataPolicyError) as exc_info:
        get_vvix_market_metar(as_of_date="1900-01-01")
    assert "METAR NOT AVAILABLE" in str(exc_info.value)
