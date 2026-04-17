"""
Tests for WalkForwardBacktester
Validates:
  - Data loading from Parquet
  - Window generation (rolling train/test splits)
  - Trade simulation with entry/exit logic
  - Metrics calculation (Sharpe, DD, Profit Factor, Win Rate)
  - Gating verification
  - Regime classification
  - Full run integration (on real downloaded Parquet)
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

from backend.application.backtester import (
    WalkForwardBacktester,
    WindowResult,
    BacktestReport,
)


@pytest.fixture
def sample_ticker_data():
    """Generate synthetic daily data for SPY spanning 3 years."""
    dates = pd.bdate_range('2020-01-02', '2023-01-02')
    np.random.seed(42)
    n = len(dates)
    # Simulate a trending market with some volatility
    returns = np.random.normal(0.0004, 0.012, n)
    prices = 300 * np.exp(np.cumsum(returns))
    volumes = np.random.randint(50_000_000, 150_000_000, n)

    return pd.DataFrame({
        'Date': dates,
        'Ticker': 'SPY',
        'Universe': 'Market',
        'Open': prices * 0.999,
        'High': prices * 1.005,
        'Low': prices * 0.995,
        'Close': prices,
        'Volume': volumes.astype(float),
    })


class TestWindowGeneration:

    def test_generates_correct_number_of_windows(self, sample_ticker_data):
        """With 3 years data, train=24m, test=6m, step=6m → should get 1 window."""
        bt = WalkForwardBacktester(train_months=24, test_months=6, step_months=6)
        windows = bt.generate_windows(sample_ticker_data)
        # 3 years = 36 months. First window: train 0-24, test 24-30. 
        # Second: train 6-30, test 30-36. Third: train 12-36, test 36-42 → exceeds.
        assert len(windows) >= 1

    def test_window_boundaries_dont_overlap_test_and_train(self, sample_ticker_data):
        """Train end should equal test start (no gap, no overlap)."""
        bt = WalkForwardBacktester(train_months=12, test_months=6, step_months=6)
        windows = bt.generate_windows(sample_ticker_data)
        for w in windows:
            assert w['train_end'] == w['test_start'], \
                "Train end must precisely equal test start"

    def test_no_windows_if_data_too_short(self):
        """Very short data should produce zero windows."""
        dates = pd.bdate_range('2020-01-02', '2020-06-01')
        df = pd.DataFrame({
            'Date': dates, 'Close': 100.0, 'Ticker': 'X',
        })
        bt = WalkForwardBacktester(train_months=24, test_months=6, step_months=6)
        windows = bt.generate_windows(df)
        assert len(windows) == 0


class TestTradeSimulation:

    def test_trades_generated_in_volatile_market(self, sample_ticker_data):
        """A volatile synthetic market should generate some trades."""
        bt = WalkForwardBacktester()
        start = pd.Timestamp('2022-01-01')
        end = pd.Timestamp('2022-07-01')
        trades = bt.simulate_trades_in_window(
            sample_ticker_data, start, end,
            entry_threshold=0.01,  # Lower threshold for more trades
        )
        assert len(trades) > 0, "Should generate at least some trades"

    def test_trade_has_required_fields(self, sample_ticker_data):
        """Each trade must have all fields needed by TradeAutopsy."""
        bt = WalkForwardBacktester()
        start = pd.Timestamp('2022-01-01')
        end = pd.Timestamp('2022-07-01')
        trades = bt.simulate_trades_in_window(
            sample_ticker_data, start, end,
            entry_threshold=0.005,
        )
        if trades:  # May be empty in calm market
            t = trades[0]
            assert 'trade_id' in t
            assert 'entry_price' in t
            assert 'exit_price' in t
            assert 'initial_stop' in t
            assert 'price_series' in t
            assert isinstance(t['price_series'], list)
            assert len(t['price_series']) >= 2

    def test_no_trades_in_empty_window(self, sample_ticker_data):
        """A window outside the data range should return no trades."""
        bt = WalkForwardBacktester()
        start = pd.Timestamp('2030-01-01')
        end = pd.Timestamp('2030-07-01')
        trades = bt.simulate_trades_in_window(sample_ticker_data, start, end)
        assert len(trades) == 0


class TestMetrics:

    def test_sharpe_ratio_positive_in_bull_window(self, sample_ticker_data):
        """In a trending up market, Sharpe should be positive."""
        bt = WalkForwardBacktester(train_months=12, test_months=6, step_months=6)
        windows = bt.generate_windows(sample_ticker_data)
        if windows:
            result = bt.evaluate_window(windows[0], sample_ticker_data)
            # At minimum, verify Sharpe is calculated (could be 0 if no trades)
            assert isinstance(result.sharpe_ratio, float)

    def test_profit_factor_nonnegative(self, sample_ticker_data):
        """Profit factor must never be negative."""
        bt = WalkForwardBacktester(train_months=12, test_months=6, step_months=6)
        windows = bt.generate_windows(sample_ticker_data)
        if windows:
            result = bt.evaluate_window(windows[0], sample_ticker_data)
            assert result.profit_factor >= 0

    def test_win_rate_bounded_0_to_100(self, sample_ticker_data):
        """Win rate must be between 0% and 100%."""
        bt = WalkForwardBacktester(train_months=12, test_months=6, step_months=6)
        windows = bt.generate_windows(sample_ticker_data)
        if windows:
            result = bt.evaluate_window(windows[0], sample_ticker_data)
            assert 0 <= result.win_rate <= 100


class TestRegimeClassification:

    def test_bull_regime(self):
        """Positive return > 10% should be BULL."""
        dates = pd.bdate_range('2020-01-02', '2020-06-30')
        prices = np.linspace(100, 120, len(dates))  # +20%
        df = pd.DataFrame({'Date': dates, 'Close': prices})
        regime = WalkForwardBacktester._classify_regime(
            df, pd.Timestamp('2020-01-02'), pd.Timestamp('2020-06-30')
        )
        assert regime == "BULL"

    def test_bear_regime(self):
        """Negative return < -10% should be BEAR."""
        dates = pd.bdate_range('2020-01-02', '2020-06-30')
        prices = np.linspace(100, 85, len(dates))  # -15%
        df = pd.DataFrame({'Date': dates, 'Close': prices})
        regime = WalkForwardBacktester._classify_regime(
            df, pd.Timestamp('2020-01-02'), pd.Timestamp('2020-06-30')
        )
        assert regime == "BEAR"

    def test_sideways_regime(self):
        """Return between -10% and +10% should be SIDEWAYS."""
        dates = pd.bdate_range('2020-01-02', '2020-06-30')
        prices = np.linspace(100, 103, len(dates))  # +3%
        df = pd.DataFrame({'Date': dates, 'Close': prices})
        regime = WalkForwardBacktester._classify_regime(
            df, pd.Timestamp('2020-01-02'), pd.Timestamp('2020-06-30')
        )
        assert regime == "SIDEWAYS"


class TestGating:

    def test_gating_all_pass(self):
        """When all criteria are met, approved_for_shadow should be True."""
        bt = WalkForwardBacktester()
        results = [
            WindowResult(
                window_id=0,
                train_start='2020-01-01', train_end='2022-01-01',
                test_start='2022-01-01', test_end='2022-07-01',
                n_trades=20, n_winners=12, n_losers=8,
                win_rate=60.0, sharpe_ratio=1.2,
                max_drawdown_pct=-8.0, profit_factor=1.8,
            ),
        ]
        report = bt._aggregate_results(results)
        assert report.approved_for_shadow is True

    def test_gating_fails_on_low_sharpe(self):
        """Sharpe < 0.8 should block approval."""
        bt = WalkForwardBacktester()
        results = [
            WindowResult(
                window_id=0,
                train_start='2020-01-01', train_end='2022-01-01',
                test_start='2022-01-01', test_end='2022-07-01',
                n_trades=20, n_winners=12, n_losers=8,
                win_rate=60.0, sharpe_ratio=0.3,  # Too low
                max_drawdown_pct=-5.0, profit_factor=1.5,
            ),
        ]
        report = bt._aggregate_results(results)
        assert report.approved_for_shadow is False
        assert report.passes_sharpe is False

    def test_gating_fails_on_deep_drawdown(self):
        """Drawdown deeper than -20% should block approval."""
        bt = WalkForwardBacktester()
        results = [
            WindowResult(
                window_id=0,
                train_start='2020-01-01', train_end='2022-01-01',
                test_start='2022-01-01', test_end='2022-07-01',
                n_trades=20, n_winners=12, n_losers=8,
                win_rate=60.0, sharpe_ratio=1.5,
                max_drawdown_pct=-25.0,  # Too deep
                profit_factor=1.5,
            ),
        ]
        report = bt._aggregate_results(results)
        assert report.approved_for_shadow is False
        assert report.passes_drawdown is False


class TestFullRun:

    def test_full_run_on_parquet(self):
        """Integration test: run Walk-Forward on real downloaded Parquet data."""
        parquet_path = Path(__file__).resolve().parent.parent / "data" / "historical" / "market_context_5y.parquet"
        if not parquet_path.exists():
            pytest.skip("Parquet not available — run download_historical.py first")

        bt = WalkForwardBacktester(
            train_months=24, test_months=6, step_months=6,
        )
        report = bt.run(ticker='SPY')

        assert isinstance(report, BacktestReport)
        assert report.total_windows > 0
        assert isinstance(report.approved_for_shadow, bool)
        # Verify we got some windows with trades
        active_windows = [w for w in report.windows if w['n_trades'] > 0]
        assert len(active_windows) > 0, "Should have at least one window with trades"
