"""
Tests for GuruFocusIntelligence adapter.
Verifies parsing of MCP responses into structured dataclasses.
"""
import pytest
from backend.infrastructure.data_providers.gurufocus_intelligence import GuruFocusIntelligence


@pytest.fixture
def gf():
    return GuruFocusIntelligence()


# ═══════════════════════════════════════════════════════════
# QGARP Scorecard
# ═══════════════════════════════════════════════════════════

class TestQGARPScorecard:
    def test_parses_complete_response(self, gf):
        raw = {
            "total_score": 82, "quality_score": 75,
            "growth_score": 60, "valuation_score": 80,
            "piotroski_f_score": 7, "altman_z_score": 3.5,
            "gf_value_discount": 20.0, "roic": 18.5,
        }
        sc = gf.parse_qgarp_scorecard("AAPL", raw)
        assert sc.ticker == "AAPL"
        assert sc.total_score == 82
        assert sc.piotroski_f_score == 7
        assert sc.altman_z_score == 3.5
        assert sc.gf_value_discount_pct == 20.0

    def test_handles_empty_response(self, gf):
        sc = gf.parse_qgarp_scorecard("AAPL", {})
        assert sc.ticker == "AAPL"
        assert sc.total_score == 0
        assert sc.piotroski_f_score == 0

    def test_handles_none_response(self, gf):
        sc = gf.parse_qgarp_scorecard("MSFT", None)
        assert sc.ticker == "MSFT"
        assert sc.total_score == 0

    def test_alternative_key_gf_score(self, gf):
        """Should accept 'gf_score' as fallback for 'total_score'."""
        raw = {"gf_score": 75}
        sc = gf.parse_qgarp_scorecard("AAPL", raw)
        assert sc.total_score == 75


# ═══════════════════════════════════════════════════════════
# Insider Conviction
# ═══════════════════════════════════════════════════════════

class TestInsiderConviction:
    def test_parses_cluster_buying_list(self, gf):
        """Cluster data as list of events."""
        cluster = [
            {"type": "buy", "value": 500000, "insider": "CEO"},
            {"type": "buy", "value": 200000, "insider": "CFO"},
            {"type": "buy", "value": 100000, "insider": "COO"},
        ]
        ic = gf.parse_insider_conviction("AAPL", cluster_data=cluster)
        assert ic.ticker == "AAPL"
        assert ic.conviction_score > 0
        assert ic.cluster_buys == 3
        assert ic.net_insider_sentiment in ("strong_buy", "buy", "neutral", "sell")

    def test_parses_cluster_buying_dict(self, gf):
        """Cluster data as dict with 'data' key."""
        cluster = {"data": [{"insider": "CEO"}, {"insider": "CFO"}]}
        ic = gf.parse_insider_conviction("AAPL", cluster_data=cluster)
        assert ic.cluster_buys == 2
        assert ic.conviction_score > 0

    def test_handles_empty_data(self, gf):
        ic = gf.parse_insider_conviction("AAPL", cluster_data={})
        assert ic.ticker == "AAPL"
        assert ic.conviction_score == 0

    def test_handles_no_data(self, gf):
        ic = gf.parse_insider_conviction("AAPL")
        assert ic.ticker == "AAPL"
        assert ic.conviction_score == 0
        assert ic.net_insider_sentiment == "neutral"

    def test_ceo_cfo_combined(self, gf):
        ceo = [{"insider": "CEO", "action": "buy"}]
        cfo = [{"insider": "CFO", "action": "buy"}]
        ic = gf.parse_insider_conviction("MSFT", ceo_data=ceo, cfo_data=cfo)
        assert ic.ceo_buys == 1
        assert ic.cfo_buys == 1
        assert ic.total_insider_buys == 2


# ═══════════════════════════════════════════════════════════
# Guru Tracking
# ═══════════════════════════════════════════════════════════

class TestGuruTracking:
    def test_parses_accumulation(self, gf):
        raw = [
            {"name": "Buffett", "action": "buy", "shares": 1000000},
            {"name": "Ackman", "action": "add", "shares": 500000},
        ]
        gt = gf.parse_guru_tracking("AAPL", gurus_data=raw)
        assert gt.ticker == "AAPL"
        assert gt.accumulation is True
        assert gt.guru_count == 2
        assert gt.net_buying_score > 0

    def test_handles_selling(self, gf):
        raw = [
            {"name": "Soros", "action": "sell", "shares": 1000000},
            {"name": "Druckenmiller", "action": "reduce", "shares": 500000},
        ]
        gt = gf.parse_guru_tracking("TSLA", gurus_data=raw)
        assert gt.accumulation is False
        assert gt.net_buying_score < 0

    def test_handles_empty(self, gf):
        gt = gf.parse_guru_tracking("AAPL", gurus_data={})
        assert gt.ticker == "AAPL"
        assert gt.accumulation is False
        assert gt.guru_count == 0


# ═══════════════════════════════════════════════════════════
# Quality Gate
# ═══════════════════════════════════════════════════════════

class TestQualityGate:
    def test_passes_healthy_stock(self, gf):
        metrics = {"piotroski_f_score": 7, "altman_z_score": 4.0}
        passes, reason = gf.passes_quality_gate(metrics)
        assert passes is True
        assert reason == "OK"

    def test_rejects_bankrupt_stock(self, gf):
        metrics = {"piotroski_f_score": 2, "altman_z_score": 0.5}
        passes, reason = gf.passes_quality_gate(metrics)
        assert passes is False
        assert "Altman" in reason or "Piotroski" in reason

    def test_rejects_low_piotroski(self, gf):
        metrics = {"piotroski_f_score": 1, "altman_z_score": 3.0}
        passes, reason = gf.passes_quality_gate(metrics)
        assert passes is False
        assert "Piotroski" in reason

    def test_passes_missing_data(self, gf):
        """Missing data should pass (benefit of the doubt)."""
        passes, reason = gf.passes_quality_gate({})
        assert passes is True


# ═══════════════════════════════════════════════════════════
# Risk Matrix 5D
# ═══════════════════════════════════════════════════════════

class TestRiskMatrix:
    def test_all_green(self, gf):
        raw = {
            "financial_risk": "GREEN", "quality_risk": "GREEN",
            "growth_risk": "GREEN", "valuation_risk": "GREEN",
            "market_risk": "GREEN",
        }
        rm = gf.parse_risk_matrix("AAPL", raw)
        assert rm.risk_score == 100.0

    def test_all_red(self, gf):
        raw = {
            "financial_risk": "RED", "quality_risk": "RED",
            "growth_risk": "RED", "valuation_risk": "RED",
            "market_risk": "RED",
        }
        rm = gf.parse_risk_matrix("JUNK", raw)
        assert rm.risk_score == 0.0

    def test_mixed_risk(self, gf):
        raw = {
            "financial_risk": "GREEN", "quality_risk": "YELLOW",
            "growth_risk": "RED", "valuation_risk": "GREEN",
            "market_risk": "YELLOW",
        }
        rm = gf.parse_risk_matrix("MIXED", raw)
        assert 0 < rm.risk_score < 100


# ═══════════════════════════════════════════════════════════
# Analyst Intelligence
# ═══════════════════════════════════════════════════════════

class TestAnalystIntelligence:
    def test_strong_buy_consensus(self, gf):
        raw = {"consensus": 1, "price_target_mean": 200, "current_price": 150}
        ai = gf.parse_analyst_intelligence("AAPL", estimates_data=raw)
        assert ai.consensus == "strong_buy"
        assert ai.price_target_upside_pct > 30

    def test_hold_consensus(self, gf):
        raw = {"consensus": 3}
        ai = gf.parse_analyst_intelligence("MSFT", estimates_data=raw)
        assert ai.consensus == "hold"

    def test_handles_empty(self, gf):
        ai = gf.parse_analyst_intelligence("TSLA", estimates_data={})
        assert ai.consensus == "hold"
