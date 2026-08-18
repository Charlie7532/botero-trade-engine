"""
Regression Guard Test: D3 Station Volatility Formula Uniformity (Rule 24 / V1.1)
================================================================================
Guards against regressions in the D3 volatility normalization formula across all 11 METAR services.
All services MUST compute D3 as std(2d) / std(10d), strictly matching the Fact Store
calibration thresholds in v3_fact_table_engine.py.

This test inspects the source code of every METAR service and asserts:
  1. "rolling(2)" is present
  2. "rolling(10)" is present
  3. "rolling(5)" is NOT present (regression guard)
  4. "rolling(20)" is NOT present (regression guard)
"""
from pathlib import Path

SERVICES_DIR = Path(__file__).resolve().parent.parent / "backend" / "modules" / "entry_decision" / "domain" / "services"

METAR_SERVICES = [
    "vix_metar_service.py",
    "vvix_metar_service.py",
    "pcr_metar_service.py",
    "fg_metar_service.py",
    "sv5_turbulence_metar_service.py",
    "skew_metar_service.py",
    "credit_metar_service.py",
    "yield_curve_metar_service.py",
    "rotation_metar_service.py",
    "bsi_metar_service.py",
    "dxy_metar_service.py",
]


def test_volatility_formula_guard():
    """Ensure all 11 METAR services strictly adhere to std(2d)/std(10d) and never regress to std(5d)/std(20d)."""
    for service_file in METAR_SERVICES:
        file_path = SERVICES_DIR / service_file
        assert file_path.exists(), f"METAR service file missing: {file_path}"

        source = file_path.read_text(encoding="utf-8")

        # Positive assertions: must use V1.1 std(2)/std(10)
        assert "rolling(2)" in source, f"{service_file} is missing rolling(2) for D3 vol_norm calculation"
        assert "rolling(10)" in source, f"{service_file} is missing rolling(10) for D3 vol_norm calculation"

        # Negative assertions: must NOT use deprecated std(5)/std(20)
        assert "rolling(5)" not in source, f"{service_file} contains deprecated rolling(5) - must use rolling(2)"
        assert "rolling(20)" not in source, f"{service_file} contains deprecated rolling(20) - must use rolling(10)"
