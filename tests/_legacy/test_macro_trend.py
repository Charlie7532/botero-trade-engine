"""
Tests for IndicatorTrend and MacroTrendCalculator
"""
import pytest
from backend.modules.shared.domain.entities.indicator_trend import IndicatorTrend
from backend.modules.shared.domain.rules.macro_trend_calculator import (
    calculate_trend,
    calculate_breadth,
)


class TestCalculateTrend:
    """Test calculate_trend domain rule."""

    def test_empty_history(self):
        t = calculate_trend("VIX", [])
        assert t.name == "VIX"
        assert t.current == 0.0

    def test_single_point(self):
        t = calculate_trend("VIX", [("2026-01-01", 18.5)])
        assert t.current == 18.5

    def test_basic_rising(self):
        history = [
            ("2026-01-01", 15.0),
            ("2026-01-02", 16.0),
            ("2026-01-03", 17.0),
            ("2026-01-04", 18.0),
            ("2026-01-05", 19.0),
        ]
        t = calculate_trend("VIX", history)
        assert t.current == 19.0
        assert t.previous == 18.0
        assert t.delta_1d == 1.0
        assert t.direction == "RISING"
        assert t.ma5 == pytest.approx(17.0, abs=0.01)

    def test_basic_falling(self):
        history = [
            ("2026-01-01", 25.0),
            ("2026-01-02", 23.0),
            ("2026-01-03", 21.0),
            ("2026-01-04", 19.0),
            ("2026-01-05", 17.0),
        ]
        t = calculate_trend("VIX", history)
        assert t.direction == "FALLING"
        assert t.delta_1d == -2.0

    def test_flat_direction(self):
        history = [
            ("2026-01-01", 20.0),
            ("2026-01-02", 20.01),
            ("2026-01-03", 19.99),
            ("2026-01-04", 20.0),
            ("2026-01-05", 20.0),
        ]
        t = calculate_trend("VIX", history)
        assert t.direction == "FLAT"

    def test_percentile_extreme(self):
        # Current value at the top of 90-day range
        history = [(f"2026-01-{i+1:02d}", float(i)) for i in range(1, 31)]
        t = calculate_trend("TEST", history)
        assert t.percentile_90d >= 90.0  # 30/30 = 100th percentile

    def test_percentile_bottom(self):
        # Current at the bottom
        history = [(f"2026-01-{i+1:02d}", 30.0 - float(i)) for i in range(30)]
        t = calculate_trend("TEST", history)
        # Last value is smallest
        assert t.percentile_90d <= 10.0

    def test_ma20_with_enough_data(self):
        history = [(f"2026-01-{i+1:02d}", 20.0 + i * 0.5) for i in range(25)]
        t = calculate_trend("VIX", history)
        assert t.ma20 > 0
        assert t.ma5 > t.ma20  # Rising trend

    def test_trend_bullish_bearish(self):
        # MA5 above MA20 → BULLISH
        history = [(f"2026-01-{i+1:02d}", 10.0 + i * 1.0) for i in range(25)]
        t = calculate_trend("TEST", history)
        assert t.trend == "BULLISH"

    def test_days_of_trend_consecutive(self):
        history = [
            ("2026-01-01", 10.0),
            ("2026-01-02", 11.0),
            ("2026-01-03", 12.0),
            ("2026-01-04", 13.0),
            ("2026-01-05", 14.0),
        ]
        t = calculate_trend("TEST", history)
        assert t.days_of_trend >= 3


class TestCalculateBreadth:
    """Test calculate_breadth (S5TH/S5TW)."""

    def test_all_above_ma(self):
        # All tickers closing above their 20-day MA
        all_closes = {
            "AAPL": [100 + i for i in range(25)],
            "MSFT": [200 + i for i in range(25)],
            "GOOG": [150 + i for i in range(25)],
        }
        result = calculate_breadth(all_closes, ma_length=20)
        assert result == 100.0

    def test_none_above_ma(self):
        # All tickers closing below their 20-day MA (declining)
        all_closes = {
            "AAPL": [100 - i for i in range(25)],
            "MSFT": [200 - i for i in range(25)],
            "GOOG": [150 - i for i in range(25)],
        }
        result = calculate_breadth(all_closes, ma_length=20)
        assert result == 0.0

    def test_mixed_breadth(self):
        all_closes = {
            "AAPL": [100 + i for i in range(25)],      # Above MA → counted
            "MSFT": [200 - i for i in range(25)],      # Below MA → not counted
        }
        result = calculate_breadth(all_closes, ma_length=20)
        assert result == 50.0

    def test_insufficient_data(self):
        # Less than MA length → skipped
        all_closes = {
            "AAPL": [100, 101, 102],
        }
        result = calculate_breadth(all_closes, ma_length=200)
        assert result is None

    def test_s5th_requires_200_days(self):
        # Exactly 200 days of flat data → at MA → not above
        all_closes = {
            "AAPL": [100.0] * 200,
        }
        # close == MA → not strictly above
        result = calculate_breadth(all_closes, ma_length=200)
        assert result == 0.0


class TestMarketRegimeSignals:
    """Test research signals (SIG-003, SIG-001)."""

    def test_mm_dominance(self):
        from backend.modules.price_analysis.domain.rules.market_regime_signals import (
            classify_mm_dominance,
        )
        # Small trades for 3 days
        result = classify_mm_dominance([90, 95, 100])
        assert result["regime"] == "MM_DOMINANT"

    def test_institutional_trades(self):
        from backend.modules.price_analysis.domain.rules.market_regime_signals import (
            classify_mm_dominance,
        )
        result = classify_mm_dominance([300, 280, 310])
        assert result["regime"] == "INSTITUTIONAL"

    def test_breakout_energy(self):
        from backend.modules.price_analysis.domain.rules.market_regime_signals import (
            classify_mm_dominance,
        )
        # 3 days MM then institutional spike
        result = classify_mm_dominance([90, 95, 100, 250])
        assert result["breakout_energy"] is True

    def test_force_confluence_melt_up(self):
        from backend.modules.price_analysis.domain.rules.market_regime_signals import (
            classify_force_confluence,
        )
        result = classify_force_confluence("DRIFT", True, "BUYING")
        assert result == "MELT_UP"

    def test_force_confluence_melt_down(self):
        from backend.modules.price_analysis.domain.rules.market_regime_signals import (
            classify_force_confluence,
        )
        result = classify_force_confluence("DRIFT", True, "SELLING")
        assert result == "MELT_DOWN"

    def test_force_confluence_none_in_pin(self):
        from backend.modules.price_analysis.domain.rules.market_regime_signals import (
            classify_force_confluence,
        )
        # PIN regime → no confluence even with vanna event
        result = classify_force_confluence("PIN", True, "BUYING")
        assert result == "NONE"


class TestGEXTrailingStop:
    """Test GEX regime adaptation in AdaptiveTrailingStop."""

    def test_pin_regime_tighter_stop(self):
        from backend.modules.execution.domain.rules.exit_rules import AdaptiveTrailingStop
        ts = AdaptiveTrailingStop()
        # Use small ATR so the stop is driven by ATR, not clamped to fixed ceiling
        stop_normal = ts.calculate_stop(100.0, 1.0)
        stop_pin = ts.calculate_stop(100.0, 1.0, gex_regime="PIN")
        # PIN multiplier 0.75 → smaller ATR trail → higher (tighter) stop
        assert stop_pin >= stop_normal

    def test_drift_regime_wider_stop(self):
        from backend.modules.execution.domain.rules.exit_rules import AdaptiveTrailingStop
        ts = AdaptiveTrailingStop()
        stop_normal = ts.calculate_stop(100.0, 2.0)
        stop_drift = ts.calculate_stop(100.0, 2.0, gex_regime="DRIFT")
        # DRIFT should give a lower (wider) stop
        assert stop_drift < stop_normal
