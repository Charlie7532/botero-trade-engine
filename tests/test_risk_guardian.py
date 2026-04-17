"""
Tests for RiskGuardian — Capital protection with iron rules.

Tests verify:
- Portfolio drawdown detection and position scaling
- Daily loss circuit breaker and cooldown
- VIX-based position scaling (reduce and emergency)
- Anti-martingale consecutive loss logic
- Combined risk scenarios
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from backend.application.portfolio_intelligence import RiskGuardian


class TestRiskGuardianBasic:
    """Tests for individual risk checks."""

    def test_normal_conditions_full_scale(self, risk_guardian):
        """Under normal conditions: full sizing, can trade, no alerts."""
        result = risk_guardian.evaluate(
            current_capital=100_000,
            daily_pnl_pct=0.005,
            current_vix=17,
        )
        assert result["position_scale"] == 1.0
        assert result["can_trade"] is True
        assert len(result["alerts"]) == 0

    def test_portfolio_drawdown_reduces_sizing(self, risk_guardian):
        """When portfolio DD exceeds max, sizing should drop to 50%."""
        # Set peak first
        risk_guardian.evaluate(current_capital=100_000, daily_pnl_pct=0, current_vix=17)
        # Now simulate drawdown
        result = risk_guardian.evaluate(
            current_capital=84_000,  # -16% DD > 15% max
            daily_pnl_pct=-0.01,
            current_vix=17,
        )
        assert result["position_scale"] == 0.5
        assert "DD" in result["alerts"][0]

    def test_daily_loss_stops_trading(self, risk_guardian):
        """Daily loss >= max should halt trading and trigger cooldown."""
        result = risk_guardian.evaluate(
            current_capital=100_000,
            daily_pnl_pct=-0.035,  # -3.5% > 3% max
            current_vix=17,
        )
        assert result["can_trade"] is False
        assert any("pausado" in a.lower() or "Pérdida" in a for a in result["alerts"])


class TestRiskGuardianVIX:
    """Tests for VIX-based scaling."""

    def test_vix_reduce_threshold(self, risk_guardian):
        """VIX >= 30 should reduce sizing by 30%."""
        result = risk_guardian.evaluate(
            current_capital=100_000,
            daily_pnl_pct=0,
            current_vix=32,
        )
        assert result["position_scale"] == 0.7
        assert any("VIX" in a for a in result["alerts"])

    def test_vix_emergency_threshold(self, risk_guardian):
        """VIX >= 40 should reduce sizing by 50%."""
        result = risk_guardian.evaluate(
            current_capital=100_000,
            daily_pnl_pct=0,
            current_vix=42,
        )
        assert result["position_scale"] == 0.5
        assert any("VIX" in a for a in result["alerts"])


class TestRiskGuardianAntiMartingale:
    """Tests for consecutive loss handling."""

    def test_three_consecutive_losses_reduce_sizing(self, risk_guardian):
        """After 3 consecutive losses, sizing should reduce by 30%."""
        for _ in range(3):
            risk_guardian.evaluate(
                current_capital=100_000,
                daily_pnl_pct=0,
                current_vix=17,
                last_trade_won=False,
            )
        result = risk_guardian.evaluate(
            current_capital=100_000,
            daily_pnl_pct=0,
            current_vix=17,
        )
        assert result["position_scale"] == 0.7
        assert result["consecutive_losses"] == 3

    def test_win_resets_consecutive_losses(self, risk_guardian):
        """A win should reset the consecutive loss counter."""
        for _ in range(2):
            risk_guardian.evaluate(
                current_capital=100_000, daily_pnl_pct=0, current_vix=17,
                last_trade_won=False,
            )
        risk_guardian.evaluate(
            current_capital=100_000, daily_pnl_pct=0, current_vix=17,
            last_trade_won=True,
        )
        result = risk_guardian.evaluate(
            current_capital=100_000, daily_pnl_pct=0, current_vix=17,
        )
        assert result["consecutive_losses"] == 0
        assert result["position_scale"] == 1.0


class TestRiskGuardianCombined:
    """Tests for combined risk scenarios."""

    def test_dd_plus_high_vix_compounds(self, risk_guardian):
        """DD + high VIX should compound the sizing reduction."""
        risk_guardian.evaluate(current_capital=100_000, daily_pnl_pct=0, current_vix=17)
        result = risk_guardian.evaluate(
            current_capital=84_000,  # -16% DD → scale 0.5
            daily_pnl_pct=-0.01,
            current_vix=32,          # VIX 32 → scale × 0.7
        )
        expected = round(0.5 * 0.7, 2)  # 0.35
        assert result["position_scale"] == expected
        assert len(result["alerts"]) >= 2

    def test_dd_plus_vix_emergency_plus_losses(self, risk_guardian):
        """Worst case: DD + VIX emergency + losing streak."""
        risk_guardian.evaluate(current_capital=100_000, daily_pnl_pct=0, current_vix=17)
        for _ in range(3):
            risk_guardian.evaluate(
                current_capital=100_000, daily_pnl_pct=0, current_vix=17,
                last_trade_won=False,
            )
        result = risk_guardian.evaluate(
            current_capital=84_000,  # DD 16% → 0.5
            daily_pnl_pct=-0.01,
            current_vix=42,          # VIX emergency → ×0.5
        )
        # 0.5 (DD) * 0.5 (VIX) * 0.7 (losses) = 0.175
        expected = round(0.5 * 0.5 * 0.7, 2)
        assert result["position_scale"] == expected
        assert len(result["alerts"]) >= 3
