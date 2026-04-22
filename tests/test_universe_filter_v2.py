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
        """Candidate with all V3 Hohn signals should score high."""
        c = UniverseCandidate(
            ticker="PERFECT", regime=MarketRegime.RISK_ON,
            qgarp_score=95,
            fcf_margin=30.0,
            piotroski_f_score=8,
            guru_conviction_score=90, guru_count=15,
            insider_conviction_score=85,
            price_to_gf_value=0.7,  # Subvaluado
        )
        score = uf._compute_score(c)
        assert score > 60  # Should be high

    def test_min_score_candidate(self, uf):
        """Candidate with toxic fundamentals should score negative."""
        c = UniverseCandidate(
            ticker="TERRIBLE", regime=MarketRegime.CRISIS,
            qgarp_score=20,
            fcf_margin=2.0,
            piotroski_f_score=2,
            price_to_gf_value=1.5,  # Muy caro + baja calidad = penalización
            beneish_m_score=-1.0,   # Manipulación contable
            altman_z_score=1.2,     # Riesgo de quiebra
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

    def test_risk_penalty_beneish_altman(self, uf):
        """Beneish and Altman should penalize risky companies."""
        c_safe = UniverseCandidate(
            ticker="SAFE", regime=MarketRegime.NEUTRAL,
            qgarp_score=60,
            fcf_margin=20.0,
            beneish_m_score=-3.0,  # No manipulation (default safe)
            altman_z_score=5.0,    # Healthy
        )
        c_risky = UniverseCandidate(
            ticker="RISKY", regime=MarketRegime.NEUTRAL,
            qgarp_score=60,
            fcf_margin=20.0,
            beneish_m_score=-1.0,  # Manipulation suspected
            altman_z_score=1.2,    # Bankruptcy risk
        )
        assert uf._compute_score(c_safe) > uf._compute_score(c_risky)

    def test_valuation_premium_penalty(self, uf):
        """Overvalued stocks with low quality should be penalized vs undervalued."""
        c_cheap = UniverseCandidate(
            ticker="CHEAP", regime=MarketRegime.NEUTRAL,
            qgarp_score=50,
            price_to_gf_value=0.7,  # 30% discount
        )
        c_expensive = UniverseCandidate(
            ticker="EXPENSIVE", regime=MarketRegime.NEUTRAL,
            qgarp_score=50,
            price_to_gf_value=1.5,  # 50% premium + low quality
        )
        assert uf._compute_score(c_cheap) > uf._compute_score(c_expensive)

    def test_all_defaults_score_zero(self, uf):
        """Default candidate (no signals) should score near 0."""
        c = UniverseCandidate(ticker="DEFAULT", regime=MarketRegime.NEUTRAL)
        score = uf._compute_score(c)
        assert -5 <= score <= 5  # Near zero
