"""
Unit tests for Institutional Volume Turbulence (SV5_TURBULENCE) Market NOTAM Service (Zero Fallback & Strict Timestamp Policy)
"""
import pytest
from backend.modules.entry_decision.domain.services.sv5_turbulence_notam_service import (
    get_sv5_turbulence_market_notam,
    MarketNOTAM,
    StrictDataPolicyError
)


def test_sv5_turbulence_market_notam_generation():
    """Verify that get_sv5_turbulence_market_notam generates a valid, timestamped NOTAM on-demand."""
    notam = get_sv5_turbulence_market_notam()
    assert isinstance(notam, MarketNOTAM)
    assert notam.timestamp_utc.endswith("Z")
    assert len(notam.as_of_date) == 10  # YYYY-MM-DD
    assert notam.notam_id.startswith("NOTAM-SV5TURB-")
    assert notam.issuer == "MarketHealthIntelligence.SV5TurbulenceAdapter"

    # Check probabilities and capital velocity
    assert 0.0 <= notam.primary_p_bull <= 1.0
    assert isinstance(notam.primary_capital_velocity, float)
    assert len(notam.p_bull_vector) == 3


def test_sv5_turbulence_market_notam_formatting():
    """Verify JSON export and CLI broadcast formatting."""
    notam = get_sv5_turbulence_market_notam()
    notam_dict = notam.to_dict()
    assert "timestamp_utc" in notam_dict
    assert "as_of_date" in notam_dict

    cli_str = notam.format_cli_broadcast()
    assert "MARKET NOTAM — INSTITUTIONAL VOLUME TURBULENCE (SV5_TURBULENCE)" in cli_str
    assert notam.as_of_date in cli_str


def test_sv5_turbulence_market_notam_strict_data_policy():
    """Verify Strict Data Policy: raises StrictDataPolicyError on invalid/unupdated requested dates."""
    with pytest.raises(StrictDataPolicyError) as exc_info:
        get_sv5_turbulence_market_notam(as_of_date="1900-01-01")

    msg = str(exc_info.value)
    assert "NOTAM NOT AVAILABLE" in msg
    assert "Data not updated in Neon Vault" in msg
