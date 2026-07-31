"""
Unit tests for CBOE Volatility of Volatility Index (VVIX) Market SIGMET Service
"""
import pytest
from backend.modules.entry_decision.domain.services.vvix_sigmet_service import (
    get_vvix_market_sigmet,
    MarketSIGMET,
    StrictDataPolicyError
)

def test_vvix_market_sigmet_generation():
    """Verify that get_vvix_market_sigmet generates a valid SIGMET."""
    sigmet = get_vvix_market_sigmet()
    assert isinstance(sigmet, MarketSIGMET)
    assert sigmet.timestamp_utc.endswith("Z")
    assert sigmet.sigmet_id.startswith("SIGMET-VVIX-")
    assert sigmet.issuer == "MarketHealthIntelligence.VVIXVolatilityAdapter"

def test_vvix_market_sigmet_strict_data_policy():
    """Verify Strict Data Policy for requested invalid date."""
    with pytest.raises(StrictDataPolicyError) as exc_info:
        get_vvix_market_sigmet(as_of_date="1900-01-01")
    assert "SIGMET NOT AVAILABLE" in str(exc_info.value)
