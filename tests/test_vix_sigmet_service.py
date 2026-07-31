"""
Unit tests for CBOE Volatility Index (VIX) Market SIGMET Service (Zero Fallback & Strict Timestamp Policy)
"""
import pytest
from backend.modules.entry_decision.domain.services.vix_sigmet_service import (
    get_vix_market_sigmet,
    MarketSIGMET,
    StrictDataPolicyError
)

def test_vix_market_sigmet_generation():
    """Verify that get_vix_market_sigmet generates a valid, timestamped SIGMET on-demand."""
    sigmet = get_vix_market_sigmet()
    assert isinstance(sigmet, MarketSIGMET)
    assert sigmet.timestamp_utc.endswith("Z")
    assert len(sigmet.as_of_date) == 10  # YYYY-MM-DD
    assert sigmet.sigmet_id.startswith("SIGMET-VIX-")
    assert sigmet.issuer == "MarketHealthIntelligence.VIXVolatilityAdapter"
    
    assert 0.0 <= sigmet.primary_p_bull <= 1.0
    assert isinstance(sigmet.primary_capital_velocity, float)
    assert len(sigmet.p_bull_vector) == 3

def test_vix_market_sigmet_formatting():
    """Verify JSON export and CLI broadcast formatting."""
    sigmet = get_vix_market_sigmet()
    sigmet_dict = sigmet.to_dict()
    assert "timestamp_utc" in sigmet_dict
    assert "as_of_date" in sigmet_dict
    
    cli_str = sigmet.format_cli_broadcast()
    assert "MARKET SIGMET" in cli_str
    assert sigmet.as_of_date in cli_str

def test_vix_market_sigmet_strict_data_policy():
    """Verify Strict Data Policy: raises StrictDataPolicyError on invalid/unupdated requested dates."""
    with pytest.raises(StrictDataPolicyError) as exc_info:
        get_vix_market_sigmet(as_of_date="1900-01-01")
    assert "SIGMET NOT AVAILABLE" in str(exc_info.value)
