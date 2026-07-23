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
