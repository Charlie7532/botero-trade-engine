"""
Tests for SmartEntryEngine — Intelligent Order Execution.
"""
import pytest
from backend.application.smart_entry import SmartEntryEngine, GapRules, PreMarketCheck


@pytest.fixture
def engine():
    return SmartEntryEngine()


@pytest.fixture
def strict_engine():
    return SmartEntryEngine(rules=GapRules(max_gap_up_pct=1.0, max_gap_down_pct=-2.0))


# ═══════════════════════════════════════════════════════════
# NORMAL ENTRIES (should approve)
# ═══════════════════════════════════════════════════════════

class TestNormalEntries:
    def test_flat_open_approved(self, engine):
        """Same price as analysis → approved."""
        check = engine.validate_entry("AAPL", analysis_price=180.0, current_price=180.0)
        assert check.is_valid is True
        assert check.gap_pct == 0.0
        assert check.recommended_limit > 0

    def test_small_gap_up_approved(self, engine):
        """Small gap up within tolerance → approved."""
        check = engine.validate_entry("MSFT", analysis_price=400.0, current_price=405.0)
        assert check.is_valid is True
        assert 0 < check.gap_pct < 3.0

    def test_gap_down_favorable(self, engine):
        """Small gap down → even better entry."""
        check = engine.validate_entry("NVDA", analysis_price=950.0, current_price=940.0)
        assert check.is_valid is True
        assert check.gap_pct < 0
        # Limit should be near current (lower) price, not analysis
        assert check.recommended_limit < 950.0

    def test_no_premarket_price(self, engine):
        """No current price → use analysis price with premium."""
        check = engine.validate_entry("AAPL", analysis_price=180.0)
        assert check.is_valid is True
        assert check.recommended_limit == pytest.approx(183.60, abs=0.01)  # 180 * 1.02

    def test_limit_has_ceiling(self, engine):
        """Limit price should never exceed analysis_price + max_premium."""
        check = engine.validate_entry("MSFT", analysis_price=400.0, current_price=402.0)
        assert check.is_valid is True
        max_allowed = 400.0 * (1 + 2.0/100)  # 408.0
        assert check.recommended_limit <= max_allowed


# ═══════════════════════════════════════════════════════════
# GAP PROTECTION (should reject)
# ═══════════════════════════════════════════════════════════

class TestGapProtection:
    def test_gap_up_rejected(self, engine):
        """Gap > +3% → rejected."""
        check = engine.validate_entry("NVDA", analysis_price=950.0, current_price=985.0)
        assert check.is_valid is False
        assert "Gap UP" in check.rejection_reason
        assert check.gap_pct > 3.0

    def test_gap_down_rejected(self, engine):
        """Gap < -5% → rejected (something bad happened)."""
        check = engine.validate_entry("META", analysis_price=500.0, current_price=470.0)
        assert check.is_valid is False
        assert "Gap DOWN" in check.rejection_reason
        assert check.gap_pct < -5.0

    def test_exact_threshold_up(self, engine):
        """Exactly at +3% should still pass (boundary)."""
        price = 100.0 * 1.03  # Exactly +3%
        check = engine.validate_entry("TEST", analysis_price=100.0, current_price=price)
        assert check.is_valid is True  # At boundary, not over

    def test_strict_rules(self, strict_engine):
        """Strict rules should reject smaller gaps."""
        check = strict_engine.validate_entry("AAPL", analysis_price=180.0, current_price=183.0)
        assert check.is_valid is False  # +1.67% > 1.0% → rejected


# ═══════════════════════════════════════════════════════════
# SPREAD PROTECTION
# ═══════════════════════════════════════════════════════════

class TestSpreadProtection:
    def test_wide_spread_rejected(self, engine):
        """Wide bid-ask spread → rejected (illiquid)."""
        check = engine.validate_entry(
            "ILLIQ", analysis_price=50.0, current_price=50.0,
            bid=49.0, ask=50.0,  # 2% spread
        )
        assert check.is_valid is False
        assert "Spread" in check.rejection_reason

    def test_tight_spread_approved(self, engine):
        """Tight spread → approved."""
        check = engine.validate_entry(
            "AAPL", analysis_price=180.0, current_price=180.0,
            bid=179.95, ask=180.05,  # 0.06% spread
        )
        assert check.is_valid is True

    def test_no_spread_data(self, engine):
        """Missing bid/ask → skip spread check (don't reject)."""
        check = engine.validate_entry("MSFT", analysis_price=400.0, current_price=401.0)
        assert check.is_valid is True


# ═══════════════════════════════════════════════════════════
# STOP LOSS CALCULATION
# ═══════════════════════════════════════════════════════════

class TestStopLoss:
    def test_atr_based_stop(self, engine):
        """Stop should be 2× ATR below entry."""
        check = engine.validate_entry(
            "AAPL", analysis_price=180.0, current_price=180.0, atr=3.0,
        )
        assert check.is_valid is True
        # Stop = 180 - (3 * 2) = 174
        assert check.recommended_stop == pytest.approx(174.0, abs=0.5)

    def test_fallback_stop(self, engine):
        """No ATR → 5% below entry."""
        check = engine.validate_entry("MSFT", analysis_price=400.0, current_price=400.0)
        assert check.is_valid is True
        assert check.recommended_stop == pytest.approx(380.0, abs=1.0)  # 400 * 0.95


# ═══════════════════════════════════════════════════════════
# ORDER CREATION
# ═══════════════════════════════════════════════════════════

class TestOrderCreation:
    def test_limit_order_params(self, engine):
        check = engine.validate_entry("AAPL", analysis_price=180.0, current_price=180.0)
        params = engine.create_limit_order_params(check, notional=10000)
        assert params["type"] == "limit"
        assert params["symbol"] == "AAPL"
        assert params["limit_price"] > 0
        assert params["qty"] > 0
        assert params["side"] == "buy"

    def test_bracket_order_params(self, engine):
        check = engine.validate_entry("MSFT", analysis_price=400.0, current_price=400.0, atr=5.0)
        params = engine.create_bracket_order_params(check, notional=20000, risk_reward_ratio=2.5)
        assert params["type"] == "bracket"
        assert params["limit_price"] > 0
        assert params["stop_loss_price"] > 0
        assert params["take_profit_price"] > params["limit_price"]
        assert params["risk_reward_ratio"] == 2.5

    def test_rejected_entry_raises(self, engine):
        check = engine.validate_entry("NVDA", analysis_price=950.0, current_price=990.0)
        assert check.is_valid is False
        with pytest.raises(ValueError, match="rejected"):
            engine.create_limit_order_params(check, notional=10000)

    def test_qty_minimum_1(self, engine):
        check = engine.validate_entry("BRK.A", analysis_price=600000.0, current_price=600000.0)
        params = engine.create_limit_order_params(check, notional=500)
        assert params["qty"] >= 1  # At least 1 share


# ═══════════════════════════════════════════════════════════
# ADAPTIVE RULES
# ═══════════════════════════════════════════════════════════

class TestAdaptiveRules:
    def test_high_vix_tightens_premium(self, engine):
        rules = engine.adaptive_rules(vix=30)
        assert rules.max_entry_premium_pct < engine.rules.max_entry_premium_pct

    def test_crisis_vix_even_tighter(self, engine):
        """VIX > 35 should be even more restrictive than VIX > 25."""
        rules_elevated = engine.adaptive_rules(vix=30)
        rules_crisis = engine.adaptive_rules(vix=40)
        assert rules_crisis.max_entry_premium_pct < rules_elevated.max_entry_premium_pct
        assert rules_crisis.wait_minutes_after_open == 15

    def test_high_beta_widens_gap_tolerance(self, engine):
        rules = engine.adaptive_rules(beta=2.0)
        assert rules.max_gap_up_pct > engine.rules.max_gap_up_pct

    def test_normal_conditions_unchanged(self, engine):
        rules = engine.adaptive_rules(vix=18)
        assert rules.max_entry_premium_pct == engine.rules.max_entry_premium_pct


# ═══════════════════════════════════════════════════════════
# GURU VALUATION SCORING (UniverseFilter — real GF data)
# ═══════════════════════════════════════════════════════════

class TestGuruValuationScoring:
    @pytest.fixture
    def uf(self):
        from backend.application.universe_filter import UniverseFilter
        return UniverseFilter()

    def test_undervalued_vs_overvalued_gf_value(self, uf):
        """Stock below GF Value should score higher than one above."""
        from backend.application.universe_filter import UniverseCandidate, MarketRegime

        c_cheap = UniverseCandidate(
            ticker="CHEAP", regime=MarketRegime.RISK_ON,
            qgarp_score=75, price_to_gf_value=0.75,
        )
        c_expensive = UniverseCandidate(
            ticker="EXPENSIVE", regime=MarketRegime.RISK_ON,
            qgarp_score=75, price_to_gf_value=1.35,
        )
        assert uf._compute_score(c_cheap) > uf._compute_score(c_expensive)

    def test_slight_discount_still_bonus(self, uf):
        """P/GF Value < 1.0 but > 0.8 should get moderate bonus."""
        from backend.application.universe_filter import UniverseCandidate, MarketRegime

        c_discount = UniverseCandidate(
            ticker="DISC", regime=MarketRegime.RISK_ON,
            price_to_gf_value=0.92,
        )
        c_fair = UniverseCandidate(
            ticker="FAIR", regime=MarketRegime.RISK_ON,
            price_to_gf_value=1.05,
        )
        assert uf._compute_score(c_discount) > uf._compute_score(c_fair)

    def test_piotroski_high_vs_low(self, uf):
        """High Piotroski F-Score should score better than low."""
        from backend.application.universe_filter import UniverseCandidate, MarketRegime

        c_strong = UniverseCandidate(
            ticker="STRONG", regime=MarketRegime.RISK_ON,
            piotroski_f_score=8,
        )
        c_weak = UniverseCandidate(
            ticker="WEAK", regime=MarketRegime.RISK_ON,
            piotroski_f_score=3,
        )
        assert uf._compute_score(c_strong) > uf._compute_score(c_weak)

    def test_guru_conviction_bonus(self, uf):
        """High guru conviction should boost score vs no conviction."""
        from backend.application.universe_filter import UniverseCandidate, MarketRegime

        c_backed = UniverseCandidate(
            ticker="BACKED", regime=MarketRegime.RISK_ON,
            guru_conviction_score=85,
        )
        c_solo = UniverseCandidate(
            ticker="SOLO", regime=MarketRegime.RISK_ON,
            guru_conviction_score=0,
        )
        assert uf._compute_score(c_backed) > uf._compute_score(c_solo)

    def test_fcf_margin_quality(self, uf):
        """High FCF margin (cash conversion) = quality bonus."""
        from backend.application.universe_filter import UniverseCandidate, MarketRegime

        c_quality = UniverseCandidate(
            ticker="QUALITY", regime=MarketRegime.RISK_ON,
            fcf_margin=30.0,
        )
        c_low = UniverseCandidate(
            ticker="LOW", regime=MarketRegime.RISK_ON,
            fcf_margin=5.0,
        )
        assert uf._compute_score(c_quality) > uf._compute_score(c_low)

    def test_beneish_manipulation_flag(self, uf):
        """Beneish M-Score > -1.78 = earnings manipulation red flag."""
        from backend.application.universe_filter import UniverseCandidate, MarketRegime

        c_manipulator = UniverseCandidate(
            ticker="FRAUD", regime=MarketRegime.RISK_ON,
            beneish_m_score=-1.2,
        )
        c_clean = UniverseCandidate(
            ticker="CLEAN", regime=MarketRegime.RISK_ON,
            beneish_m_score=-2.8,
        )
        assert uf._compute_score(c_manipulator) < uf._compute_score(c_clean)

    def test_beneish_default_is_safe(self, uf):
        """Default beneish (-3.0) should not penalize."""
        from backend.application.universe_filter import UniverseCandidate, MarketRegime

        c_default = UniverseCandidate(
            ticker="DEFAULT", regime=MarketRegime.RISK_ON,
        )
        c_penalized = UniverseCandidate(
            ticker="PENALIZED", regime=MarketRegime.RISK_ON,
            beneish_m_score=-1.5,
        )
        assert uf._compute_score(c_default) > uf._compute_score(c_penalized)

    def test_complete_guru_profile(self, uf):
        """A stock with all guru metrics positive should score well."""
        from backend.application.universe_filter import UniverseCandidate, MarketRegime

        c_guru_pick = UniverseCandidate(
            ticker="GURU", regime=MarketRegime.RISK_ON,
            qgarp_score=85,
            price_to_gf_value=0.75,
            ps_vs_historical=0.6,
            price_to_fcf=10.0,
            fcf_margin=28.0,
            beneish_m_score=-2.5,
            guru_conviction_score=80,
            insider_conviction_score=70,
        )
        score = uf._compute_score(c_guru_pick)
        assert score > 50
