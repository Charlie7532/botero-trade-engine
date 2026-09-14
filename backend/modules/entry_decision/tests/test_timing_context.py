"""Tests for timing_context.py — TimingContext loading and properties.

Covers:
1. All 11 stations have timing stores that load correctly
2. TimingSlot and FirstPassage parsing
3. has_timing_signal property
4. Missing state/station returns None
5. to_dict serialization
"""
import pytest

from backend.modules.entry_decision.domain.rules.timing_context import (
    get_timing_context,
    TimingContext,
    TimingSlot,
    FirstPassage,
    _load_timing_store,
)


STATIONS = [
    "vix", "vvix", "bsi", "fg", "pcr", "skew", "credit",
    "yield_curve", "rotation", "sv5_turbulence", "dxy",
]

# Known high-N state that exists in all stores (central D1, central D2, central D3)
COMMON_STATE = "2__2__2"


class TestTimingContextLoading:
    def test_all_11_stations_have_timing_stores(self):
        """All 11 METAR stations must have timing_fact_store JSON files."""
        for station in STATIONS:
            store = _load_timing_store(station)
            assert store is not None, f"No timing store for {station}"
            assert "states" in store, f"No 'states' key in {station} timing store"

    def test_all_11_stations_load_common_state(self):
        """State 2__2__2 must exist in all 11 timing stores."""
        for station in STATIONS:
            tc = get_timing_context(station, COMMON_STATE)
            assert tc is not None, f"No timing context for {station} state {COMMON_STATE}"
            assert tc.station == station
            assert tc.state_key == COMMON_STATE
            assert tc.n_barras > 0

    def test_missing_state_returns_none(self):
        """Non-existent state_key returns None, not exception."""
        tc = get_timing_context("vix", "99__99__99")
        assert tc is None

    def test_missing_station_returns_none(self):
        """Non-existent station returns None, not exception."""
        tc = get_timing_context("nonexistent_station", COMMON_STATE)
        assert tc is None


class TestTimingContextProperties:
    def test_floor_temporal_spread(self):
        """VIX 2__2__2 must have positive floor temporal spread."""
        tc = get_timing_context("vix", COMMON_STATE)
        spread = tc.floor_temporal_spread
        assert spread is not None
        assert spread > 0.005, f"Expected floor spread > 0.5%, got {spread:.5f}"

    def test_ceiling_temporal_spread(self):
        """VIX 2__2__2 must have positive ceiling temporal spread."""
        tc = get_timing_context("vix", COMMON_STATE)
        spread = tc.ceiling_temporal_spread
        assert spread is not None
        assert spread > 0.005, f"Expected ceiling spread > 0.5%, got {spread:.5f}"

    def test_has_timing_signal_strong_state(self):
        """Common state in VIX has timing signal."""
        tc = get_timing_context("vix", COMMON_STATE)
        assert tc.has_timing_signal is True

    def test_floor_slots_structure(self):
        """Floor slots must have t=0 and ENTRE."""
        tc = get_timing_context("vix", COMMON_STATE)
        assert "t=0" in tc.floor_slots
        assert "ENTRE" in tc.floor_slots
        t0 = tc.floor_slots["t=0"]
        assert isinstance(t0, TimingSlot)
        assert t0.slot == "t=0"
        assert t0.n >= 0

    def test_first_passage_present(self):
        """First passage zz75 must be present for well-populated states."""
        tc = get_timing_context("vix", COMMON_STATE)
        fp = tc.first_passage_zz75_floor
        assert fp is not None
        assert isinstance(fp, FirstPassage)
        assert fp.scale == "zz75"
        assert fp.hit_rate > 0
        assert fp.bars_medio > 0

    def test_demographics(self):
        """Demographics fields must be populated."""
        tc = get_timing_context("vix", COMMON_STATE)
        assert tc.n_barras > 100
        assert tc.fire_rate_pct > 0
        assert tc.n_episodios > 0
        assert tc.duracion_media > 0


class TestTimingContextSerialization:
    def test_to_dict_has_required_keys(self):
        """to_dict must include key temporal fields."""
        tc = get_timing_context("vix", COMMON_STATE)
        d = tc.to_dict()
        assert "station" in d
        assert "state_key" in d
        assert "floor_temporal_spread_ev" in d
        assert "ceiling_temporal_spread_ev" in d
        assert "n_barras" in d
        assert "duracion_media" in d

    def test_to_dict_first_passage(self):
        """to_dict must include first passage quality metrics."""
        tc = get_timing_context("vix", COMMON_STATE)
        d = tc.to_dict()
        assert "fp_floor_zz75" in d
        fp = d["fp_floor_zz75"]
        assert "profit_factor" in fp
        assert "p_value" in fp
        assert "mae_medio" in fp


class TestTimingContextAllStations:
    @pytest.mark.parametrize("station", STATIONS)
    def test_station_timing_signal_consistent(self, station):
        """All 11 stations must have consistent timing signal in their common state."""
        tc = get_timing_context(station, COMMON_STATE)
        assert tc is not None
        # All stations showed STRONG signal in analysis
        assert tc.floor_slots.get("t=0") is not None
        assert tc.floor_slots.get("ENTRE") is not None
        assert tc.ceiling_slots.get("t=0") is not None
        assert tc.ceiling_slots.get("ENTRE") is not None
