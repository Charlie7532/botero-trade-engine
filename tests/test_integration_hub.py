"""
Tests para EntryIntelligenceHub — Verifica que el hub conecta
correctamente todos los módulos existentes y nuevos.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock
from datetime import datetime, date, UTC

from application.entry_intelligence_hub import EntryIntelligenceHub, EntryIntelligenceReport


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _make_prices(n=60, base=200, trend="up"):
    """Generate synthetic price data for testing."""
    close = [base]
    if trend == "up":
        # Gentle uptrend then pullback (correction setup)
        for i in range(1, 45):
            close.append(close[-1] * 1.002)
        for i in range(45, n):
            if i % 5 in (0, 3):
                close.append(close[-1] * 1.0015)
            else:
                close.append(close[-1] * 0.9985)
    elif trend == "parabolic":
        for i in range(1, n):
            close.append(close[-1] * 1.018)
    elif trend == "flat":
        np.random.seed(42)
        close = list(base + np.random.randn(n) * 0.5)
    close = np.array(close)
    high = close * 1.004
    low = close * 0.996
    vol = np.ones(n) * 1_000_000
    if trend == "up":
        vol[-10:] = 200_000
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": vol})


def _mock_options_data():
    return {
        "put_wall": 195.0,
        "call_wall": 215.0,
        "gamma_regime": "PIN",
        "max_pain": 200.0,
    }


def _mock_kalman_result():
    return {
        "wyckoff_state": "ACCUMULATION",
        "velocity": 0.05,
        "rel_vol": 0.4,
        "acceleration": 0.01,
        "confidence": 0.85,
    }


# ═══════════════════════════════════════════════════════════════
# TEST: Hub Initialization
# ═══════════════════════════════════════════════════════════════

class TestHubInit:
    def test_hub_creates_decision_modules(self):
        hub = EntryIntelligenceHub()
        assert hub.event_flow is not None
        assert hub.price_phase is not None

    def test_hub_lazy_inits_data_providers(self):
        hub = EntryIntelligenceHub()
        # Before accessing, they should be None
        assert hub._options is None
        assert hub._kalman is None
        assert hub._uw is None

    def test_uw_data_injection(self):
        hub = EntryIntelligenceHub()
        hub.inject_uw_data(
            spy_ticks=[{"delta": 100}],
            flow_alerts=[{"ticker": "AAPL"}],
            tide_data=[{"premium": 5_000_000}],
        )
        assert len(hub._uw_data_cache["spy_ticks"]) == 1
        assert len(hub._uw_data_cache["flow_alerts"]) == 1
        assert len(hub._uw_data_cache["tide_data"]) == 1


# ═══════════════════════════════════════════════════════════════
# TEST: Full Pipeline Integration
# ═══════════════════════════════════════════════════════════════

class TestHubEvaluate:
    """Tests evaluate() with mocked data providers."""

    def _make_hub_with_mocks(self):
        hub = EntryIntelligenceHub()

        # Mock options
        mock_opts = MagicMock()
        mock_opts.get_full_analysis.return_value = _mock_options_data()
        hub._options = mock_opts

        # Mock Kalman (needs sequential updates, so we mock the final result)
        mock_kalman = MagicMock()
        mock_kalman.update.return_value = _mock_kalman_result()
        hub._kalman = mock_kalman

        # Mock UW (returns empty since no MCP data)
        mock_uw = MagicMock()
        mock_uw.parse_spy_macro_gate.return_value = MagicMock(
            cum_delta=500_000, signal="STAY_IN", confidence=0.75,
            am_pm_diverges=False, last_updated="2023-10-27T10:00:00Z"
        )
        mock_uw.parse_market_tide.return_value = MagicMock(
            tide_direction="BULLISH", is_accelerating=True,
            cum_net_premium=8_000_000, last_updated="2023-10-27T10:05:00Z"
        )
        mock_uw.parse_flow_alerts.return_value = MagicMock(
            n_sweeps=12, n_calls=15, n_puts=5, last_updated="2023-10-27T10:01:00Z"
        )
        mock_uw.parse_market_sentiment.return_value = MagicMock(
            regime="BULL", breadth_pct=65, last_updated="2023-10-27T10:00:00Z"
        )
        hub._uw = mock_uw

        # V7: Mock journal to avoid real DB + provide empty vector search
        mock_journal = MagicMock()
        mock_journal.find_similar_trades.return_value = []
        hub.journal = mock_journal

        # V7: Inject recent_flow with a fresh timestamp to bypass DEAD_SIGNAL
        from datetime import datetime, UTC
        fresh_ts = datetime.now(UTC).isoformat()
        hub.inject_uw_data(
            spy_ticks=[{"delta": 500_000}],
            flow_alerts=[{"ticker": "TEST"}],
            tide_data=[{"premium": 8_000_000}],
            recent_flow=[
                {"timestamp": fresh_ts, "option_type": "CALL", "side": "ASK", "ticker": "TEST"},
                {"timestamp": fresh_ts, "option_type": "CALL", "side": "ASK", "ticker": "TEST"},
            ],
            darkpool_prints=[],
        )

        return hub

    @patch.object(EntryIntelligenceHub, '_fetch_vix', return_value=19.0)
    @patch.object(EntryIntelligenceHub, '_calc_rs_vs_spy', return_value=1.12)
    def test_correction_with_accumulation_and_bullish_flow(self, mock_rs, mock_vix):
        """
        Full pipeline: correction prices + ACCUMULATION Wyckoff +
        BULLISH whale flow → should produce a high-conviction report.
        """
        hub = self._make_hub_with_mocks()
        # V7: recent_flow already injected by _make_hub_with_mocks

        prices = _make_prices(trend="up")
        report = hub.evaluate("TEST", prices_df=prices)

        assert isinstance(report, EntryIntelligenceReport)
        assert report.ticker == "TEST"
        assert report.gamma_regime == "PIN"
        assert report.wyckoff_state == "ACCUMULATION"
        assert report.put_wall == 195.0
        assert report.call_wall == 215.0
        assert report.tide_direction == "BULLISH"
        assert report.vix == 19.0
        # Phase should be CORRECTION or similar with these inputs
        assert report.phase in ("CORRECTION", "CONSOLIDATION", "BREAKOUT")

    @patch.object(EntryIntelligenceHub, '_fetch_vix', return_value=28.0)
    @patch.object(EntryIntelligenceHub, '_calc_rs_vs_spy', return_value=0.85)
    def test_exhaustion_is_blocked(self, mock_rs, mock_vix):
        """Parabolic extension should produce BLOCK verdict."""
        hub = self._make_hub_with_mocks()
        prices = _make_prices(trend="parabolic")
        report = hub.evaluate("TEST", prices_df=prices)

        assert report.phase == "EXHAUSTION_UP"
        assert report.final_verdict == "BLOCK"
        assert report.final_scale == 0.0

    @patch.object(EntryIntelligenceHub, '_fetch_vix', return_value=18.0)
    @patch.object(EntryIntelligenceHub, '_calc_rs_vs_spy', return_value=1.0)
    def test_consolidation_is_stalk(self, mock_rs, mock_vix):
        """Flat sideways price should produce STALK."""
        hub = self._make_hub_with_mocks()
        prices = _make_prices(trend="flat")
        report = hub.evaluate("TEST", prices_df=prices)

        # Flat prices = CONSOLIDATION → STALK
        assert report.phase in ("CONSOLIDATION", "CORRECTION")
        assert report.final_verdict in ("STALK", "PASS")

    @patch.object(EntryIntelligenceHub, '_fetch_vix', return_value=18.0)
    @patch.object(EntryIntelligenceHub, '_calc_rs_vs_spy', return_value=1.0)
    def test_report_has_all_fields(self, mock_rs, mock_vix):
        """Verify report contains data from all connected modules."""
        hub = self._make_hub_with_mocks()
        # recent_flow already injected by _make_hub_with_mocks

        prices = _make_prices(trend="up")
        report = hub.evaluate("TEST", prices_df=prices)
        d = report.to_dict()

        # Verify all source modules contributed
        assert d["gamma_regime"] != "UNKNOWN"  # from options_awareness
        assert d["wyckoff_state"] != "UNKNOWN"  # from volume_dynamics
        assert d["tide_direction"] != "NEUTRAL"  # from uw_intelligence
        assert d["whale_verdict"] != "UNKNOWN"  # from event_flow_intelligence
        assert d["phase"] != "UNKNOWN"  # from price_phase_intelligence
        assert d["vix"] > 0  # from yfinance
        assert d["final_verdict"] in ("EXECUTE", "STALK", "BLOCK", "PASS")

    @patch.object(EntryIntelligenceHub, '_fetch_vix', return_value=18.0)
    @patch.object(EntryIntelligenceHub, '_calc_rs_vs_spy', return_value=1.0)
    def test_empty_prices_returns_pass(self, mock_rs, mock_vix):
        """Empty prices → PASS (no data to diagnose)."""
        hub = self._make_hub_with_mocks()
        report = hub.evaluate("TEST", prices_df=pd.DataFrame())

        assert report.final_verdict == "PASS"
        assert "datos de precio" in report.final_reason.lower() or "no se" in report.final_reason.lower()


# ═══════════════════════════════════════════════════════════════
# TEST: Data Provider Connections
# ═══════════════════════════════════════════════════════════════

class TestDataProviderConnections:
    def test_options_data_flows_to_phase(self):
        """Verify options data (put_wall, call_wall, gamma_regime)
        flows from OptionsAwareness → PricePhaseIntelligence."""
        hub = EntryIntelligenceHub()
        mock_opts = MagicMock()
        mock_opts.get_full_analysis.return_value = {
            "put_wall": 180.0,
            "call_wall": 220.0,
            "gamma_regime": "SQUEEZE_UP",
            "max_pain": 195.0,
        }
        hub._options = mock_opts

        result = hub._fetch_options_data("TEST")
        assert result["put_wall"] == 180.0
        assert result["call_wall"] == 220.0
        assert result["gamma_regime"] == "SQUEEZE_UP"

    def test_kalman_processes_volume_data(self):
        """Verify Kalman tracker processes price volume into wyckoff states."""
        hub = EntryIntelligenceHub()
        hub._kalman = hub._get_kalman()  # Real Kalman
        if hub._kalman is None:
            pytest.skip("KalmanVolumeTracker not available")

        prices = _make_prices(trend="up")
        result = hub._run_kalman("TEST", prices)

        assert "wyckoff_state" in result
        assert "velocity" in result
        assert result["wyckoff_state"] in (
            "ACCUMULATION", "MARKUP", "DISTRIBUTION",
            "MARKDOWN", "CONSOLIDATION", "UNKNOWN",
        )

    def test_uw_data_injection_and_parsing(self):
        """Verify UW data flows through injection → parse → report."""
        hub = EntryIntelligenceHub()
        hub._uw = hub._get_uw()
        if hub._uw is None:
            pytest.skip("UnusualWhalesIntelligence not available")

        # Even with empty data, parsing should not crash
        hub.inject_uw_data(spy_ticks=[], flow_alerts=[], tide_data=[])
        result = hub._parse_whale_flow("TEST")
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════
# TEST: Orchestrator Integration
# ═══════════════════════════════════════════════════════════════

class TestOrchestratorIntegration:
    def test_orchestrator_has_entry_hub(self):
        """PaperTradingOrchestrator should have EntryIntelligenceHub."""
        # Import from backend context
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))
        from application.paper_trading import PaperTradingOrchestrator

        orch = PaperTradingOrchestrator()
        assert hasattr(orch, 'entry_hub')
        assert isinstance(orch.entry_hub, EntryIntelligenceHub)

    def test_orchestrator_has_freeze_state(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))
        from application.paper_trading import PaperTradingOrchestrator

        orch = PaperTradingOrchestrator()
        assert hasattr(orch, '_freeze_state')
        assert isinstance(orch._freeze_state, dict)

    def test_inject_whale_data_method_exists(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))
        from application.paper_trading import PaperTradingOrchestrator

        orch = PaperTradingOrchestrator()
        assert hasattr(orch, 'inject_whale_data')
        # Should not crash
        orch.inject_whale_data(spy_ticks=[], flow_alerts=[], tide_data=[])
