"""
TEST SUITE: Entry Intelligence System
=======================================
Validates the full entry funnel:
  1. EventFlowIntelligence (Macro Calendar + Whale Flow)
  2. PricePhaseIntelligence (Price Phase Diagnosis)
  3. GammaAwareStop (Gamma-anchored, VIX-adaptive stops)
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta, UTC

# ── Modules under test ──
from backend.infrastructure.data_providers.event_flow_intelligence import (
    MacroEventCalendar, WhaleFlowReader, EventFlowIntelligence,
    MacroEvent, WhaleVerdict,
)
from backend.application.price_phase_intelligence import (
    PricePhaseIntelligence, EntryVerdict,
)
from backend.application.portfolio_intelligence import AdaptiveTrailingStop


# ═══════════════════════════════════════════════════════════════
# HELPERS: Generate synthetic price data
# ═══════════════════════════════════════════════════════════════

def _make_correction_prices(n=60, base=190, drop_pct=0.02):
    """Price rises gently, then corrects toward SMA20 with low volume."""
    close = [base]
    # Gentle uptrend for first 45 bars
    for i in range(1, 45):
        close.append(close[-1] * 1.002)
    # Then mixed sideways pullback for last 15 bars
    for i in range(45, n):
        if i % 5 in (0, 3):  # 2 of 5 green
            close.append(close[-1] * 1.0015)
        else:
            close.append(close[-1] * 0.9985)
    close = np.array(close)
    high = close * 1.003
    low = close * 0.997
    vol = np.ones(n) * 1_000_000
    # Key: only the last 10 bars are dry, so RVOL of last bar < 0.9
    vol[-10:] = 200_000  # 200K vs avg ~700K = RVOL ~0.3
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": vol})


def _make_breakout_prices(n=55, base=190):
    """Price consolidates then breaks out with volume (not too far from SMA)."""
    np.random.seed(42)
    # Flat consolidation for 50 bars
    close = np.full(50, base) + np.random.randn(50) * 0.2
    # Only 5 breakout bars: keeps dist_to_sma under 2.5 ATR
    for i in range(50, n):
        close = np.append(close, close[-1] * 1.003)
    high = close * 1.004
    low = close * 0.996
    vol = np.ones(n) * 500_000  # Normal volume = 500K
    vol[50:] = 2_000_000  # Breakout volume 4x = strong RVOL
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": vol})


def _make_exhaustion_prices(n=60, base=150):
    """Parabolic extension far above SMA20."""
    close = [base]
    for i in range(1, n):
        close.append(close[-1] * 1.015)  # +1.5% daily = parabolic
    close = np.array(close)
    high = close * 1.01
    low = close * 0.99
    vol = np.ones(n) * 1_000_000
    vol[-5:] *= 4  # Volume climax at the top
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": vol})


# ═══════════════════════════════════════════════════════════════
# TEST CLASS 1: Macro Event Calendar
# ═══════════════════════════════════════════════════════════════

class TestMacroEventCalendar:
    """Tests for the MacroEventCalendar."""

    def test_fomc_detection_april_2026(self):
        """Should detect the April 28-29 FOMC meeting."""
        cal = MacroEventCalendar()
        events = cal.get_upcoming_events(days_ahead=10, reference_date=date(2026, 4, 22))
        fomc_events = [e for e in events if e.name == "FOMC_DECISION"]
        assert len(fomc_events) >= 1
        assert fomc_events[0].event_date.date() == date(2026, 4, 29)
        assert fomc_events[0].impact_level == 1  # NUCLEAR

    def test_fomc_sep_flag(self):
        """FOMC with SEP (Jun, Sep, Dec) should have has_projections=True."""
        cal = MacroEventCalendar()
        events = cal.get_upcoming_events(days_ahead=5, reference_date=date(2026, 6, 14))
        fomc = [e for e in events if e.name == "FOMC_DECISION"]
        assert len(fomc) >= 1
        assert fomc[0].has_projections is True

    def test_nfp_estimation(self):
        """Should estimate NFP as first Friday of month."""
        cal = MacroEventCalendar()
        events = cal.get_upcoming_events(days_ahead=10, reference_date=date(2026, 5, 1))
        nfp = [e for e in events if e.name == "NFP"]
        assert len(nfp) >= 1
        assert nfp[0].event_date.weekday() == 4  # Friday

    def test_event_classification(self):
        """Should classify event impact levels correctly."""
        assert MacroEventCalendar._classify_event_impact("FOMC Interest Rate Decision") == 1
        assert MacroEventCalendar._classify_event_impact("CPI YoY") == 1
        assert MacroEventCalendar._classify_event_impact("Non-Farm Payrolls") == 1
        assert MacroEventCalendar._classify_event_impact("ISM Manufacturing PMI") == 2
        assert MacroEventCalendar._classify_event_impact("Retail Sales MoM") == 3
        assert MacroEventCalendar._classify_event_impact("Consumer Confidence") is None

    def test_no_duplicates(self):
        """Should not have duplicate events for the same name + date."""
        cal = MacroEventCalendar()
        events = cal.get_upcoming_events(days_ahead=10, reference_date=date(2026, 4, 22))
        keys = [(e.name, e.event_date.date()) for e in events]
        assert len(keys) == len(set(keys))


# ═══════════════════════════════════════════════════════════════
# TEST CLASS 2: Whale Flow Reader
# ═══════════════════════════════════════════════════════════════

class TestWhaleFlowReader:
    """Tests for the WhaleFlowReader verdicts."""

    def test_ride_the_whales(self):
        """Strong bullish flow should produce RIDE_THE_WHALES."""
        reader = WhaleFlowReader()
        v = reader.read_flow(
            spy_cum_delta=800_000,
            total_sweeps=15,
            sweep_call_pct=75,
            tide_direction="BULLISH",
            tide_accelerating=True,
            tide_net_premium=8_000_000,
            spy_confidence=0.85,
        )
        assert v.verdict == "RIDE_THE_WHALES"
        assert v.position_scale == 1.0

    def test_lean_with_flow(self):
        """Moderate bullish flow should produce LEAN_WITH_FLOW."""
        reader = WhaleFlowReader()
        v = reader.read_flow(
            spy_cum_delta=300_000,
            total_sweeps=6,
            sweep_call_pct=68,
            tide_direction="BULLISH",
            tide_accelerating=False,
            spy_confidence=0.6,
        )
        assert v.verdict == "LEAN_WITH_FLOW"
        assert v.position_scale == 0.70

    def test_uncertain_silent_flow(self):
        """Silent flow should produce UNCERTAIN."""
        reader = WhaleFlowReader()
        v = reader.read_flow(
            spy_cum_delta=10_000,
            total_sweeps=0,
            sweep_call_pct=50,
            tide_direction="NEUTRAL",
        )
        assert v.verdict == "UNCERTAIN"
        assert v.position_scale <= 0.60

    def test_am_pm_divergence_reduces_conviction(self):
        """AM/PM divergence should reduce conviction even with bullish flow."""
        reader = WhaleFlowReader()
        v = reader.read_flow(
            spy_cum_delta=300_000,
            am_pm_diverges=True,
            total_sweeps=8,
            sweep_call_pct=65,
        )
        # With divergence, even moderate flow shouldn't be RIDE_THE_WHALES
        assert v.am_pm_divergence is True
        assert v.verdict != "RIDE_THE_WHALES"

    def test_event_freeze_when_nuclear_imminent(self):
        """Should freeze stops when nuclear event is < 30 min away."""
        reader = WhaleFlowReader()
        event = MacroEvent(
            name="FOMC_DECISION",
            event_date=datetime.now(UTC) + timedelta(minutes=15),
            impact_level=1,
        )
        v = reader.read_flow(nearest_event=event, spy_cum_delta=100_000)
        assert v.freeze_stops is True
        assert v.freeze_duration_min == 30

    def test_no_freeze_when_event_far(self):
        """Should NOT freeze stops when event is > 30 min away."""
        reader = WhaleFlowReader()
        event = MacroEvent(
            name="FOMC_DECISION",
            event_date=datetime.now(UTC) + timedelta(hours=18),
            impact_level=1,
        )
        v = reader.read_flow(nearest_event=event)
        assert v.freeze_stops is False


# ═══════════════════════════════════════════════════════════════
# TEST CLASS 3: Price Phase Intelligence
# ═══════════════════════════════════════════════════════════════

class TestPricePhaseIntelligence:
    """Tests for the PricePhaseIntelligence diagnosis."""

    def test_correction_phase(self):
        """Gentle pullback with dry volume → CORRECTION."""
        ppi = PricePhaseIntelligence()
        prices = _make_correction_prices()
        v = ppi.diagnose("TEST", prices, put_wall=188.0, call_wall=200.0, gamma_regime="PIN")
        assert v.phase == "CORRECTION"
        assert v.rvol < 1.0  # Dry volume

    def test_breakout_phase(self):
        """New high with volume expansion → BREAKOUT."""
        ppi = PricePhaseIntelligence()
        prices = _make_breakout_prices()
        v = ppi.diagnose("TEST", prices, gamma_regime="SQUEEZE_UP")
        assert v.phase == "BREAKOUT"
        assert v.rvol >= 1.5

    def test_exhaustion_up_phase(self):
        """Parabolic extension → EXHAUSTION_UP / ABORT."""
        ppi = PricePhaseIntelligence()
        prices = _make_exhaustion_prices()
        v = ppi.diagnose("TEST", prices)
        assert v.phase == "EXHAUSTION_UP"
        assert v.verdict == "ABORT"

    def test_fire_requires_rr_minimum(self):
        """FIRE verdict requires R:R >= 3.0."""
        ppi = PricePhaseIntelligence()
        prices = _make_correction_prices()
        # Put wall very close to price → small risk → good R:R
        v = ppi.diagnose("TEST", prices, put_wall=188.0, call_wall=210.0,
                         gamma_regime="PIN", wyckoff_state="ACCUMULATION")
        if v.verdict == "FIRE":
            assert v.risk_reward_ratio >= 3.0

    def test_fire_requires_2_of_3_dimensions(self):
        """FIRE needs at least 2 of 3 dimensions confirming."""
        ppi = PricePhaseIntelligence()
        prices = _make_correction_prices()
        v = ppi.diagnose("TEST", prices, put_wall=188.0, call_wall=210.0,
                         gamma_regime="PIN", wyckoff_state="ACCUMULATION")
        if v.verdict == "FIRE":
            assert v.dimensions_confirming >= 2

    def test_entry_price_anchored_to_put_wall(self):
        """When near Put Wall, entry price should be near it."""
        ppi = PricePhaseIntelligence()
        prices = _make_correction_prices()
        current_price = float(prices['Close'].iloc[-1])
        put_wall = current_price * 0.99  # Very close to current price
        v = ppi.diagnose("TEST", prices, put_wall=put_wall, call_wall=current_price * 1.08)
        if v.entry_price > 0:
            # Entry should be very close to put_wall
            assert abs(v.entry_price - put_wall) / put_wall < 0.01

    def test_stop_below_put_wall(self):
        """Stop should be BELOW the Put Wall, not at it."""
        ppi = PricePhaseIntelligence()
        prices = _make_correction_prices()
        current_price = float(prices['Close'].iloc[-1])
        put_wall = current_price * 0.98
        v = ppi.diagnose("TEST", prices, put_wall=put_wall, call_wall=current_price * 1.08)
        if v.stop_price > 0 and v.put_wall > 0:
            assert v.stop_price < v.put_wall  # Stop is BELOW Put Wall


# ═══════════════════════════════════════════════════════════════
# TEST CLASS 4: Gamma-Aware Stop
# ═══════════════════════════════════════════════════════════════

class TestGammaAwareStop:
    """Tests for the V2 Gamma-aware AdaptiveTrailingStop."""

    def test_vix_scaling_normal(self):
        """VIX < 18 should not scale the multiplier."""
        ts = AdaptiveTrailingStop()
        stop_normal = ts.calculate_stop(200.0, 3.0, vix_current=15.0)
        stop_high = ts.calculate_stop(200.0, 3.0, vix_current=30.0)
        # High VIX should produce a LOWER stop (more room)
        assert stop_high < stop_normal

    def test_vix_extreme_doubles_atr(self):
        """VIX > 35 should roughly double the ATR multiplier."""
        ts = AdaptiveTrailingStop()
        stop_normal = ts.calculate_stop(200.0, 3.0, vix_current=15.0)
        stop_extreme = ts.calculate_stop(200.0, 3.0, vix_current=40.0)
        # With doubled multiplier, stop should be significantly lower
        assert stop_extreme < stop_normal - 3.0

    def test_put_wall_anchoring(self):
        """With Put Wall, stop should go below it (not at ATR level)."""
        ts = AdaptiveTrailingStop()
        stop_no_wall = ts.calculate_stop(200.0, 3.0)
        put_wall = 194.0  # Below price but above typical ATR stop
        stop_with_wall = ts.calculate_stop(200.0, 3.0, put_wall=put_wall)
        # Gamma stop = 194 - 0.3*3 = 193.1
        # This should be lower than the no-wall stop
        assert stop_with_wall <= stop_no_wall

    def test_put_wall_stop_is_below_wall(self):
        """Stop with Put Wall anchor should be BELOW the Put Wall."""
        ts = AdaptiveTrailingStop()
        put_wall = 194.0
        stop = ts.calculate_stop(200.0, 3.0, put_wall=put_wall)
        assert stop < put_wall

    def test_freeze_active(self):
        """Freeze should return True when active and within duration."""
        ts = AdaptiveTrailingStop()
        result = ts.should_freeze(
            freeze_stops=True,
            freeze_start_time=datetime.now(UTC) - timedelta(minutes=10),
            freeze_duration_min=30,
        )
        assert result is True

    def test_freeze_expired(self):
        """Freeze should return False after duration expires."""
        ts = AdaptiveTrailingStop()
        result = ts.should_freeze(
            freeze_stops=True,
            freeze_start_time=datetime.now(UTC) - timedelta(minutes=45),
            freeze_duration_min=30,
        )
        assert result is False

    def test_backward_compatibility(self):
        """Old API without new params should still work."""
        ts = AdaptiveTrailingStop()
        stop = ts.calculate_stop(200.0, 3.0, rs_vs_spy=1.1)
        assert stop > 0
        assert stop < 200.0
