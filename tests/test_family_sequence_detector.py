"""Tests for family_sequence_detector — Pure Domain Rules."""
import pytest
from backend.modules.entry_decision.domain.rules.family_sequence_detector import (
    detect_family_sequence,
    _classify_station,
    _detect_phase,
    Category,
    STATION_CATEGORIES,
    StationFloorCeiling,
    FamilySequenceReport,
)


# ── Helper: Build mock station_summaries ─────────────────────────────────

def _make_summary(d1: int, d2: int, d3: int = 2, kinematic: dict = None) -> dict:
    """Build a minimal station summary dict."""
    s = {
        "state_key": f"{d1}__{d2}__{d3}",
        "d1_bin_numeric": d1,
        "d2_bin_numeric": d2,
    }
    if kinematic:
        s["zigzag_kinematic"] = kinematic
    return s


def _crisis_summaries():
    """All stations in extreme stress, VIX D2 building."""
    return {
        "vix":             _make_summary(5, 4),  # EXTREME_PANIC + FAST_SPIKE
        "vvix":            _make_summary(5, 3),
        "pcr":             _make_summary(5, 3),
        "skew":            _make_summary(4, 3),
        "credit":          _make_summary(0, 1),  # EXTREME stress (low = stress)
        "yield_curve":     _make_summary(0, 1),
        "dxy":             _make_summary(5, 4),
        "bsi":             _make_summary(0, 1),  # Weak breadth
        "sv5_turbulence":  _make_summary(5, 4),
        "fg":              _make_summary(0, 1),  # Extreme fear
    }


def _neutral_summaries():
    """All stations in neutral territory."""
    return {
        "vix":             _make_summary(2, 2),
        "vvix":            _make_summary(3, 2),
        "pcr":             _make_summary(2, 2),
        "skew":            _make_summary(3, 2),
        "credit":          _make_summary(3, 2),
        "yield_curve":     _make_summary(3, 2),
        "dxy":             _make_summary(2, 2),
        "bsi":             _make_summary(3, 2),
        "sv5_turbulence":  _make_summary(2, 2),
        "fg":              _make_summary(3, 2),
    }


# ── Phase Detection Tests ────────────────────────────────────────────────

class TestPhaseDetection:
    """Test causal phase detection from category ratios."""

    def test_capitulation_building_with_vix_d2_up(self):
        """All three categories stressed + VIX D2 building → CAPITULATION_BUILDING."""
        report = detect_family_sequence(_crisis_summaries())
        assert report.phase == "CAPITULATION_BUILDING"
        assert report.vix_d2_building is True
        assert report.cat1_stress_ratio >= 0.50
        assert report.cat2_fear_ratio >= 0.50
        assert report.cat3_capitulation_ratio >= 0.50

    def test_capitulation_resolving_with_vix_d2_down(self):
        """All stressed but VIX D2 resolving → CAPITULATION_RESOLVING."""
        sums = _crisis_summaries()
        sums["vix"] = _make_summary(5, 1)  # D2=1 → resolving
        report = detect_family_sequence(sums)
        assert report.phase == "CAPITULATION_RESOLVING"
        assert report.vix_d2_building is False

    def test_volatility_accelerating(self):
        """CAT1 + CAT2 stressed, CAT3 neutral → VOLATILITY_ACCELERATING."""
        sums = _crisis_summaries()
        # Neutralize CAT3 stations (bsi, sv5_turbulence, fg)
        sums["bsi"] = _make_summary(3, 2)
        sums["sv5_turbulence"] = _make_summary(2, 2)
        sums["fg"] = _make_summary(3, 2)
        report = detect_family_sequence(sums)
        assert report.phase == "VOLATILITY_ACCELERATING"

    def test_macro_precursor(self):
        """Only CAT1 stressed → MACRO_PRECURSOR."""
        sums = _neutral_summaries()
        sums["credit"] = _make_summary(0, 1)
        sums["yield_curve"] = _make_summary(0, 1)
        sums["dxy"] = _make_summary(5, 4)
        report = detect_family_sequence(sums)
        assert report.phase == "MACRO_PRECURSOR"

    def test_neutral_all_normal(self):
        """All neutral → NEUTRAL."""
        report = detect_family_sequence(_neutral_summaries())
        assert report.phase == "NEUTRAL"
        assert report.cat1_stress_ratio == 0.0
        assert report.cat2_fear_ratio == 0.0
        assert report.cat3_capitulation_ratio == 0.0

    def test_complacent_distribution(self):
        """CAT1 + CAT2 complacent → COMPLACENT_DISTRIBUTION."""
        sums = {
            "vix":             _make_summary(0, 1),  # Complacent (bins 0,1)
            "vvix":            _make_summary(0, 1),
            "pcr":             _make_summary(0, 2),
            "skew":            _make_summary(1, 2),
            "credit":          _make_summary(5, 3),  # Complacent for credit (bins 4,5)
            "yield_curve":     _make_summary(4, 3),
            "dxy":             _make_summary(0, 1),  # Complacent (bins 0,1)
            "bsi":             _make_summary(3, 2),  # Neutral
            "sv5_turbulence":  _make_summary(2, 2),
            "fg":              _make_summary(3, 2),
        }
        report = detect_family_sequence(sums)
        assert report.phase == "COMPLACENT_DISTRIBUTION"


# ── Station Classification Tests ─────────────────────────────────────────

class TestStationClassification:
    """Test per-station floor/ceiling classification."""

    def test_vix_in_panic_with_momentum(self):
        """VIX at D1=5 (EXTREME_PANIC) with structural momentum data."""
        kinematic = {
            "zz25": {
                "structural_momentum": {
                    "up_legs": {"p_continuation": 0.60, "ev_structural_pct": 2.1},
                    "down_legs": {"p_continuation": 0.45, "ev_structural_pct": -1.5},
                }
            }
        }
        sfc = _classify_station("vix", d1_bin=5, d2_bin=3, kinematic_data=kinematic)
        assert sfc.floor_type == "STRUCTURAL"  # P(HL)=0.60 > 0.55
        assert sfc.timing_mode == "ANTICIPATION"  # D2=3 (stress accelerating)

    def test_fg_in_extreme_fear_trap(self):
        """FG at D1=0 (EXTREME_FEAR) with low P(HL) → TRAP."""
        kinematic = {
            "zz25": {
                "structural_momentum": {
                    "up_legs": {"p_continuation": 0.40, "ev_structural_pct": 0.5},
                    "down_legs": {"p_continuation": 0.55, "ev_structural_pct": -2.0},
                }
            }
        }
        sfc = _classify_station("fg", d1_bin=0, d2_bin=1, kinematic_data=kinematic)
        assert sfc.floor_type == "TRAP"  # P(HL)=0.40 < 0.45

    def test_bsi_complacent_ceiling_hh(self):
        """BSI at D1=5 (complacent) with P(HH)>0.55 → ceiling TRAP (Regla de Oro)."""
        kinematic = {
            "zz25": {
                "structural_momentum": {
                    "up_legs": {"p_continuation": 0.55, "ev_structural_pct": 1.5},
                    "down_legs": {"p_continuation": 0.60, "ev_structural_pct": -1.8},
                }
            }
        }
        sfc = _classify_station("bsi", d1_bin=5, d2_bin=3, kinematic_data=kinematic)
        assert sfc.ceiling_type == "TRAP"  # P(HH)=0.60 > 0.55 → Regla de Oro

    def test_neutral_station_no_floor_ceiling(self):
        """Station at neutral D1 → no floor/ceiling classification."""
        sfc = _classify_station("vix", d1_bin=2, d2_bin=2)
        assert sfc.floor_type is None
        assert sfc.ceiling_type is None
        assert sfc.timing_mode == "NEUTRAL"


# ── Regla de Oro Tests ───────────────────────────────────────────────────

class TestReglaDeOro:
    """Test structural momentum signals (HH exit amplify, LL trap veto)."""

    def test_hh_exit_amplify(self):
        """At least one station with ceiling TRAP + P(HH)>0.55 → hh_exit_amplify=True."""
        sums = _neutral_summaries()
        sums["bsi"] = _make_summary(5, 3, kinematic={
            "zz25": {
                "structural_momentum": {
                    "up_legs": {"p_continuation": 0.55, "ev_structural_pct": 1.5},
                    "down_legs": {"p_continuation": 0.60, "ev_structural_pct": -1.8},
                }
            }
        })
        report = detect_family_sequence(sums)
        assert report.hh_exit_amplify is True

    def test_no_hh_exit_amplify_when_neutral(self):
        """No stations with ceiling TRAP → hh_exit_amplify=False."""
        report = detect_family_sequence(_neutral_summaries())
        assert report.hh_exit_amplify is False


# ── Category Assignment Tests ────────────────────────────────────────────

class TestCategoryAssignment:
    """Verify all stations are correctly categorized."""

    def test_all_stations_mapped(self):
        assert len(STATION_CATEGORIES) == 10

    def test_cat1_stations(self):
        cat1 = [s for s, c in STATION_CATEGORIES.items() if c == Category.CAT1_MACRO]
        assert set(cat1) == {"credit", "yield_curve", "dxy"}

    def test_cat2_stations(self):
        cat2 = [s for s, c in STATION_CATEGORIES.items() if c == Category.CAT2_SENTIMENT]
        assert set(cat2) == {"vix", "vvix", "pcr", "skew"}

    def test_cat3_stations(self):
        cat3 = [s for s, c in STATION_CATEGORIES.items() if c == Category.CAT3_ACTION]
        assert set(cat3) == {"bsi", "sv5_turbulence", "fg"}


# ── Report Serialization Tests ───────────────────────────────────────────

class TestReportSerialization:
    """Test to_dict produces valid output."""

    def test_to_dict_has_required_fields(self):
        report = detect_family_sequence(_neutral_summaries())
        d = report.to_dict()
        assert "cat1_stress_ratio" in d
        assert "cat2_fear_ratio" in d
        assert "cat3_capitulation_ratio" in d
        assert "phase" in d
        assert "vix_d2_building" in d
        assert "hh_exit_amplify" in d

    def test_state_key_fallback(self):
        """Test that state_key parsing works when d1_bin_numeric is not provided."""
        sums = {"vix": {"state_key": "4__3__2"}}
        report = detect_family_sequence(sums)
        assert report.n_cat2_active == 1
