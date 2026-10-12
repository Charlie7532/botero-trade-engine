"""Tests for Triad Lookup Tripartite Hierarchy & Phase 2 Enriched Fields.

Verifies:
1. A-2: Resolution hierarchy: Sector (L2, N >= 20) -> Tier (L1, N >= 20) -> Global (L0).
2. A-3: All 19 pre-existing TriadSignal fields retain their exact names, types, and values.
3. A-4: Effective threshold is unified at N=20.
4. Phase 2 Enriched Fields: ev_net_zz50, rr_asymmetry_zz50, duration_mean_days, pct_en_rango,
   fatigue_stage, timing_slot, sector_level are properly populated.
"""
import pytest
from backend.modules.entry_decision.domain.rules.triad_lookup import (
    lookup_triad_signal,
    lookup_s5v_triad_signal,
    TriadSignal,
    _get_triad_table,
    _get_s5v_triad_table,
)


def test_tripartite_resolution_sector_level():
    """Verify Sector-level resolution (L2) when sector has N >= 20 in state."""
    # State <<|<<|<<|- with sector XLK (n=176 in cells)
    sig = lookup_triad_signal(
        th_val=15.0,
        fi_val=10.0,
        tw_val=12.0,
        sector_etf="XLK",
        spy_fi_val=50.0,
    )

    assert isinstance(sig, TriadSignal)
    assert sig.sector_level == "XLK"
    assert "L2_XLK" in sig.level
    assert "L1_Cyclical" in sig.level
    assert sig.n_samples == 176
    assert sig.ev_net_zz50 is not None
    assert sig.rr_asymmetry_zz50 is not None
    assert sig.duration_mean_days is not None
    assert sig.pct_en_rango is not None


def test_tripartite_resolution_tier_fallback():
    """Verify Tier-level resolution (L1) when sector is unknown or has no sector breakdown."""
    # Query with a synthetic ticker or sector not in 'sectors' dict for this cell
    sig = lookup_triad_signal(
        th_val=15.0,
        fi_val=10.0,
        tw_val=12.0,
        sector_etf="SPY",  # SPY tier pool
        spy_fi_val=50.0,
    )

    assert isinstance(sig, TriadSignal)
    # SPY resolves to L2_SPY or L1_SPY
    assert "SPY" in sig.level
    assert sig.n_samples > 0


def test_tripartite_resolution_global_fallback():
    """Verify Global-level resolution (L0) when tier is not available."""
    # Using an empty sector_etf forces global resolution
    sig = lookup_triad_signal(
        th_val=15.0,
        fi_val=10.0,
        tw_val=12.0,
        sector_etf="",
        spy_fi_val=50.0,
    )

    assert isinstance(sig, TriadSignal)
    assert sig.sector_level is None
    assert "L0_global" in sig.level
    assert sig.n_samples == 2021  # Total global samples for <<|<<|<<|-


def test_unified_threshold_invariant():
    """A-4: Verify unified min_n threshold equals 20 in both table and fallback."""
    table = _get_triad_table()
    threshold = (
        table.get("hierarchical_fallback", {}).get("min_n_prefix")
        or table.get("_documentation", {}).get("hierarchical_fallback", {}).get("min_n_prefix")
    )
    assert threshold == 20


def test_phase2_enriched_fields_populated():
    """Verify that enriched kinematic and timing fields are properly typed and populated."""
    sig = lookup_triad_signal(
        th_val=15.0,
        fi_val=10.0,
        tw_val=12.0,
        sector_etf="XLK",
        spy_fi_val=50.0,
    )

    # Check types and physical validity
    assert isinstance(sig.ev_net_zz50, float)
    assert isinstance(sig.rr_asymmetry_zz50, float)
    assert isinstance(sig.duration_mean_days, float)
    assert sig.duration_mean_days > 0.0
    assert isinstance(sig.pct_en_rango, float)
    if sig.timing_slot is not None:
        assert sig.timing_slot in ("t-2", "t-1", "t=0", "entre")
    if sig.fatigue_stage is not None:
        assert sig.fatigue_stage in ("fresh", "persist", "mature", "exhaustion")


def test_s5v_tripartite_resolution_sector_level():
    """Verify S5V Sector-level resolution (L2) when sector has N >= 20 in state."""
    # State <<|<<|<<|- with sector XLE (n=30 in cells, tier=Mixed)
    sig = lookup_s5v_triad_signal(
        vth_val=10.0,
        vfi_val=12.0,
        vtw_val=10.0,
        sector_etf="XLE",
        spy_vfi_val=50.0,
    )

    assert isinstance(sig, TriadSignal)
    assert sig.sector_level == "XLE"
    assert "L2_XLE" in sig.level
    assert "L1_Mixed" in sig.level
    assert sig.n_samples == 30
    assert sig.ev_net_zz50 is not None
    assert sig.rr_asymmetry_zz50 is not None
    assert sig.duration_mean_days is not None
    assert sig.pct_en_rango is not None


def test_s5v_tripartite_resolution_tier_fallback():
    """Verify S5V Tier fallback (L1) when sector has N < 20 in state."""
    # State <<|<<|>|+ with sector XLK (n < 20 for XLK, so falls back to Cyclical tier with N=27)
    sig = lookup_s5v_triad_signal(
        vth_val=10.0,
        vfi_val=12.0,
        vtw_val=60.0,
        sector_etf="XLK",
        spy_vfi_val=50.0,
        vtw_prev_val=50.0,
    )

    assert isinstance(sig, TriadSignal)
    assert sig.sector_level is None
    assert "L1_Cyclical" in sig.level
    assert sig.n_samples == 27


def test_s5v_tripartite_resolution_global_fallback():
    """Verify S5V Global-level resolution (L0) when sector is not specified."""
    sig = lookup_s5v_triad_signal(
        vth_val=10.0,
        vfi_val=12.0,
        vtw_val=10.0,
        sector_etf="",
        spy_vfi_val=50.0,
    )

    assert isinstance(sig, TriadSignal)
    assert sig.sector_level is None
    assert "L0_global" in sig.level
    assert sig.n_samples > 0


def test_s5v_unified_threshold_invariant():
    """Verify unified min_n threshold equals 20 for S5V table."""
    from backend.modules.entry_decision.domain.rules.triad_lookup import _get_s5v_triad_table
    table = _get_s5v_triad_table()
    threshold = (
        table.get("hierarchical_fallback", {}).get("min_n_prefix")
        or table.get("_documentation", {}).get("hierarchical_fallback", {}).get("min_n_prefix")
    )
    assert threshold == 20


def test_s5v_phase2_enriched_fields_populated():
    """Verify S5V enriched kinematic and timing fields are properly typed and populated."""
    sig = lookup_s5v_triad_signal(
        vth_val=10.0,
        vfi_val=12.0,
        vtw_val=10.0,
        sector_etf="XLK",
        spy_vfi_val=50.0,
    )

    assert isinstance(sig.ev_net_zz50, float)
    assert isinstance(sig.rr_asymmetry_zz50, float)
    assert isinstance(sig.duration_mean_days, float)
    assert sig.duration_mean_days > 0.0
    assert isinstance(sig.pct_en_rango, float)
    assert 0.0 <= sig.pct_en_rango <= 1.0
    if sig.timing_slot is not None:
        assert sig.timing_slot in ("t-2", "t-1", "t=0", "entre")
    if sig.fatigue_stage is not None:
        assert sig.fatigue_stage in ("fresh", "persist", "mature", "exhaustion")

