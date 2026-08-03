"""
Unit tests for CBOE Equity Put/Call Ratio (CBOE_PCR) Market METAR Service
"""
import pytest
from backend.modules.entry_decision.domain.services.pcr_metar_service import (
    get_pcr_market_metar,
    MarketMETAR,
    StrictDataPolicyError
)

def test_pcr_market_metar_generation():
    """Verify that get_pcr_market_metar generates a valid METAR."""
    metar = get_pcr_market_metar()
    assert isinstance(metar, MarketMETAR)
    assert metar.timestamp_utc.endswith("Z")
    assert metar.metar_id.startswith("METAR-PCR-")
    assert metar.issuer == "MarketHealthIntelligence.PCROptionsAdapter"

def test_pcr_market_metar_strict_data_policy():
    """Verify Strict Data Policy for requested invalid date."""
    with pytest.raises(StrictDataPolicyError) as exc_info:
        get_pcr_market_metar(as_of_date="1900-01-01")
    assert "METAR NOT AVAILABLE" in str(exc_info.value)
