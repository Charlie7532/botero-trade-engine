"""
Tests for UniverseFilter v2 scoring and MacroRegimeDetector with FRED.
Validates institutional scoring with MCP data inputs.
"""
import pytest
from backend.application.universe_filter import (
    UniverseFilter, UniverseCandidate, MacroRegimeDetector, MarketRegime,
)


# ═══════════════════════════════════════════════════════════
# MacroRegimeDetector + FRED
# ═══════════════════════════════════════════════════════════

class TestMacroRegimeDetectorFRED:
    def test_detect_risk_on(self):
        detector = MacroRegimeDetector()
        regime = detector.detect_from_fred({
            "vix": 13, "yield_spread": 1.5,
            "gdp_growth": 3.0, "cpi_yoy": 2.0,
            "unemployment_rate": 3.5,
        })
        assert regime == MarketRegime.RISK_ON
        assert detector.macro_snapshot is not None
        assert detector.macro_snapshot.macro_regime == "risk_on"

    def test_detect_crisis(self):
        detector = MacroRegimeDetector()
        regime = detector.detect_from_fred({
            "vix": 50, "yield_spread": -1.5,
            "gdp_growth": -3.0, "cpi_yoy": 9.0,
            "unemployment_rate": 7.0,
        })
        assert regime == MarketRegime.CRISIS

    def test_detect_neutral(self):
        detector = MacroRegimeDetector()
        regime = detector.detect_from_fred({
            "vix": 20, "yield_spread": 0.3,
        })
        assert regime in (MarketRegime.NEUTRAL, MarketRegime.RISK_ON)

    def test_vix_level_updated(self):
        detector = MacroRegimeDetector()
        detector.detect_from_fred({"vix": 35.5})
        assert detector.vix_level == 35.5

    def test_fallback_to_manual(self):
        detector = MacroRegimeDetector()
        regime = detector.detect_from_data(vix=30, yield_spread=-0.5)
        assert regime == MarketRegime.RISK_OFF


# ═══════════════════════════════════════════════════════════
# UniverseFilter v2 Scoring
# ═══════════════════════════════════════════════════════════

class TestUniverseFilterScoring:
    @pytest.fixture
    def uf(self):
        return UniverseFilter()

    def test_max_score_candidate(self, uf):
        """Candidate with all signals bullish should score high."""
        c = UniverseCandidate(
            ticker="PERFECT", regime=MarketRegime.RISK_ON,
            relative_momentum=0.1, qgarp_score=95,
            guru_conviction_score=90, guru_count=15,
            insider_conviction_score=85, insider_sentiment="strong_buy",
            dcf_discount_pct=30, catalyst_active=True,
            risk_score_5d=90, analyst_consensus="strong_buy",
            political_signal="bullish", mm_bias="BULLISH_PULL",
            sentiment_score=20,
        )
        score = uf._compute_score(c)
        assert score > 60  # Should be high

    def test_min_score_candidate(self, uf):
        """Candidate with all signals bearish should score low."""
        c = UniverseCandidate(
            ticker="TERRIBLE", regime=MarketRegime.CRISIS,
            relative_momentum=-0.1, qgarp_score=0,
            risk_score_5d=10, analyst_consensus="strong_sell",
            political_signal="bearish", mm_bias="BEARISH_PULL",
            sentiment_score=90,
        )
        score = uf._compute_score(c)
        assert score < 0

    def test_qgarp_vs_legacy_fallback(self, uf):
        """QGARP score should take priority over legacy guru boolean."""
        c_qgarp = UniverseCandidate(
            ticker="QGARP", regime=MarketRegime.NEUTRAL,
            qgarp_score=80, guru_accumulation=True,
        )
        c_legacy = UniverseCandidate(
            ticker="LEGACY", regime=MarketRegime.NEUTRAL,
            qgarp_score=0, guru_accumulation=True,
        )
        score_qgarp = uf._compute_score(c_qgarp)
        score_legacy = uf._compute_score(c_legacy)
        assert score_qgarp > score_legacy

    def test_risk_penalty(self, uf):
        """High risk stock should get penalized."""
        c_safe = UniverseCandidate(
            ticker="SAFE", regime=MarketRegime.NEUTRAL,
            risk_score_5d=80,
        )
        c_risky = UniverseCandidate(
            ticker="RISKY", regime=MarketRegime.NEUTRAL,
            risk_score_5d=10,
        )
        assert uf._compute_score(c_safe) > uf._compute_score(c_risky)

    def test_contrarian_sentiment(self, uf):
        """Extreme fear should boost score (contrarian)."""
        c_fear = UniverseCandidate(
            ticker="FEAR", regime=MarketRegime.NEUTRAL,
            sentiment_score=15,  # extreme fear
        )
        c_greed = UniverseCandidate(
            ticker="GREED", regime=MarketRegime.NEUTRAL,
            sentiment_score=90,  # extreme greed
        )
        assert uf._compute_score(c_fear) > uf._compute_score(c_greed)

    def test_all_defaults_score_zero(self, uf):
        """Default candidate (no signals) should score near 0."""
        c = UniverseCandidate(ticker="DEFAULT", regime=MarketRegime.NEUTRAL)
        score = uf._compute_score(c)
        assert -5 <= score <= 5  # Near zero
