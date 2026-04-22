"""
Tests para el scoring v3 de UniverseFilter (La "Puerta Doble").

Valida:
- Ruta A (S&P500 / Hohn Mode): Calidad fundamental pura
- Ruta B (Guru Gems / Emergentes): Convicción institucional
- Purga de sesgos: momentum, opciones, analistas = 0 impacto
- Regla anti-sesgo: monopolios caros no son penalizados
- Penalización severa: Beneish y Altman Z-Score
"""
import pytest
from backend.application.universe_filter import (
    UniverseFilter,
    UniverseCandidate,
    MarketRegime,
)


@pytest.fixture
def uf():
    return UniverseFilter()


def _make_candidate(**kwargs):
    """Helper para crear candidatos con defaults razonables."""
    defaults = dict(
        ticker="TEST",
        regime=MarketRegime.NEUTRAL,
        is_emerging_gem=False,
    )
    defaults.update(kwargs)
    return UniverseCandidate(**defaults)


# ================================================================
# RUTA A: S&P 500 (HOHN MODE)
# ================================================================

class TestRutaA_HohnMode:

    def test_qgarp_score_dominates(self, uf):
        """QGARP score debe ser el factor con mayor peso (30%)."""
        high_q = _make_candidate(qgarp_score=100.0)
        low_q = _make_candidate(qgarp_score=20.0)
        diff = uf._compute_score(high_q) - uf._compute_score(low_q)
        assert diff == pytest.approx(24.0, abs=0.1), \
            f"QGARP 100 vs 20 debería dar ~24pts de diferencia, dio {diff}"

    def test_fcf_margin_tiers(self, uf):
        """FCF Margin tiene 3 escalones: >25%, >15%, >10%."""
        tier1 = _make_candidate(fcf_margin=30.0)
        tier2 = _make_candidate(fcf_margin=18.0)
        tier3 = _make_candidate(fcf_margin=12.0)
        zero = _make_candidate(fcf_margin=5.0)
        assert uf._compute_score(tier1) == pytest.approx(15.0)
        assert uf._compute_score(tier2) == pytest.approx(10.0)
        assert uf._compute_score(tier3) == pytest.approx(5.0)
        assert uf._compute_score(zero) == pytest.approx(0.0)

    def test_piotroski_f_score_tiers(self, uf):
        """Piotroski F-Score: >=7 → 10pts, >=5 → 5pts."""
        strong = _make_candidate(piotroski_f_score=8)
        moderate = _make_candidate(piotroski_f_score=6)
        weak = _make_candidate(piotroski_f_score=3)
        assert uf._compute_score(strong) == pytest.approx(10.0)
        assert uf._compute_score(moderate) == pytest.approx(5.0)
        assert uf._compute_score(weak) == pytest.approx(0.0)

    def test_monopoly_not_penalized_for_price(self, uf):
        """
        Regla anti-sesgo Hohn: Si qgarp >= 80 y fcf_margin >= 20,
        la penalización por price_to_gf_value > 1.3 se ANULA.
        """
        # Monopolio caro → sin penalización
        monopoly_expensive = _make_candidate(
            qgarp_score=85.0, fcf_margin=25.0, price_to_gf_value=1.4,
        )
        monopoly_base = _make_candidate(
            qgarp_score=85.0, fcf_margin=25.0, price_to_gf_value=0.0,
        )
        # Deben tener el mismo score (penalización anulada)
        assert uf._compute_score(monopoly_expensive) == uf._compute_score(monopoly_base)

    def test_mediocre_penalized_for_price(self, uf):
        """Empresa mediocre y cara SÍ debe ser castigada."""
        mediocre_expensive = _make_candidate(
            qgarp_score=40.0, fcf_margin=8.0, price_to_gf_value=1.4,
        )
        mediocre_fair = _make_candidate(
            qgarp_score=40.0, fcf_margin=8.0, price_to_gf_value=0.0,
        )
        assert uf._compute_score(mediocre_expensive) < uf._compute_score(mediocre_fair)

    def test_beneish_severe_penalty(self, uf):
        """Beneish M-Score > -1.78 → penalización severa de -15."""
        fraud = _make_candidate(
            qgarp_score=70.0, fcf_margin=20.0, beneish_m_score=-1.5,
        )
        clean = _make_candidate(
            qgarp_score=70.0, fcf_margin=20.0, beneish_m_score=-3.0,
        )
        diff = uf._compute_score(clean) - uf._compute_score(fraud)
        assert diff == pytest.approx(15.0)

    def test_altman_bankruptcy_penalty(self, uf):
        """Altman Z-Score < 1.8 → penalización de -10."""
        bankrupt = _make_candidate(
            qgarp_score=60.0, altman_z_score=1.2,
        )
        safe = _make_candidate(
            qgarp_score=60.0, altman_z_score=3.5,
        )
        diff = uf._compute_score(safe) - uf._compute_score(bankrupt)
        assert diff == pytest.approx(10.0)


# ================================================================
# RUTA B: GURU GEMS (EMERGENTES)
# ================================================================

class TestRutaB_GuruGems:

    def test_guru_conviction_dominates(self, uf):
        """Para Gems, guru_conviction_score tiene 35% de peso."""
        gem_high = _make_candidate(
            is_emerging_gem=True, guru_conviction_score=100.0,
        )
        gem_low = _make_candidate(
            is_emerging_gem=True, guru_conviction_score=0.0,
        )
        diff = uf._compute_score(gem_high) - uf._compute_score(gem_low)
        assert diff == pytest.approx(35.0)

    def test_insider_conviction_for_gems(self, uf):
        """Insider conviction tiene 25% de peso para Gems."""
        gem = _make_candidate(
            is_emerging_gem=True, insider_conviction_score=100.0,
        )
        assert uf._compute_score(gem) == pytest.approx(25.0)

    def test_negative_fcf_not_penalized(self, uf):
        """Gems con FCF negativo NO deben ser penalizadas (amnistía)."""
        gem_negative_fcf = _make_candidate(
            is_emerging_gem=True, fcf_margin=-20.0,
            guru_conviction_score=80.0,
        )
        gem_positive_fcf = _make_candidate(
            is_emerging_gem=True, fcf_margin=0.0,
            guru_conviction_score=80.0,
        )
        # FCF negativo = 0, FCF cero = 0 → misma puntuación
        assert uf._compute_score(gem_negative_fcf) == uf._compute_score(gem_positive_fcf)

    def test_guru_accumulation_fallback(self, uf):
        """Si no hay guru_conviction_score, usar guru_accumulation boolean."""
        gem_bool = _make_candidate(
            is_emerging_gem=True, guru_accumulation=True, guru_conviction_score=0.0,
        )
        gem_none = _make_candidate(
            is_emerging_gem=True, guru_accumulation=False, guru_conviction_score=0.0,
        )
        assert uf._compute_score(gem_bool) > uf._compute_score(gem_none)


# ================================================================
# PURGA DE SESGOS (aplica a ambas rutas)
# ================================================================

class TestPurgaDeSesgos:

    def test_momentum_has_zero_impact(self, uf):
        """El momentum técnico ya NO debe afectar el score."""
        with_momentum = _make_candidate(relative_momentum=0.9, qgarp_score=50.0)
        without_momentum = _make_candidate(relative_momentum=0.0, qgarp_score=50.0)
        assert uf._compute_score(with_momentum) == uf._compute_score(without_momentum)

    def test_analyst_consensus_has_zero_impact(self, uf):
        """El consenso de analistas ya NO debe afectar el score."""
        strong_buy = _make_candidate(analyst_consensus="strong_buy", qgarp_score=50.0)
        strong_sell = _make_candidate(analyst_consensus="strong_sell", qgarp_score=50.0)
        assert uf._compute_score(strong_buy) == uf._compute_score(strong_sell)

    def test_options_mm_bias_has_zero_impact(self, uf):
        """El sesgo de Market Makers ya NO debe afectar el score."""
        bullish = _make_candidate(mm_bias="BULLISH_PULL", qgarp_score=50.0)
        bearish = _make_candidate(mm_bias="BEARISH_PULL", qgarp_score=50.0)
        assert uf._compute_score(bullish) == uf._compute_score(bearish)

    def test_sentiment_has_zero_impact(self, uf):
        """El sentimiento Fear & Greed ya NO debe afectar el score."""
        fearful = _make_candidate(sentiment_score=10.0, qgarp_score=50.0)
        greedy = _make_candidate(sentiment_score=90.0, qgarp_score=50.0)
        assert uf._compute_score(fearful) == uf._compute_score(greedy)

    def test_political_signal_has_zero_impact(self, uf):
        """La señal política ya NO debe afectar el score."""
        bullish = _make_candidate(political_signal="bullish", qgarp_score=50.0)
        bearish = _make_candidate(political_signal="bearish", qgarp_score=50.0)
        assert uf._compute_score(bullish) == uf._compute_score(bearish)


# ================================================================
# LIQUIDEZ FED (MacroSnapshot)
# ================================================================

class TestLiquidezFED:

    def test_classify_liquidity_with_series(self):
        """Calcula delta de WALCL desde una serie histórica."""
        from backend.infrastructure.data_providers.fred_macro_intelligence import (
            FREDMacroIntelligence, MacroSnapshot,
        )
        s = MacroSnapshot(
            fed_balance_sheet=8000.0,
            raw_data={"WALCL_series": [7800, 7850, 7900, 7950, 8000]},
        )
        FREDMacroIntelligence._classify_liquidity(s)
        assert s.liquidity_regime == "abundant"
        assert s.fed_balance_trend == "expanding"
        assert s.raw_data["_walcl_diff_pct_calculated"] > 0

    def test_classify_liquidity_tightening(self):
        """Detecta tightening cuando la serie cae."""
        from backend.infrastructure.data_providers.fred_macro_intelligence import (
            FREDMacroIntelligence, MacroSnapshot,
        )
        s = MacroSnapshot(
            fed_balance_sheet=7700.0,
            raw_data={"WALCL_series": [8000, 7950, 7900, 7800, 7700]},
        )
        FREDMacroIntelligence._classify_liquidity(s)
        assert s.liquidity_regime == "tightening"
        assert s.fed_balance_trend == "contracting"

    def test_classify_liquidity_with_prev_value(self):
        """Calcula delta desde un valor previo explícito."""
        from backend.infrastructure.data_providers.fred_macro_intelligence import (
            FREDMacroIntelligence, MacroSnapshot,
        )
        s = MacroSnapshot(
            fed_balance_sheet=8100.0,
            raw_data={"WALCL_prev": 8000.0},
        )
        FREDMacroIntelligence._classify_liquidity(s)
        assert s.liquidity_regime == "abundant"

    def test_classify_liquidity_stable(self):
        """Régimen neutral cuando la variación es mínima."""
        from backend.infrastructure.data_providers.fred_macro_intelligence import (
            FREDMacroIntelligence, MacroSnapshot,
        )
        s = MacroSnapshot(
            fed_balance_sheet=8001.0,
            raw_data={"WALCL_prev": 8000.0},
        )
        FREDMacroIntelligence._classify_liquidity(s)
        assert s.liquidity_regime == "neutral"
        assert s.fed_balance_trend == "stable"
