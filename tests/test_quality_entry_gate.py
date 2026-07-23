"""
Unit Tests for QualityEntryGate V28 — H1a Divergent Leadership + H4b Weinstein Smart Veto
===========================================================================================
Tests boundary conditions for H1a (regime classification) and H4b (satellite veto).
"""
import pytest
from backend.modules.entry_decision.application.use_cases.quality_entry_gate import (
    QualityEntryGate,
)

# ── Helpers ──────────────────────────────────────────────────

SECTORS_11 = ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB", "XLE", "XLY"]


def make_sec(val: float) -> dict:
    """Create a sector dict with all 11 sectors at the same value."""
    return {s: val for s in SECTORS_11}


def make_sec_mixed(hot_val: float, cold_val: float, n_hot: int) -> dict:
    """Create a sector dict with n_hot sectors at hot_val and the rest at cold_val."""
    d = {}
    for i, s in enumerate(SECTORS_11):
        d[s] = hot_val if i < n_hot else cold_val
    return d


# ── H1a Divergent Leadership Tests ──────────────────────────


class TestH1aDivergentLeadership:
    """Tests for the Divergent Leadership trigger (V28 H1a)."""

    def test_h1a_triggers_when_1_hot_7_cold(self):
        """H1a fires: exactly 1 sector with TW > 50, 7 sectors with TW < 20."""
        gate = QualityEntryGate()
        # 1 hot (55%), 7 cold (15%), 3 neutral (35%)
        sec_tw = {}
        sec_tw["XLK"] = 55.0  # hot
        for s in ["XLC", "XLF", "XLI", "XLV", "XLP", "XLU", "XLRE"]:
            sec_tw[s] = 15.0  # cold (7 sectors)
        for s in ["XLB", "XLE", "XLY"]:
            sec_tw[s] = 35.0  # neutral

        result = gate.evaluate_regime(
            th=50.0, fi=50.0, tw=40.0,
            v_th=50.0, v_fi=50.0, v_tw=50.0,
            sec_th=make_sec(50.0), sec_fi=make_sec(50.0), sec_tw=sec_tw,
            fi_velocity=0.0, current_mode="NORMAL", days_in_mode=25,
        )
        assert result == "DISTRIBUCION_PRE_CRASH"

    def test_h1a_does_not_trigger_when_2_hot_7_cold(self):
        """H1a does NOT fire: 2 sectors hot (must be <= 1)."""
        gate = QualityEntryGate()
        sec_tw = {}
        sec_tw["XLK"] = 55.0  # hot 1
        sec_tw["XLC"] = 52.0  # hot 2
        for s in ["XLF", "XLI", "XLV", "XLP", "XLU", "XLRE", "XLB"]:
            sec_tw[s] = 15.0  # cold (7 sectors)
        sec_tw["XLE"] = 35.0
        sec_tw["XLY"] = 35.0

        result = gate.evaluate_regime(
            th=50.0, fi=50.0, tw=40.0,
            v_th=50.0, v_fi=50.0, v_tw=50.0,
            sec_th=make_sec(50.0), sec_fi=make_sec(50.0), sec_tw=sec_tw,
            fi_velocity=0.0, current_mode="NORMAL", days_in_mode=25,
        )
        # Should NOT go to DIST_PRE_CRASH via H1a (may go to other regime based on th/fi/tw)
        assert result != "DISTRIBUCION_PRE_CRASH"

    def test_h1a_does_not_trigger_when_1_hot_6_cold(self):
        """H1a does NOT fire: only 6 sectors cold (must be >= 7)."""
        gate = QualityEntryGate()
        sec_tw = {}
        sec_tw["XLK"] = 55.0  # hot
        for s in ["XLC", "XLF", "XLI", "XLV", "XLP", "XLU"]:
            sec_tw[s] = 15.0  # cold (6 sectors — NOT enough)
        for s in ["XLRE", "XLB", "XLE", "XLY"]:
            sec_tw[s] = 35.0  # neutral

        result = gate.evaluate_regime(
            th=50.0, fi=50.0, tw=40.0,
            v_th=50.0, v_fi=50.0, v_tw=50.0,
            sec_th=make_sec(50.0), sec_fi=make_sec(50.0), sec_tw=sec_tw,
            fi_velocity=0.0, current_mode="NORMAL", days_in_mode=25,
        )
        assert result != "DISTRIBUCION_PRE_CRASH"

    def test_h1a_triggers_with_0_hot_7_cold(self):
        """H1a fires: 0 sectors hot, 7 cold (extreme case)."""
        gate = QualityEntryGate()
        sec_tw = {}
        for s in ["XLK", "XLC", "XLF", "XLI", "XLV", "XLP", "XLU"]:
            sec_tw[s] = 15.0  # cold (7)
        for s in ["XLRE", "XLB", "XLE", "XLY"]:
            sec_tw[s] = 35.0  # neutral

        result = gate.evaluate_regime(
            th=50.0, fi=50.0, tw=40.0,
            v_th=50.0, v_fi=50.0, v_tw=50.0,
            sec_th=make_sec(50.0), sec_fi=make_sec(50.0), sec_tw=sec_tw,
            fi_velocity=0.0, current_mode="NORMAL", days_in_mode=25,
        )
        assert result == "DISTRIBUCION_PRE_CRASH"

    def test_h1a_at_exact_boundary_hot50_cold20(self):
        """Boundary: TW exactly 50.0 is NOT > 50, and TW exactly 20.0 is NOT < 20."""
        gate = QualityEntryGate()
        sec_tw = {}
        sec_tw["XLK"] = 50.0  # exactly 50 — NOT hot (requires > 50)
        for s in ["XLC", "XLF", "XLI", "XLV", "XLP", "XLU"]:
            sec_tw[s] = 20.0  # exactly 20 — NOT cold (requires < 20)
        for s in ["XLRE", "XLB", "XLE", "XLY"]:
            sec_tw[s] = 35.0

        result = gate.evaluate_regime(
            th=50.0, fi=50.0, tw=40.0,
            v_th=50.0, v_fi=50.0, v_tw=50.0,
            sec_th=make_sec(50.0), sec_fi=make_sec(50.0), sec_tw=sec_tw,
            fi_velocity=0.0, current_mode="NORMAL", days_in_mode=25,
        )
        # hot=0 (<= 1 ✓) but cold=0 (< 7 ✗) → should NOT trigger
        assert result != "DISTRIBUCION_PRE_CRASH"


# ── H4b Weinstein Smart Veto Tests ──────────────────────────


class TestH4bWeinsteinSmartVeto:
    """Tests for the Weinstein Stage 4 satellite veto (V28 H4b)."""

    def _make_satellite_scenario(self, sec_stage4, vol_div_value):
        """Helper to create a scenario where XLE is the only satellite candidate."""
        gate = QualityEntryGate()
        sec_th = make_sec(60.0)
        sec_fi = make_sec(60.0)
        sec_tw = make_sec(50.0)
        # XLE is the satellite candidate: low FI + high structural
        sec_fi["XLE"] = 30.0
        sec_th["XLE"] = 50.0
        sec_v_fi = make_sec(50.0)
        sec_v_fi["XLE"] = 30.0 + vol_div_value  # vol_div = sec_v_fi - sec_fi
        rs_roc = {s: 0.0 for s in SECTORS_11}
        rs_roc["XLE"] = 0.01  # positive RS → candidate

        target = gate.calculate_target_weights(
            "NORMAL", sec_th, sec_fi, sec_tw, SECTORS_11,
            sec_v_fi=sec_v_fi, sec_v_tw=make_sec(50.0),
            rs_roc_5d=rs_roc, sec_stage4=sec_stage4,
        )
        return target

    def test_veto_blocks_stage4_low_volume(self):
        """Stage 4 sector with vol_div=12 (< 15) should be VETOED."""
        sec_stage4 = {s: False for s in SECTORS_11}
        sec_stage4["XLE"] = True
        target = self._make_satellite_scenario(sec_stage4, vol_div_value=12.0)
        # XLE should NOT appear as satellite (vetoed)
        assert target.get("XLE", 0.0) == 0.0

    def test_veto_overrides_stage4_high_volume(self):
        """Stage 4 sector with vol_div=20 (> 15) should OVERRIDE the veto."""
        sec_stage4 = {s: False for s in SECTORS_11}
        sec_stage4["XLE"] = True
        target = self._make_satellite_scenario(sec_stage4, vol_div_value=20.0)
        # XLE SHOULD appear as satellite (override)
        assert target.get("XLE", 0.0) > 0.0

    def test_no_veto_without_stage4_data(self):
        """Without sec_stage4 (None), no veto is applied (backward compatible)."""
        target = self._make_satellite_scenario(None, vol_div_value=12.0)
        # XLE should appear as satellite (no veto possible)
        assert target.get("XLE", 0.0) > 0.0

    def test_veto_at_exact_boundary_15(self):
        """vol_div exactly 15.0 should be VETOED (condition is <= 15.0)."""
        sec_stage4 = {s: False for s in SECTORS_11}
        sec_stage4["XLE"] = True
        target = self._make_satellite_scenario(sec_stage4, vol_div_value=15.0)
        assert target.get("XLE", 0.0) == 0.0

    def test_veto_override_at_15_01(self):
        """vol_div 15.01 should OVERRIDE the veto (> 15.0)."""
        sec_stage4 = {s: False for s in SECTORS_11}
        sec_stage4["XLE"] = True
        target = self._make_satellite_scenario(sec_stage4, vol_div_value=15.01)
        assert target.get("XLE", 0.0) > 0.0


# ── V32a & V33c Unit Tests ──────────────────────────────────


class TestV32aCrashExitLock:
    """Tests for V32a 3-day tactical exit lock in CRASH_SISTEMICO."""

    def test_crash_exit_blocked_on_day_2(self):
        """CRASH_SISTEMICO cannot exit on day 2 even if breadth is strong."""
        gate = QualityEntryGate()
        result = gate.evaluate_regime(
            th=30.0, fi=40.0, tw=50.0,
            v_th=50.0, v_fi=50.0, v_tw=50.0,
            sec_th=make_sec(30.0), sec_fi=make_sec(40.0), sec_tw=make_sec(50.0),
            fi_velocity=0.0, current_mode="CRASH_SISTEMICO", days_in_mode=2,
        )
        assert result == "CRASH_SISTEMICO"

    def test_crash_exit_allowed_on_day_3(self):
        """CRASH_SISTEMICO exits to RECUPERACION on day 3 when breadth confirms (and no defensive floor)."""
        gate = QualityEntryGate()
        sec_fi = make_sec(40.0)
        sec_fi["XLP"] = 20.0  # < 25 to prevent defensive floor trigger
        result = gate.evaluate_regime(
            th=30.0, fi=40.0, tw=50.0,
            v_th=50.0, v_fi=50.0, v_tw=50.0,
            sec_th=make_sec(30.0), sec_fi=sec_fi, sec_tw=make_sec(50.0),
            fi_velocity=0.0, current_mode="CRASH_SISTEMICO", days_in_mode=3,
        )
        assert result == "RECUPERACION"


class TestV33cHybridResilience:
    """Tests for V33c Hybrid Resilience weighting in RECUPERACION."""

    def test_recuperacion_hybrid_selection(self):
        """RECUPERACION selects Top 3 sectors by (rs_20d + 1) * sec_v_tw score."""
        gate = QualityEntryGate()
        rs_20d = {s: 0.0 for s in SECTORS_11}
        sec_v_tw = {s: 50.0 for s in SECTORS_11}

        # Give XLK, XLC, XLY high hybrid resilience
        rs_20d["XLK"] = 0.10; sec_v_tw["XLK"] = 80.0
        rs_20d["XLC"] = 0.08; sec_v_tw["XLC"] = 75.0
        rs_20d["XLY"] = 0.05; sec_v_tw["XLY"] = 70.0

        target = gate.calculate_target_weights(
            "RECUPERACION", make_sec(30.0), make_sec(30.0), make_sec(30.0), SECTORS_11,
            sec_v_tw=sec_v_tw, rs_roc_20d=rs_20d,
        )
        assert "XLK" in target
        assert "XLC" in target
        assert "XLY" in target
        assert sum(target.values()) == pytest.approx(1.0, abs=1e-3)


class TestV34NextGenIndicators:
    """Tests for V34 Next-Gen indicators integration."""

    def test_fgbi_reversal_exit_triggers_in_bull(self):
        """In structural bull market, FGBI reversal exits crash state on day 3."""
        gate = QualityEntryGate()
        # Mock historical FGBI window (peak > 20)
        gate.fgbi_window = [22.0, 22.0, 22.0]

        sec_fi = make_sec(30.0)
        sec_fi["XLP"] = 20.0  # prevent defensive floor trigger

        result = gate.evaluate_regime(
            th=50.0, fi=30.0, tw=20.0,
            v_th=50.0, v_fi=50.0, v_tw=40.0,
            sec_th=make_sec(30.0), sec_fi=sec_fi, sec_tw=make_sec(20.0),
            fi_velocity=0.0, current_mode="CRASH_SISTEMICO", days_in_mode=3,
            fgbi=14.0, vbi=1.0
        )
        assert result == "PISO_GENERACIONAL"

    def test_fgbi_reversal_exit_blocked_in_bear_without_vbi(self):
        """In structural bear market, FGBI reversal is blocked if VBI has no capitulation."""
        gate = QualityEntryGate()
        gate.fgbi_window = [22.0, 22.0, 22.0]

        sec_fi = make_sec(30.0)
        sec_fi["XLP"] = 20.0  # prevent defensive floor trigger

        result = gate.evaluate_regime(
            th=30.0, fi=30.0, tw=20.0,
            v_th=50.0, v_fi=50.0, v_tw=40.0,
            sec_th=make_sec(30.0), sec_fi=sec_fi, sec_tw=make_sec(20.0),
            fi_velocity=0.0, current_mode="CRASH_SISTEMICO", days_in_mode=3,
            fgbi=14.0, vbi=1.0
        )
        # Blocked: returns current mode
        assert result == "CRASH_SISTEMICO"

    def test_fgbi_reversal_exit_allowed_in_bear_with_vbi(self):
        """In structural bear market, FGBI reversal exits if VBI confirms panic (>1.5)."""
        gate = QualityEntryGate()
        gate.fgbi_window = [22.0, 22.0, 22.0]

        sec_fi = make_sec(30.0)
        sec_fi["XLP"] = 20.0  # prevent defensive floor trigger

        result = gate.evaluate_regime(
            th=30.0, fi=30.0, tw=20.0,
            v_th=50.0, v_fi=50.0, v_tw=40.0,
            sec_th=make_sec(30.0), sec_fi=sec_fi, sec_tw=make_sec(20.0),
            fi_velocity=0.0, current_mode="CRASH_SISTEMICO", days_in_mode=3,
            fgbi=14.0, vbi=1.8
        )
        assert result == "PISO_GENERACIONAL"

    def test_s5cap_extreme_divergence_penalty(self):
        """In RE_ACUMULACION_ALCISTA, a sector with extreme divergence (div > 25) gets a 0.5x weight penalty."""
        gate = QualityEntryGate()
        # All sectors have normal equal-weighted breadth (50) and cap-weighted breadth (50)
        sec_fi = make_sec(50.0)
        s5cap_fi = make_sec(50.0)

        # XLK has extreme divergence: equal-weighted = 50%, cap-weighted = 20% (div = 30)
        s5cap_fi["XLK"] = 20.0

        # Normal weights (baseline)
        target_normal = gate.calculate_target_weights(
            "RE_ACUMULACION_ALCISTA", make_sec(60.0), sec_fi, make_sec(50.0), SECTORS_11,
            s5cap_fi=None
        )

        # With V34 divergence penalty active
        target_v34 = gate.calculate_target_weights(
            "RE_ACUMULACION_ALCISTA", make_sec(60.0), sec_fi, make_sec(50.0), SECTORS_11,
            s5cap_fi=s5cap_fi
        )

        # XLK weight should be significantly lower in V34
        assert target_v34["XLK"] < target_normal["XLK"]


