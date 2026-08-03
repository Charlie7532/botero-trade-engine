"""
Unit tests for CBOE Volatility Index (VIX) Market METAR Service (Zero Fallback & Strict Timestamp Policy)
"""
import pytest
from backend.modules.entry_decision.domain.services.vix_metar_service import (
    get_vix_market_metar,
    MarketMETAR,
    StrictDataPolicyError
)

def test_vix_market_metar_generation():
    """Verify that get_vix_market_metar generates a valid, timestamped METAR on-demand."""
    metar = get_vix_market_metar()
    assert isinstance(metar, MarketMETAR)
    assert metar.timestamp_utc.endswith("Z")
    assert len(metar.as_of_date) == 10  # YYYY-MM-DD
    assert metar.metar_id.startswith("METAR-VIX-")
    assert metar.issuer == "MarketHealthIntelligence.VIXVolatilityAdapter"
    
    assert 0.0 <= metar.primary_p_bull <= 1.0
    assert isinstance(metar.primary_capital_velocity, float)
    assert len(metar.p_bull_vector) == 3

def test_vix_market_metar_formatting():
    """Verify JSON export and CLI broadcast formatting."""
    metar = get_vix_market_metar()
    metar_dict = metar.to_dict()
    assert "timestamp_utc" in metar_dict
    assert "as_of_date" in metar_dict
    
    cli_str = metar.format_cli_broadcast()
    assert "MARKET METAR" in cli_str
    assert metar.as_of_date in cli_str

def test_vix_market_metar_strict_data_policy():
    """Verify Strict Data Policy: raises StrictDataPolicyError on invalid/unupdated requested dates."""
    with pytest.raises(StrictDataPolicyError) as exc_info:
        get_vix_market_metar(as_of_date="1900-01-01")
    assert "METAR NOT AVAILABLE" in str(exc_info.value)
