"""
Tests for FREDMacroIntelligence adapter.
Verifies macro snapshot parsing and regime classification.
"""
import pytest
from backend.infrastructure.data_providers.fred_macro_intelligence import (
    FREDMacroIntelligence, MacroSnapshot,
)


@pytest.fixture
def fred():
    return FREDMacroIntelligence()


# ═══════════════════════════════════════════════════════════
# Macro Snapshot Parsing
# ═══════════════════════════════════════════════════════════

class TestMacroSnapshot:
    def test_full_snapshot(self, fred):
        data = {
            "vix": 22.5, "yield_spread": 0.3,
            "gdp_growth": 2.1, "cpi_yoy": 3.2,
            "fed_funds_rate": 4.5, "unemployment_rate": 3.8,
            "consumer_sentiment": 65.0, "mortgage_30y": 6.8,
        }
        s = fred.parse_macro_snapshot(indicators_data=data)
        assert s.vix == 22.5
        assert s.gdp_growth == 2.1
        assert s.cpi_yoy == 3.2
        assert s.fed_funds_rate == 4.5
        assert s.yield_spread == 0.3

    def test_handles_empty(self, fred):
        s = fred.parse_macro_snapshot(indicators_data={})
        assert s.macro_regime == "neutral"
        assert s.regime_score == 50.0

    def test_handles_none(self, fred):
        s = fred.parse_macro_snapshot()
        assert isinstance(s, MacroSnapshot)
        assert s.macro_regime == "neutral"


# ═══════════════════════════════════════════════════════════
# VIX Classification
# ═══════════════════════════════════════════════════════════

class TestVIXClassification:
    def test_calm_market(self, fred):
        s = fred.parse_macro_snapshot(indicators_data={"vix": 12})
        assert s.vix_regime == "calm"

    def test_elevated_vix(self, fred):
        s = fred.parse_macro_snapshot(indicators_data={"vix": 22})
        assert s.vix_regime == "elevated"

    def test_panic_vix(self, fred):
        s = fred.parse_macro_snapshot(indicators_data={"vix": 32})
        assert s.vix_regime == "panic"

    def test_crisis_vix(self, fred):
        s = fred.parse_macro_snapshot(indicators_data={"vix": 45})
        assert s.vix_regime == "crisis"


# ═══════════════════════════════════════════════════════════
# Yield Curve Classification  
# ═══════════════════════════════════════════════════════════

class TestYieldCurve:
    def test_normal_curve(self, fred):
        s = fred.parse_macro_snapshot(indicators_data={"yield_spread": 1.5})
        assert s.yield_curve_signal == "normal"

    def test_flat_curve(self, fred):
        s = fred.parse_macro_snapshot(indicators_data={"yield_spread": 0.1})
        assert s.yield_curve_signal == "flat"

    def test_inverted_curve(self, fred):
        s = fred.parse_macro_snapshot(indicators_data={"yield_spread": -0.8})
        assert s.yield_curve_signal == "inverted"

    def test_computes_spread_from_rates(self, fred):
        """If yield_spread missing but 10Y and 2Y present, compute it."""
        s = fred.parse_macro_snapshot(indicators_data={
            "treasury_10y": 4.5, "treasury_2y": 3.5,
        })
        assert s.yield_spread == pytest.approx(1.0, abs=0.01)
        assert s.yield_curve_signal == "normal"


# ═══════════════════════════════════════════════════════════
# Composite Regime
# ═══════════════════════════════════════════════════════════

class TestCompositeRegime:
    def test_risk_on_environment(self, fred):
        """Low VIX, positive spread, strong GDP, low inflation."""
        s = fred.parse_macro_snapshot(indicators_data={
            "vix": 13, "yield_spread": 1.5,
            "gdp_growth": 3.0, "cpi_yoy": 2.0,
            "unemployment_rate": 3.5,
        })
        assert s.macro_regime == "risk_on"
        assert s.regime_score > 70

    def test_crisis_environment(self, fred):
        """High VIX, inverted curve, negative GDP, high inflation, high unemployment."""
        s = fred.parse_macro_snapshot(indicators_data={
            "vix": 55, "yield_spread": -2.0,
            "gdp_growth": -5.0, "cpi_yoy": 10.0,
            "unemployment_rate": 9.0,
        })
        assert s.macro_regime == "crisis"
        assert s.regime_score < 20

    def test_neutral_environment(self, fred):
        """Mixed signals."""
        s = fred.parse_macro_snapshot(indicators_data={
            "vix": 20, "yield_spread": 0.3,
            "gdp_growth": 1.5, "cpi_yoy": 3.5,
        })
        assert s.macro_regime in ("neutral", "risk_on")
        assert 30 < s.regime_score < 80


# ═══════════════════════════════════════════════════════════
# Inflation Classification
# ═══════════════════════════════════════════════════════════

class TestInflation:
    def test_low_inflation(self, fred):
        s = fred.parse_macro_snapshot(indicators_data={"cpi_yoy": 1.5})
        assert s.inflation_regime == "low"

    def test_moderate_inflation(self, fred):
        s = fred.parse_macro_snapshot(indicators_data={"cpi_yoy": 3.0})
        assert s.inflation_regime == "moderate"

    def test_high_inflation(self, fred):
        s = fred.parse_macro_snapshot(indicators_data={"cpi_yoy": 5.5})
        assert s.inflation_regime == "high"

    def test_hyperinflation(self, fred):
        s = fred.parse_macro_snapshot(indicators_data={"cpi_yoy": 9.0})
        assert s.inflation_regime == "hyperinflation"
