"""
Tests for Unusual Whales Intelligence Adapter
==============================================
Validates the 4 parsers (FlowSignal, MacroGate, MarketSentiment, MarketTide)
using mock data that mirrors real API responses from forensic validation.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.infrastructure.data_providers.uw_intelligence import (
    UnusualWhalesIntelligence,
    FlowSignal,
    MacroGate,
    MarketSentiment,
    MarketTide,
)


@pytest.fixture
def uw():
    return UnusualWhalesIntelligence()


# ================================================================
# MOCK DATA — mirrors real UW API responses
# ================================================================

def _make_alert(ticker, alert_type='call', has_sweep=False, premium=100_000,
                voi=1.5, ask_prem=60_000, bid_prem=40_000, trade_count=5):
    return {
        'ticker': ticker,
        'type': alert_type,
        'has_sweep': has_sweep,
        'total_premium': premium,
        'volume_oi_ratio': voi,
        'total_ask_side_prem': ask_prem,
        'total_bid_side_prem': bid_prem,
        'trade_count': trade_count,
    }


def _make_spy_tick(net_delta=100_000, call_prem=500_000, put_prem=300_000,
                   call_vol=1000, put_vol=800):
    return {
        'tape_time': '2026-04-17T10:00:00',
        'net_delta': net_delta,
        'net_call_premium': call_prem,
        'net_put_premium': put_prem,
        'call_volume': call_vol,
        'put_volume': put_vol,
    }


def _make_tide_bar(call_prem=1_000_000, put_prem=800_000, net_vol=5000):
    return {
        'timestamp': '2026-04-17T10:00:00',
        'date': '2026-04-17',
        'net_call_premium': call_prem,
        'net_put_premium': put_prem,
        'net_volume': net_vol,
    }


# ================================================================
# FLOW SIGNAL TESTS
# ================================================================

class TestFlowSignal:
    """Tests for parse_flow_alerts — per-ticker scoring."""

    def test_empty_alerts_returns_neutral(self, uw):
        """No alerts → neutral score (50)."""
        signal = uw.parse_flow_alerts('AAPL', [])
        assert signal.ticker == 'AAPL'
        assert signal.flow_score == 50.0
        assert signal.n_sweeps == 0

    def test_high_conviction_signal(self, uw):
        """Call sweeps + high VOI + high premium → high score."""
        alerts = [
            _make_alert('NVDA', 'call', has_sweep=True, premium=800_000, voi=3.5, ask_prem=600_000, bid_prem=200_000),
            _make_alert('NVDA', 'call', has_sweep=True, premium=500_000, voi=2.1, ask_prem=400_000, bid_prem=100_000),
            _make_alert('NVDA', 'call', has_sweep=False, premium=200_000, voi=1.2),
        ]
        signal = uw.parse_flow_alerts('NVDA', alerts)

        assert signal.n_calls == 3
        assert signal.n_puts == 0
        assert signal.n_sweeps == 2
        assert signal.call_put_ratio > 1.0
        # Score breakdown: sweeps(40) + VOI>2(20) + calls>puts(15) + ask>bid(10) + premium>500K(7) = 92
        assert signal.flow_score >= 85, f"High conviction should score ≥85, got {signal.flow_score}"

    def test_low_conviction_no_sweeps(self, uw):
        """Calls but no sweeps, low VOI → moderate-low score."""
        alerts = [
            _make_alert('AAPL', 'call', has_sweep=False, premium=50_000, voi=0.3),
            _make_alert('AAPL', 'put', has_sweep=False, premium=40_000, voi=0.4),
        ]
        signal = uw.parse_flow_alerts('AAPL', alerts)

        assert signal.n_sweeps == 0
        # No sweeps(0) + VOI<0.5(0) + calls≈puts(3-5) + ...
        assert signal.flow_score < 30, f"Low conviction should score <30, got {signal.flow_score}"

    def test_bearish_flow(self, uw):
        """Put-dominant alerts → low score."""
        alerts = [
            _make_alert('SPY', 'put', premium=300_000, voi=2.0),
            _make_alert('SPY', 'put', premium=200_000, voi=1.5),
            _make_alert('SPY', 'call', premium=50_000, voi=0.5),
        ]
        signal = uw.parse_flow_alerts('SPY', alerts)

        assert signal.n_puts > signal.n_calls
        assert signal.call_put_ratio < 1.0
        # Puts dominate → no call dominance bonus
        assert signal.flow_score < 50

    def test_sweep_is_dominant_factor(self, uw):
        """Sweep presence alone should add 40 points (validated: 83.9% of misses had 0)."""
        no_sweep = uw.parse_flow_alerts('A', [
            _make_alert('A', 'call', has_sweep=False, premium=100_000, voi=1.5),
        ])
        with_sweep = uw.parse_flow_alerts('B', [
            _make_alert('B', 'call', has_sweep=True, premium=100_000, voi=1.5),
        ])
        
        diff = with_sweep.flow_score - no_sweep.flow_score
        assert diff >= 35, f"Sweep should add ≥35 points, added {diff}"

    def test_score_caps_at_100(self, uw):
        """Score should never exceed 100."""
        alerts = [
            _make_alert('X', 'call', has_sweep=True, premium=5_000_000, voi=10.0,
                        ask_prem=4_000_000, bid_prem=500_000),
        ] * 5
        signal = uw.parse_flow_alerts('X', alerts)
        assert signal.flow_score <= 100


# ================================================================
# MACRO GATE TESTS
# ================================================================

class TestMacroGate:
    """Tests for parse_spy_macro_gate — adaptive SPY risk posture."""

    def test_empty_ticks_returns_neutral(self, uw):
        gate = uw.parse_spy_macro_gate([])
        assert gate.signal == "NEUTRAL"
        assert gate.position_scale_factor == 1.0

    def test_strong_bullish_delta(self, uw):
        """Strong positive delta across all ticks → STAY_IN or FULL_IN."""
        ticks = [_make_spy_tick(net_delta=200_000, call_prem=1_000_000, put_prem=200_000,
                                call_vol=2000, put_vol=800)] * 20
        gate = uw.parse_spy_macro_gate(ticks)

        assert gate.cum_delta > 0
        assert gate.composite_score > 0
        assert gate.signal in ("STAY_IN", "FULL_IN")
        assert gate.position_scale_factor >= 1.0

    def test_strong_bearish_delta(self, uw):
        """Strong negative delta → REDUCE or EXIT."""
        ticks = [_make_spy_tick(net_delta=-300_000, call_prem=200_000, put_prem=1_000_000,
                                call_vol=500, put_vol=2000)] * 20
        gate = uw.parse_spy_macro_gate(ticks)

        assert gate.cum_delta < 0
        assert gate.composite_score < 0
        assert gate.signal in ("REDUCE", "EXIT")
        assert gate.position_scale_factor < 1.0

    def test_am_pm_divergence_detection(self, uw):
        """AM bullish + PM bearish → divergence flag + scale reduction."""
        morning = [_make_spy_tick(net_delta=500_000)] * 10
        afternoon = [_make_spy_tick(net_delta=-600_000)] * 10
        ticks = morning + afternoon

        gate = uw.parse_spy_macro_gate(ticks)

        assert gate.am_pm_diverges is True
        assert gate.morning_delta > 0
        assert gate.afternoon_delta < 0
        # Divergence should force at least REDUCE
        assert gate.signal in ("REDUCE", "EXIT", "NEUTRAL")
        # Scaling should be reduced
        assert gate.position_scale_factor < 1.0

    def test_adaptive_scaling_is_graduated(self, uw):
        """Verify scaling is graduated, not binary."""
        # Mildly bearish
        mild = uw.parse_spy_macro_gate(
            [_make_spy_tick(net_delta=-60_000, call_vol=900, put_vol=1100)] * 10
        )
        # Strongly bearish
        strong = uw.parse_spy_macro_gate(
            [_make_spy_tick(net_delta=-800_000, call_prem=100_000, put_prem=2_000_000,
                            call_vol=300, put_vol=3000)] * 20
        )

        # Strong bearish should have lower scale than mild
        assert strong.position_scale_factor < mild.position_scale_factor
        # But neither should be exactly 0.5 (that would be binary)
        assert mild.position_scale_factor != 0.5
        assert strong.position_scale_factor != 0.5

    def test_confidence_reflects_agreement(self, uw):
        """When all components agree, confidence should be high."""
        # All components bullish
        ticks = [_make_spy_tick(net_delta=500_000, call_prem=2_000_000, put_prem=100_000,
                                call_vol=3000, put_vol=800)] * 20
        gate = uw.parse_spy_macro_gate(ticks)
        assert gate.confidence >= 0.7


# ================================================================
# MARKET SENTIMENT TESTS
# ================================================================

class TestMarketSentiment:
    """Tests for parse_market_sentiment — market-wide regime detection."""

    def test_empty_alerts_neutral(self, uw):
        sent = uw.parse_market_sentiment([])
        assert sent.regime == "NEUTRAL"
        assert sent.sentiment_score == 0

    def test_bullish_market(self, uw):
        """Call-dominant alerts across multiple tickers → BULL."""
        alerts = []
        for ticker in ['AAPL', 'NVDA', 'MSFT', 'AMD', 'META', 'GOOG', 'TSLA', 'AMZN']:
            alerts.append(_make_alert(ticker, 'call', has_sweep=True, premium=500_000))
            alerts.append(_make_alert(ticker, 'call', premium=200_000))
        # A few puts
        alerts.append(_make_alert('SPY', 'put', premium=100_000))
        alerts.append(_make_alert('QQQ', 'put', premium=100_000))

        sent = uw.parse_market_sentiment(alerts)

        assert sent.pcr_alerts < 0.8  # Low PCR = bullish
        assert sent.breadth_pct > 60
        assert sent.regime == "BULL"
        assert sent.sentiment_score >= 3

    def test_bearish_market(self, uw):
        """Put-dominant + sweep puts → BEAR."""
        alerts = []
        for ticker in ['AAPL', 'NVDA', 'MSFT', 'AMD', 'META']:
            alerts.append(_make_alert(ticker, 'put', has_sweep=True))
            alerts.append(_make_alert(ticker, 'put'))
        alerts.append(_make_alert('GOOG', 'call'))

        sent = uw.parse_market_sentiment(alerts)

        assert sent.pcr_alerts > 1.0
        assert sent.breadth_pct < 40
        assert sent.regime == "BEAR"

    def test_breadth_calculation(self, uw):
        """Breadth = % tickers with more call alerts than put alerts."""
        alerts = [
            _make_alert('A', 'call'), _make_alert('A', 'call'),  # A: bullish
            _make_alert('B', 'put'), _make_alert('B', 'put'),    # B: bearish
            _make_alert('C', 'call'),                            # C: bullish
            _make_alert('D', 'put'),                             # D: bearish
        ]
        sent = uw.parse_market_sentiment(alerts)
        # 2 out of 4 tickers bullish = 50%
        assert 45 <= sent.breadth_pct <= 55


# ================================================================
# MARKET TIDE TESTS
# ================================================================

class TestMarketTide:
    """Tests for parse_market_tide — real-time premium flow."""

    def test_empty_tide(self, uw):
        tide = uw.parse_market_tide([])
        assert tide.tide_direction == "NEUTRAL"
        assert tide.n_bars == 0

    def test_bullish_tide(self, uw):
        bars = [_make_tide_bar(call_prem=2_000_000, put_prem=500_000)] * 10
        tide = uw.parse_market_tide(bars)

        assert tide.cum_net_premium > 0
        assert tide.tide_direction == "BULLISH"
        assert tide.n_bars == 10

    def test_bearish_tide(self, uw):
        bars = [_make_tide_bar(call_prem=300_000, put_prem=2_000_000)] * 10
        tide = uw.parse_market_tide(bars)

        assert tide.cum_net_premium < 0
        assert tide.tide_direction == "BEARISH"

    def test_acceleration_detection(self, uw):
        """If second half flow is stronger than first half → accelerating."""
        first_half = [_make_tide_bar(call_prem=1_000_000, put_prem=500_000)] * 5
        second_half = [_make_tide_bar(call_prem=3_000_000, put_prem=500_000)] * 5
        bars = first_half + second_half

        tide = uw.parse_market_tide(bars)
        assert tide.is_accelerating is True


# ================================================================
# EXTRACT TICKER SIGNALS (batch utility)
# ================================================================

class TestExtractTickerSignals:
    """Tests for extract_ticker_signals — batch processing."""

    def test_extracts_matching_tickers(self, uw):
        alerts = [
            _make_alert('AAPL', 'call', has_sweep=True),
            _make_alert('AAPL', 'call'),
            _make_alert('NVDA', 'put'),
            _make_alert('TSLA', 'call', has_sweep=True),
        ]
        signals = uw.extract_ticker_signals(alerts, ['AAPL', 'NVDA', 'MSFT'])

        assert 'AAPL' in signals
        assert 'NVDA' in signals
        assert 'MSFT' in signals  # present but empty
        assert signals['AAPL'].n_calls == 2
        assert signals['AAPL'].n_sweeps == 1
        assert signals['MSFT'].flow_score == 50.0  # neutral (no data)
        assert 'TSLA' not in signals  # not requested


# ================================================================
# ADAPTIVE WEIGHT MANAGER TESTS
# ================================================================

class TestAdaptiveWeightManager:
    """Tests for AdaptiveWeightManager — dynamic weight adjustment."""

    def test_initial_weights_sum_to_one(self):
        from backend.application.alpha_scanner import AdaptiveWeightManager
        mgr = AdaptiveWeightManager()
        total = sum(mgr.weights.values())
        assert abs(total - 1.0) < 0.01, f"Weights should sum to ~1.0, got {total}"

    def test_successful_component_gains_weight(self):
        from backend.application.alpha_scanner import AdaptiveWeightManager
        mgr = AdaptiveWeightManager()
        initial = mgr.weights['uw_flow_score']

        for _ in range(10):
            mgr.update_effectiveness('uw_flow_score', was_correct=True)

        updated = mgr.weights['uw_flow_score']
        assert updated > initial, f"Successful component should gain weight: {initial} → {updated}"

    def test_failing_component_loses_weight(self):
        from backend.application.alpha_scanner import AdaptiveWeightManager
        mgr = AdaptiveWeightManager()
        initial = mgr.weights['analyst_score']

        for _ in range(10):
            mgr.update_effectiveness('analyst_score', was_correct=False)

        updated = mgr.weights['analyst_score']
        assert updated < initial, f"Failing component should lose weight: {initial} → {updated}"

    def test_weights_bounded(self):
        from backend.application.alpha_scanner import AdaptiveWeightManager
        mgr = AdaptiveWeightManager()

        # Push one component to extreme
        for _ in range(100):
            mgr.update_effectiveness('rs_vs_spy', was_correct=True)

        w = mgr.weights
        for component, weight in w.items():
            assert weight >= 0.01, f"{component} weight below floor: {weight}"
            assert weight <= 0.50, f"{component} weight above ceiling: {weight}"

    def test_weights_always_normalize(self):
        from backend.application.alpha_scanner import AdaptiveWeightManager
        mgr = AdaptiveWeightManager()

        for _ in range(20):
            mgr.update_effectiveness('rs_vs_spy', was_correct=True)
            mgr.update_effectiveness('uw_flow_score', was_correct=False)

        total = sum(mgr.weights.values())
        assert abs(total - 1.0) < 0.01, f"Weights must always normalize to ~1.0, got {total}"


# ================================================================
# RISK GUARDIAN INTEGRATION TESTS
# ================================================================

class TestRiskGuardianMacroGate:
    """Tests for RiskGuardian with macro_gate and market_sentiment."""

    def test_macro_gate_exit_reduces_scale(self):
        from backend.application.portfolio_intelligence import RiskGuardian
        rg = RiskGuardian()
        rg._peak_capital = 100_000

        gate = MacroGate(
            composite_score=-4,
            signal='EXIT',
            position_scale_factor=0.60,
            am_pm_diverges=True,
            confidence=0.9,
        )

        result = rg.evaluate(
            current_capital=100_000,
            daily_pnl_pct=0.0,
            macro_gate=gate,
        )

        assert result['position_scale'] <= 0.65
        assert any('EXIT' in a for a in result['alerts'])

    def test_macro_gate_full_in_no_exceed_one(self):
        from backend.application.portfolio_intelligence import RiskGuardian
        rg = RiskGuardian()
        rg._peak_capital = 100_000

        gate = MacroGate(
            composite_score=4,
            signal='FULL_IN',
            position_scale_factor=1.10,
            confidence=0.9,
        )

        result = rg.evaluate(
            current_capital=100_000,
            daily_pnl_pct=0.0,
            macro_gate=gate,
        )

        assert result['position_scale'] <= 1.0

    def test_sentiment_bear_reduces_scale(self):
        from backend.application.portfolio_intelligence import RiskGuardian
        rg = RiskGuardian()
        rg._peak_capital = 100_000

        sent = MarketSentiment(
            regime='BEAR',
            sentiment_score=-3,
            breadth_pct=30.0,
        )

        result = rg.evaluate(
            current_capital=100_000,
            daily_pnl_pct=0.0,
            market_sentiment=sent,
        )

        assert result['position_scale'] < 1.0
        assert any('BEARISH' in a for a in result['alerts'])

    def test_no_uw_data_is_neutral(self):
        """Without UW data, RiskGuardian should behave exactly as before."""
        from backend.application.portfolio_intelligence import RiskGuardian
        rg = RiskGuardian()
        rg._peak_capital = 100_000

        result = rg.evaluate(
            current_capital=100_000,
            daily_pnl_pct=0.0,
        )

        assert result['position_scale'] == 1.0
        assert result['can_trade'] is True

    def test_macro_gate_dict_format(self):
        """RiskGuardian should accept dict format (from JSON serialization)."""
        from backend.application.portfolio_intelligence import RiskGuardian
        rg = RiskGuardian()
        rg._peak_capital = 100_000

        gate_dict = {
            'composite_score': -3,
            'signal': 'REDUCE',
            'position_scale_factor': 0.75,
            'am_pm_diverges': True,
            'confidence': 0.6,
        }

        result = rg.evaluate(
            current_capital=100_000,
            daily_pnl_pct=0.0,
            macro_gate=gate_dict,
        )

        assert result['position_scale'] < 1.0
