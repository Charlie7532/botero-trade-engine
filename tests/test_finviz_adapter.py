"""
Tests for FinvizIntelligence adapter.
Verifies parsing of Finviz MCP responses into structured dataclasses.
"""
import pytest
from backend.infrastructure.data_providers.finviz_intelligence import FinvizIntelligence


@pytest.fixture
def fv():
    return FinvizIntelligence()


# ═══════════════════════════════════════════════════════════
# Sector Performance
# ═══════════════════════════════════════════════════════════

class TestSectorPerformance:
    def test_parses_sector_list(self, fv):
        raw = {"data": [
            {"sector": "Technology", "1D": 2.1, "1W": 4.5, "1M": 8.0, "3M": 15.0,
             "YTD": 20.0, "1Y": 35.0, "relative_volume": 1.5},
            {"sector": "Healthcare", "1D": -0.5, "1W": 1.0, "1M": 3.0, "3M": 5.0,
             "YTD": 8.0, "1Y": 12.0, "relative_volume": 0.9},
        ]}
        sectors = fv.parse_sector_performance(raw)
        assert len(sectors) == 2
        # Sorted by momentum_score descending — Technology first
        assert sectors[0].sector == "Technology"
        assert sectors[0].perf_1d == 2.1
        assert sectors[1].sector == "Healthcare"
        assert sectors[1].perf_1d == -0.5

    def test_handles_empty_data(self, fv):
        sectors = fv.parse_sector_performance({"data": []})
        assert sectors == []

    def test_handles_none(self, fv):
        sectors = fv.parse_sector_performance(None)
        assert sectors == []

    def test_momentum_score_calculated(self, fv):
        raw = {"data": [
            {"sector": "Tech", "1D": 2.0, "1W": 5.0, "1M": 10.0, "3M": 20.0},
        ]}
        sectors = fv.parse_sector_performance(raw)
        assert len(sectors) == 1
        # momentum = 2.0*0.1 + 5.0*0.2 + 10.0*0.3 + 20.0*0.4 = 12.2
        assert sectors[0].momentum_score == pytest.approx(12.2, abs=0.01)

    def test_parses_alternative_keys(self, fv):
        """Should handle both key formats."""
        raw = {"sectors": [
            {"name": "Energy", "perf_1d": 1.5, "perf_1w": 3.0, "perf_1m": 5.0, "perf_3m": 10.0},
        ]}
        sectors = fv.parse_sector_performance(raw)
        assert len(sectors) == 1
        assert sectors[0].sector == "Energy"
        assert sectors[0].perf_1d == 1.5


# ═══════════════════════════════════════════════════════════
# Volume Surge
# ═══════════════════════════════════════════════════════════

class TestVolumeSurge:
    def test_parses_surge_list(self, fv):
        raw = {"data": [
            {"ticker": "NVDA", "price": 950, "change_pct": 5.2,
             "volume": 80000000, "relative_volume": 3.5},
            {"ticker": "AAPL", "price": 178, "change_pct": -1.2,
             "volume": 45000000, "relative_volume": 2.1},
        ]}
        surges = fv.parse_volume_surge(raw)
        assert len(surges) == 2
        assert surges[0].ticker == "NVDA"
        assert surges[0].relative_volume == 3.5
        assert surges[1].change_pct == -1.2

    def test_handles_empty(self, fv):
        surges = fv.parse_volume_surge({"data": []})
        assert surges == []

    def test_handles_none(self, fv):
        surges = fv.parse_volume_surge(None)
        assert surges == []


# ═══════════════════════════════════════════════════════════
# Earnings Screener
# ═══════════════════════════════════════════════════════════

class TestEarningsScreener:
    def test_parses_earnings(self, fv):
        raw = {"data": [
            {"ticker": "META", "earnings_date": "2026-04-25", "earnings_timing": "AMC",
             "price": 520, "change_pct": 2.3},
        ]}
        plays = fv.parse_earnings_screener(raw)
        assert len(plays) == 1
        assert plays[0].ticker == "META"
        assert plays[0].earnings_date == "2026-04-25"

    def test_handles_none(self, fv):
        plays = fv.parse_earnings_screener(None)
        assert plays == []


# ═══════════════════════════════════════════════════════════
# Market Overview
# ═══════════════════════════════════════════════════════════

class TestMarketOverview:
    def test_parses_overview(self, fv):
        raw = {"advances": 350, "declines": 150, "vix": 18.5, "sp500_change": 0.5}
        overview = fv.parse_market_overview(raw)
        assert overview["advances"] == 350
        assert overview["declines"] == 150
        assert overview["vix"] == 18.5

    def test_handles_empty(self, fv):
        overview = fv.parse_market_overview({})
        assert isinstance(overview, dict)
        assert overview["advances"] == 0


# ═══════════════════════════════════════════════════════════
# SEC Filings
# ═══════════════════════════════════════════════════════════

class TestSECFilings:
    def test_parses_filings(self, fv):
        raw = {"data": [
            {"form_type": "10-K", "date": "2026-01-15", "title": "Annual Report"},
        ]}
        filings = fv.parse_sec_filings("AAPL", raw)
        assert len(filings) == 1
        assert filings[0]["form_type"] == "10-K"
        assert filings[0]["ticker"] == "AAPL"

    def test_handles_none(self, fv):
        filings = fv.parse_sec_filings("AAPL", None)
        assert filings == []


# ═══════════════════════════════════════════════════════════
# Stock News
# ═══════════════════════════════════════════════════════════

class TestStockNews:
    def test_parses_news(self, fv):
        raw = {"data": [
            {"headline": "AAPL beats earnings", "source": "Reuters", "date": "2026-04-15"},
        ]}
        news = fv.parse_stock_news("AAPL", raw)
        assert len(news) == 1
        assert news[0]["headline"] == "AAPL beats earnings"
        assert news[0]["ticker"] == "AAPL"

    def test_handles_empty(self, fv):
        news = fv.parse_stock_news("AAPL", {})
        assert news == []
