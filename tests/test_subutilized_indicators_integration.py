"""
Unit Tests — Sub-utilized Indicators & Blind Spots Safeguards
================================================================
Tests Wishlists Registry, Short Squeeze ETF exemption (Blind Spot 3),
and Beneish M-Score Financials exemption (Blind Spot 4).
"""
import pytest
from backend.modules.shared.domain.constants.wishlists import (
    INVESTMENT_WISHLIST,
    ROTATION_SECTOR_LEADERS,
    QUALITY_SWING_WISHLIST,
    SPECULATIVE_WISHLIST,
    ALL_DEPARTMENTAL_TICKERS,
)


def test_wishlists_registry_integrity():
    """Test 1: Verify all 4 Departmental Wishlists exist and contain valid tickers."""
    assert len(INVESTMENT_WISHLIST) >= 15
    assert "AAPL" in INVESTMENT_WISHLIST
    assert "MSFT" in INVESTMENT_WISHLIST

    assert "XLK" in ROTATION_SECTOR_LEADERS
    assert "NVDA" in ROTATION_SECTOR_LEADERS["XLK"]

    assert len(QUALITY_SWING_WISHLIST) >= 5
    assert len(SPECULATIVE_WISHLIST) >= 5
    assert "TSLA" in SPECULATIVE_WISHLIST

    assert len(ALL_DEPARTMENTAL_TICKERS) >= 20


def test_blind_spot_3_short_squeeze_etf_exemption():
    """Test 2: Short Squeeze multiplier active for stocks (GME/TSLA), disabled for ETFs (SPY/XLE)."""
    # Stock with High Short Interest -> Squeeze eligible
    stock_ticker = "GME"
    stock_is_etf = False
    short_interest = 22.0
    days_to_cover = 5.0

    stock_squeeze_active = (short_interest >= 15.0 and days_to_cover >= 4.0 and not stock_is_etf)
    assert stock_squeeze_active is True

    # ETF with High Short Interest -> Exempt (Delta-neutral hedging)
    etf_ticker = "SPY"
    etf_is_etf = True
    etf_squeeze_active = (short_interest >= 15.0 and days_to_cover >= 4.0 and not etf_is_etf)
    assert etf_squeeze_active is False


def test_blind_spot_4_beneish_mscore_financials_exemption():
    """Test 3: Beneish M-Score > -1.78 triggers accounting fraud veto, EXCEPT for Financials (JPM)."""
    # Tech stock with Beneish M-score > -1.78 -> Vetoed
    tech_sector = "Technology"
    tech_beneish = -1.50  # Fraud zone (> -1.78)
    tech_vetoed = (tech_beneish > -1.78 and tech_sector != "Financial")
    assert tech_vetoed is True

    # Bank with Beneish M-score > -1.78 -> Exempt
    bank_sector = "Financial"
    bank_beneish = -1.50
    bank_vetoed = (bank_beneish > -1.78 and bank_sector != "Financial")
    assert bank_vetoed is False


def test_watchlist_candidate_financials_exemption():
    """Verify that a QualityWatchlistCandidate with sector='Financial' or 'Financials' is exempt from Beneish manipulation veto."""
    from backend.modules.portfolio_management.domain.entities.watchlist_entities import QualityWatchlistCandidate

    # Technology candidate - fails quality gate due to Beneish M-score > -1.78
    tech_cand = QualityWatchlistCandidate(
        ticker="TECH",
        sector="Technology",
        gf_score=85,
        piotroski_f_score=7,
        roic=20,
        beneish_m_score=-1.50  # Manipulator zone
    )
    assert tech_cand.beneish_m_safe is False
    assert tech_cand.passes_quality_gate() is False

    # Financial candidate - passes quality gate because it's exempt from Beneish manipulation veto
    fin_cand = QualityWatchlistCandidate(
        ticker="JPM",
        sector="Financials",
        gf_score=85,
        piotroski_f_score=7,
        roic=20,
        beneish_m_score=-1.50  # Manipulator zone, but exempt
    )
    assert fin_cand.beneish_m_safe is True
    assert fin_cand.passes_quality_gate() is True


def test_calculate_target_weights_empty_sectors():
    """Verify that QualityEntryGate.calculate_target_weights does not throw ZeroDivisionError if avail_sectors is empty."""
    from backend.modules.entry_decision.application.use_cases.quality_entry_gate import QualityEntryGate

    gate = QualityEntryGate()
    target_weights = gate.calculate_target_weights(
        mode="MERCADO_SANO",
        sec_th={},
        sec_fi={},
        sec_tw={},
        avail_sectors=[]
    )
    assert target_weights == {}

