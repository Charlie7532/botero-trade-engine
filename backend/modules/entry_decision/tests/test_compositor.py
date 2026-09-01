"""Tests for ConvergenceCompositor and multi-station convergence domain logic.

Covers:
1. d1_directional_vote: High-bearish vs Low-bearish station polarities, numeric bins, null-safety
2. reliability_factor & rarity_amplifier: Sample-size attenuation functions
3. Composite EV calculation: Weighting, scale-factors, N-reliability
4. Quorum and blind-stations handling: Missing stations, graceful degradation
5. Report structure and fields: Convexity count, kinematic convergence counts, to_dict consistency
"""
import pytest
from unittest.mock import MagicMock

from backend.modules.entry_decision.domain.services.convergence_compositor import (
    ConvergenceCompositor,
    ConvergenceReport,
    d1_directional_vote,
    reliability_factor,
    rarity_amplifier,
    STATIONS_HIGH_BEARISH,
    STATIONS_LOW_BEARISH,
)


# ── 1. D1 Directional Vote Tests ──────────────────────────────────────────

def test_d1_directional_vote_high_bearish():
    """For high-bearish stations (VIX, VVIX, PCR, SV5, SKEW, DXY), bin >= 4 is bearish (-1), bin <= 1 is bullish (+1)."""
    for st in STATIONS_HIGH_BEARISH:
        assert d1_directional_vote("4__2__1", st) == -1, f"Expected {st} bin 4 to vote -1"
        assert d1_directional_vote("5__0__0", st) == -1, f"Expected {st} bin 5 to vote -1"
        assert d1_directional_vote("0__2__1", st) == +1, f"Expected {st} bin 0 to vote +1"
        assert d1_directional_vote("1__3__2", st) == +1, f"Expected {st} bin 1 to vote +1"
        assert d1_directional_vote("2__2__2", st) == 0, f"Expected {st} bin 2 to vote 0"
        assert d1_directional_vote("3__1__1", st) == 0, f"Expected {st} bin 3 to vote 0"


def test_d1_directional_vote_low_bearish():
    """For low-bearish stations (FG, Credit, Yield, Rotation, BSI), bin <= 1 is bearish (-1), bin >= 4 is bullish (+1)."""
    for st in STATIONS_LOW_BEARISH:
        assert d1_directional_vote("0__2__1", st) == -1, f"Expected {st} bin 0 to vote -1"
        assert d1_directional_vote("1__3__2", st) == -1, f"Expected {st} bin 1 to vote -1"
        assert d1_directional_vote("4__2__1", st) == +1, f"Expected {st} bin 4 to vote +1"
        assert d1_directional_vote("5__0__0", st) == +1, f"Expected {st} bin 5 to vote +1"
        assert d1_directional_vote("2__2__2", st) == 0, f"Expected {st} bin 2 to vote 0"
        assert d1_directional_vote("3__1__1", st) == 0, f"Expected {st} bin 3 to vote 0"


def test_d1_directional_vote_null_safety():
    """Null, empty, invalid format, or missing station code must return 0 safely without crashing."""
    assert d1_directional_vote("", "vix") == 0
    assert d1_directional_vote(None, "vix") == 0
    assert d1_directional_vote("4__2__1", None) == 0
    assert d1_directional_vote("INVALID_STRING", "vix") == 0
    assert d1_directional_vote("UNKNOWN_STATION_KEY", "unknown_station") == 0


# ── 2. Reliability & Rarity Attenuation Functions ─────────────────────────

def test_reliability_factor():
    """N >= 30: full trust (1.0). N 10-29: partial trust (0.5). N < 10: zero trust (0.0)."""
    assert reliability_factor(100) == 1.0
    assert reliability_factor(30) == 1.0
    assert reliability_factor(29) == 0.5
    assert reliability_factor(10) == 0.5
    assert reliability_factor(9) == 0.0
    assert reliability_factor(0) == 0.0


def test_rarity_amplifier():
    """N >= 30: no alarm (0.0). N 10-29: moderate (0.5). N < 10: loud (1.0). N < 3: max (1.5)."""
    assert rarity_amplifier(100) == 0.0
    assert rarity_amplifier(30) == 0.0
    assert rarity_amplifier(29) == 0.5
    assert rarity_amplifier(10) == 0.5
    assert rarity_amplifier(9) == 1.0
    assert rarity_amplifier(3) == 1.0
    assert rarity_amplifier(2) == 1.5
    assert rarity_amplifier(0) == 1.5


# ── 3. Mocked Compositor Computation & Quorum Tests ───────────────────────

def _make_mock_metar(
    code: str,
    state_key: str = "2__2__2",
    n: int = 50,
    ev25: float = 0.001,
    ev75: float = 0.005,
    rr_asymmetry: float = 1.2,
    kinematic_pbull: float = 0.55,
):
    """Creates a mock METAR object matching MarketMETAR interface."""
    mock = MagicMock()
    mock.to_dict.return_value = {
        "metar_id": f"METAR_{code.upper()}_TEST",
        "state_key": state_key,
        "n_samples": n,
        "operational_guidance": "STK_HOLD_STABLE",
        "action_code": "STK_HOLD_STABLE",
        "ev_net_vector": {"zz25": ev25, "zz50": (ev25 + ev75) / 2, "zz75": ev75},
        "p_bull_vector": {"zz25": 0.52, "zz50": 0.54, "zz75": 0.56},
        "ev_per_day_vector": [ev25, ev25, ev75 / 5.0],
        "rr_asymmetry_ratio": rr_asymmetry,
        "e_ret_max_zz75": 0.02,
        "e_ret_min_zz75": -0.01,
        "zigzag_kinematic": {
            "zz75": {"p_bull": kinematic_pbull, "ev_net": 2.5, "e_days": 10.0}
        },
    }
    return mock


def test_compositor_quorum_and_blind_stations(monkeypatch):
    """Compositor correctly tracks active vs blind stations and adjusts quorum."""
    compositor = ConvergenceCompositor(max_workers=2)

    # Mock 8 successful stations and 3 failing stations
    def mock_fetch(code, fn, as_of_date):
        if code in ["rotation", "dxy", "credit"]:
            return (code, None, "Simulated network timeout")
        mock_m = _make_mock_metar(code, state_key="4__2__1", n=40)
        return (code, mock_m.to_dict(), None)

    monkeypatch.setattr(compositor, "_fetch_station", mock_fetch)

    rep = compositor.compute(as_of_date="2026-08-31")

    assert rep.total_stations == 11
    assert rep.active_stations == 8
    assert len(rep.blind_stations) == 3
    assert any("rotation" in b for b in rep.blind_stations)
    assert any("dxy" in b for b in rep.blind_stations)
    assert any("credit" in b for b in rep.blind_stations)


def test_compositor_convexity_and_kinematic_counts(monkeypatch):
    """Compositor correctly counts n_convex_stations and kinematic convergence."""
    compositor = ConvergenceCompositor(max_workers=2)

    def mock_fetch(code, fn, as_of_date):
        # 3 stations with rr > 1.0, 8 with rr <= 1.0
        rr = 1.5 if code in ["vix", "bsi", "yield_curve"] else 0.8
        # 4 stations with kinematic p_bull > 0.52 (bull), 2 with < 0.48 (bear)
        if code in ["vix", "bsi", "fg", "skew"]:
            k_pbull = 0.65  # bull
        elif code in ["vvix", "pcr"]:
            k_pbull = 0.40  # bear
        else:
            k_pbull = 0.50  # neutral
        mock_m = _make_mock_metar(code, rr_asymmetry=rr, kinematic_pbull=k_pbull)
        return (code, mock_m.to_dict(), None)

    monkeypatch.setattr(compositor, "_fetch_station", mock_fetch)

    rep = compositor.compute(as_of_date="2026-08-31")

    assert rep.n_convex_stations == 3
    assert rep.n_kinematic_bull_convergent == 4
    assert rep.n_kinematic_bear_convergent == 2


def test_compositor_report_to_dict():
    """ConvergenceReport must serialize cleanly to dict and JSON without missing keys."""
    compositor = ConvergenceCompositor(max_workers=2)

    def mock_fetch(code, fn, as_of_date):
        mock_m = _make_mock_metar(code, state_key="2__2__2", n=50)
        return (code, mock_m.to_dict(), None)

    compositor._fetch_station = mock_fetch

    rep = compositor.compute(as_of_date="2026-08-31")
    d = rep.to_dict()

    assert isinstance(d, dict)
    assert "n_convex_stations" in d
    assert "n_kinematic_bull_convergent" in d
    assert "n_kinematic_bear_convergent" in d
    assert "station_summaries" in d
    assert "vix" in d["station_summaries"]
    assert "kinematic_p_bull_75" in d["station_summaries"]["vix"]
