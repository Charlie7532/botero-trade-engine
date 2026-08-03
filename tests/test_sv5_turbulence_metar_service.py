"""
Unit tests for Institutional Volume Turbulence (SV5_TURBULENCE) Market METAR Service
"""
import pytest
from backend.modules.entry_decision.domain.services.sv5_turbulence_metar_service import (
    get_sv5_turbulence_market_metar,
    MarketMETAR,
    StrictDataPolicyError
)

def test_sv5_turbulence_market_metar_generation():
    """Verify that get_sv5_turbulence_market_metar generates a valid METAR."""
    metar = get_sv5_turbulence_market_metar()
    assert isinstance(metar, MarketMETAR)
    assert metar.timestamp_utc.endswith("Z")
    assert metar.metar_id.startswith("METAR-SV5TURB-")
    assert metar.issuer == "MarketHealthIntelligence.SV5TurbulenceAdapter"

def test_sv5_turbulence_market_metar_strict_data_policy():
    """Verify Strict Data Policy for requested invalid date."""
    with pytest.raises(StrictDataPolicyError) as exc_info:
        get_sv5_turbulence_market_metar(as_of_date="1900-01-01")
    assert "METAR NOT AVAILABLE" in str(exc_info.value)
