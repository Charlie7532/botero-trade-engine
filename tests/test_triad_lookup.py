"""
Unit Tests for Triad Lookup Adapter
===================================
Tests lookup_triad_signal with various inputs, including direction.
"""
import pytest
from backend.modules.entry_decision.domain.rules.triad_lookup import (
    lookup_triad_signal,
    TriadSignal,
)


def test_lookup_triad_signal_default_direction():
    """Verify that lookup works with default direction (-) when tw_prev_val is not supplied."""
    sig = lookup_triad_signal(
        th_val=15.0,     # structural colapsado (<<)
        fi_val=10.0,     # intermediate colapsado (<<)
        tw_val=12.0,     # tactical colapsado (<<)
        sector_etf="XLK",
        spy_fi_val=50.0,
    )
    assert isinstance(sig, TriadSignal)
    assert sig.triad_key == "<<|<<|<<|-"
    assert sig.dir_bin == "-"
    assert sig.n_samples > 0
    assert "L1_Cyclical" in sig.level or "L2_global" in sig.level


def test_lookup_triad_signal_direction_up():
    """Verify that direction resolves to (+) when tw_val > tw_prev_val."""
    sig = lookup_triad_signal(
        th_val=15.0,
        fi_val=10.0,
        tw_val=20.0,      # táctico subió
        sector_etf="XLK",
        spy_fi_val=50.0,
        tw_prev_val=10.0, # prev táctico más bajo
    )
    assert sig.triad_key == "<<|<<|<|+"
    assert sig.dir_bin == "+"


def test_lookup_triad_signal_direction_down():
    """Verify that direction resolves to (-) when tw_val <= tw_prev_val."""
    sig = lookup_triad_signal(
        th_val=15.0,
        fi_val=10.0,
        tw_val=5.0,        # táctico bajó
        sector_etf="XLK",
        spy_fi_val=50.0,
        tw_prev_val=10.0,  # prev táctico más alto
    )
    assert sig.triad_key == "<<|<<|<<|-"
    assert sig.dir_bin == "-"

    # Equal values should also resolve to "-"
    sig_equal = lookup_triad_signal(
        th_val=15.0,
        fi_val=10.0,
        tw_val=10.0,
        sector_etf="XLK",
        spy_fi_val=50.0,
        tw_prev_val=10.0,
    )
    assert sig_equal.dir_bin == "-"


def test_lookup_triad_signal_fallback_levels():
    """Verify L1/L2 fallbacks and baselines work for rare/unobserved states."""
    # Let's use an unobserved combination: ">>|<<|>>|+"
    sig = lookup_triad_signal(
        th_val=98.0,      # th >>
        fi_val=5.0,       # fi <<
        tw_val=98.0,      # tw >>
        sector_etf="XLK",
        spy_fi_val=50.0,
        tw_prev_val=90.0, # +
    )
    # Even if this specific cell doesn't exist for Cyclical, it should fall back to baseline/global baseline
    assert sig.triad_key == ">>|<<|>>|+"
    assert sig.dir_bin == "+"
    assert sig.n_samples >= 0


def test_lookup_s5v_triad_signal_rom_deviation():
    """Verify that lookup_s5v_triad_signal correctly computes RoM volume breadth subtraction."""
    from backend.modules.entry_decision.domain.rules.triad_lookup import (
        lookup_s5v_triad_signal,
    )
    
    # Test XLK: weight = 65 / 500 = 13% (0.13)
    # vfi_val = 80%, spy_vfi_val = 50%
    # rom_vfi = (50 - 0.13 * 80) / 0.87 = 45.517%
    # rel_fi = 80 - 45.517 = +34.48%
    # v2.0 Z-Score: (34.48 - (-1.0)) / 9.0 = +3.94 → bin ">>"
    sig = lookup_s5v_triad_signal(
        vth_val=50.0,
        vfi_val=80.0,
        vtw_val=50.0,
        sector_etf="XLK",
        spy_vfi_val=50.0,
        vtw_prev_val=49.0,
    )
    
    assert sig.sector_etf == "XLK"
    assert sig.rel_fi_bin == ">>"  # Z-Score +3.94 → extreme positive
    assert sig.rel_bot_factor > 1.0  # Should boost bottom probability
    assert "Z_dev=" in sig.context_label  # v2.0 shows Z-Score, not raw pp

