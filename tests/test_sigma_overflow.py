import pytest
from backend.modules.entry_decision.domain.rules.sigma_overflow import (
    validate_overflow,
    STATION_MU_SIGMA,
)
from backend.modules.entry_decision.domain.rules.vix_lookup import vix_lookup
from backend.modules.entry_decision.domain.rules.vvix_lookup import vvix_lookup
from backend.modules.entry_decision.domain.rules.pcr_lookup import pcr_lookup
from backend.modules.entry_decision.domain.rules.fg_lookup import fg_lookup
from backend.modules.entry_decision.domain.rules.sv5_turbulence_lookup import sv5_turbulence_lookup
from backend.modules.entry_decision.domain.rules.skew_lookup import skew_lookup
from backend.modules.entry_decision.domain.rules.credit_lookup import credit_lookup
from backend.modules.entry_decision.domain.rules.yield_curve_lookup import yield_curve_lookup
from backend.modules.entry_decision.domain.rules.rotation_lookup import rotation_lookup
from backend.modules.entry_decision.domain.rules.bsi_lookup import bsi_lookup
from backend.modules.entry_decision.domain.rules.dxy_lookup import dxy_lookup
from backend.modules.entry_decision.domain.services.market_sigmet_hazard_service import _check_overflow_sigmet


def test_validate_overflow_within_bounds():
    """Values within ±3σ return None, None."""
    # VIX mean is ~19.44, sigma ~7.73. VIX=20 is ~0.07σ.
    depth, flag = validate_overflow("vix", "d1", 20.0)
    assert depth is None
    assert flag is None

    # D2 velocity near 0.0
    depth, flag = validate_overflow("vix", "d2", 0.0)
    assert depth is None
    assert flag is None

    # D3 vol ratio near 0.5
    depth, flag = validate_overflow("vix", "d3", 0.5)
    assert depth is None
    assert flag is None


def test_validate_overflow_vix_82():
    """VIX=82 is a catastrophic tail event (COVID crash peak, ~8.1σ)."""
    depth, flag = validate_overflow("vix", "d1", 82.0)
    assert depth is not None
    assert pytest.approx(depth, rel=0.05) == 8.09
    assert flag == "UPPER"


def test_validate_overflow_lower_bound():
    """Extreme negative outliers trigger LOWER overflow."""
    # Yield curve spread at -4.0% (mean ~1.39%, sigma ~1.27% -> z = (-4 - 1.39)/1.27 ≈ -4.24)
    depth, flag = validate_overflow("yield_curve", "d1", -4.0)
    assert depth is not None
    assert depth < -3.0
    assert flag == "LOWER"


def test_vix_lookup_normal_vs_overflow():
    """lookup_vix_guidance returns correct sigma depth and keeps state_key intact."""
    # Normal case
    g_normal = vix_lookup.lookup_vix_guidance(20.0, 0.0, 0.5)
    assert g_normal is not None
    assert g_normal.sigma_depth_d1 is None
    assert g_normal.sigma_depth_d2 is None
    assert g_normal.sigma_depth_d3 is None
    assert g_normal.overflow_flag is None
    assert ":" in g_normal.state_key or "__" in g_normal.state_key  # Standard D1:D2:D3 format intact

    # Single dimension overflow (D1 only)
    g_overflow = vix_lookup.lookup_vix_guidance(82.0, 0.0, 0.5)
    assert g_overflow is not None
    assert g_overflow.sigma_depth_d1 is not None
    assert pytest.approx(g_overflow.sigma_depth_d1, rel=0.05) == 8.09
    assert g_overflow.sigma_depth_d2 is None
    assert g_overflow.sigma_depth_d3 is None
    assert g_overflow.overflow_flag == "UPPER"
    assert ":" in g_overflow.state_key or "__" in g_overflow.state_key  # state_key remains standard 3D taxonomy key


def test_multi_dimension_overflow():
    """When 2+ dimensions breach ±3σ, overflow_flag becomes 'MULTI'."""
    # VIX=82 (D1 > 3σ), d3_speed=20.0 (D2 mean ~0, sigma ~2.59 -> z ≈ 7.7 > 3σ)
    g_multi = vix_lookup.lookup_vix_guidance(82.0, 20.0, 0.5)
    assert g_multi is not None
    assert g_multi.sigma_depth_d1 is not None
    assert g_multi.sigma_depth_d2 is not None
    assert g_multi.overflow_flag == "MULTI"


def test_all_11_stations_have_sigma_overflow_fields():
    """All 11 lookup adapters provide sigma depth and overflow flag fields."""
    lookups = [
        ("vix", lambda: vix_lookup.lookup_vix_guidance(20.0, 0.0, 0.5)),
        ("vvix", lambda: vvix_lookup.lookup_vvix_guidance(90.0, 0.0, 0.5)),
        ("pcr", lambda: pcr_lookup.lookup_pcr_guidance(0.9, 0.0, 0.7)),
        ("fg", lambda: fg_lookup.lookup_fg_guidance(50.0, 0.0, 0.45)),
        ("sv5_turbulence", lambda: sv5_turbulence_lookup.lookup_sv5_turbulence_guidance(7.0, 0.0, 0.4)),
        ("skew", lambda: skew_lookup.lookup_skew_guidance(130.0, 0.0, 0.55)),
        ("credit", lambda: credit_lookup.lookup_credit_guidance(0.62, 0.0, 0.5)),
        ("yield_curve", lambda: yield_curve_lookup.lookup_yield_curve_guidance(1.4, 0.0, 0.5)),
        ("rotation", lambda: rotation_lookup.lookup_rotation_guidance(0.5, 0.0, 0.5)),
        ("bsi", lambda: bsi_lookup.lookup_bsi_guidance(50.0, 0.0, 0.5)),
        ("dxy", lambda: dxy_lookup.lookup_dxy_guidance(97.0, 0.0, 0.5)),
    ]

    for station, fn in lookups:
        guidance = fn()
        assert guidance is not None, f"Station {station} returned None"
        assert hasattr(guidance, "sigma_depth_d1"), f"Station {station} missing sigma_depth_d1"
        assert hasattr(guidance, "sigma_depth_d2"), f"Station {station} missing sigma_depth_d2"
        assert hasattr(guidance, "sigma_depth_d3"), f"Station {station} missing sigma_depth_d3"
        assert hasattr(guidance, "overflow_flag"), f"Station {station} missing overflow_flag"

        vec = guidance.to_vector()
        assert "sigma_depth_d1" in vec, f"Station {station} vector missing sigma_depth_d1"
        assert "sigma_depth_d2" in vec, f"Station {station} vector missing sigma_depth_d2"
        assert "sigma_depth_d3" in vec, f"Station {station} vector missing sigma_depth_d3"
        assert "overflow_flag" in vec, f"Station {station} vector missing overflow_flag"


def test_sigmet_overflow_generation():
    """_check_overflow_sigmet creates appropriate SIGMET for MULTI, EXTREMO, MODERADO."""
    class DummyMetar:
        def __init__(self, d1, d2, d3, flag, as_of="2026-08-16"):
            self.sigma_depth_d1 = d1
            self.sigma_depth_d2 = d2
            self.sigma_depth_d3 = d3
            self.overflow_flag = flag
            self.as_of_date = as_of

    now_str = "2026-08-16T00:00:00Z"

    # 1. No overflow
    metar_clean = DummyMetar(None, None, None, None)
    assert _check_overflow_sigmet("VIX", metar_clean, now_str) is None

    # 2. Moderado (3σ < depth <= 4σ)
    metar_mod = DummyMetar(3.5, None, None, "UPPER")
    sig_mod = _check_overflow_sigmet("VIX", metar_mod, now_str)
    assert sig_mod is not None
    assert sig_mod.hazard_type == "OVERFLOW_MODERADO"
    assert sig_mod.severity == "WARNING"
    assert sig_mod.operational_action == "STK_HOLD_STABLE"

    # 3. Extremo (depth > 4σ)
    metar_ext = DummyMetar(8.1, None, None, "UPPER")
    sig_ext = _check_overflow_sigmet("VIX", metar_ext, now_str)
    assert sig_ext is not None
    assert sig_ext.hazard_type == "OVERFLOW_EXTREMO"
    assert sig_ext.severity == "CRITICAL"
    assert sig_ext.operational_action == "STK_BLOCK_CRISIS"

    # 4. Multi-dimensional (Black Swan)
    metar_multi = DummyMetar(3.8, 3.2, None, "MULTI")
    sig_multi = _check_overflow_sigmet("VIX", metar_multi, now_str)
    assert sig_multi is not None
    assert sig_multi.hazard_type == "OVERFLOW_MULTI"
    assert sig_multi.severity == "CRITICAL"
    assert sig_multi.operational_action == "MKT_MACRO_CIRCUIT_BREAKER"
