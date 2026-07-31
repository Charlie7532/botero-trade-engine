"""
Unit tests for Fear & Greed Market SIGMET Service
"""
import pytest
from backend.modules.entry_decision.domain.services.fg_sigmet_service import (
    get_fg_market_sigmet,
    MarketSIGMET,
    StrictDataPolicyError
)

def test_fg_market_sigmet_generation():
    """Verify that get_fg_market_sigmet generates a valid SIGMET."""
    sigmet = get_fg_market_sigmet()
    assert isinstance(sigmet, MarketSIGMET)
    assert sigmet.timestamp_utc.endswith("Z")
    assert sigmet.sigmet_id.startswith("SIGMET-FG-")
    assert sigmet.issuer == "MarketHealthIntelligence.FearGreedAdapter"

def test_fg_market_sigmet_strict_data_policy():
    """Verify Strict Data Policy for requested invalid date."""
    with pytest.raises(StrictDataPolicyError) as exc_info:
        get_fg_market_sigmet(as_of_date="1900-01-01")
    assert "SIGMET NOT AVAILABLE" in str(exc_info.value)
