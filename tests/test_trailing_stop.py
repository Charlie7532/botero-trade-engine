"""
Tests for AdaptiveTrailingStop — Regime-adaptive stop loss.

Tests verify:
- Stop calculation in strong trend (RS > 1.05)
- Stop calculation in weak trend (RS < 0.95)
- Stop floor and ceiling enforcement
- ATR vs fixed % interaction
"""
import pytest
from backend.application.portfolio_intelligence import AdaptiveTrailingStop


class TestAdaptiveTrailingStop:

    def test_strong_trend_uses_wide_multiplier(self, trailing_stop):
        """In strong trend (RS > 1.05), should use 3.0× ATR."""
        stop = trailing_stop.calculate_stop(
            highest_since_entry=100.0,
            current_atr=2.0,
            rs_vs_spy=1.10,  # strong trend
        )
        # ATR stop = 100 - (3.0 × 2.0) = 94.0
        # Fixed ceiling = 100 × 0.88 = 88.0
        # Fixed floor = 100 × 0.95 = 95.0
        # max(94.0, 88.0) = 94.0, min(94.0, 95.0) = 94.0
        assert stop == 94.0

    def test_weak_trend_uses_tight_multiplier(self, trailing_stop):
        """In weak trend (RS < 0.95), should use 2.0× ATR."""
        stop = trailing_stop.calculate_stop(
            highest_since_entry=100.0,
            current_atr=2.0,
            rs_vs_spy=0.90,  # weak
        )
        # ATR stop = 100 - (2.0 × 2.0) = 96.0
        # Fixed floor = 95.0
        # max(96.0, 88.0) = 96.0, min(96.0, 95.0) = 95.0
        assert stop == 95.0  # capped by floor

    def test_neutral_uses_average_multiplier(self, trailing_stop):
        """Neutral RS should use average of trend and chop multipliers."""
        stop = trailing_stop.calculate_stop(
            highest_since_entry=100.0,
            current_atr=2.0,
            rs_vs_spy=1.00,  # neutral
        )
        # avg mult = (3.0 + 2.0) / 2 = 2.5
        # ATR stop = 100 - (2.5 × 2.0) = 95.0
        # max(95.0, 88.0) = 95.0, min(95.0, 95.0) = 95.0
        assert stop == 95.0

    def test_ceiling_prevents_catastrophic_loss(self, trailing_stop):
        """Fixed ceiling (12%) prevents stops from being too wide."""
        stop = trailing_stop.calculate_stop(
            highest_since_entry=100.0,
            current_atr=10.0,  # very high ATR
            rs_vs_spy=1.10,
        )
        # ATR stop = 100 - (3.0 × 10.0) = 70.0
        # Fixed ceiling = 88.0
        # max(70.0, 88.0) = 88.0
        assert stop >= 88.0  # ceiling protects

    def test_floor_prevents_premature_exit(self, trailing_stop):
        """Fixed floor (5%) prevents stops from being too tight."""
        stop = trailing_stop.calculate_stop(
            highest_since_entry=100.0,
            current_atr=0.5,  # very low ATR
            rs_vs_spy=0.90,
        )
        # ATR stop = 100 - (2.0 × 0.5) = 99.0 (too tight!)
        # Fixed floor = 95.0
        # min(99.0, 95.0) = 95.0
        assert stop == 95.0  # floor protects
