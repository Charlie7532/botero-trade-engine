"""
Quaternion Unit Tests — Mathematical Bounds + Signal Integration
==================================================================
Tests the MarketQuaternion core math and QuaternionSignalAdapter.
Isolated from production test suite (lives in research_lab/tests/).

Run: PYTHONPATH=. backend/.venv/bin/python -m pytest backend/research_lab/tests/ -v
"""
import numpy as np
import pandas as pd
import pytest

from backend.research_lab.models.quaternion_core import MarketQuaternion
from backend.research_lab.experiments.quaternion_signal import (
    QuaternionSignalAdapter,
    QuaternionScorecard,
)


def _make_ohlcv(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")

    close = 100 + np.cumsum(rng.randn(n) * 0.5)
    open_ = close + rng.randn(n) * 0.3
    high = np.maximum(open_, close) + abs(rng.randn(n) * 0.5)
    low = np.minimum(open_, close) - abs(rng.randn(n) * 0.5)
    volume = (1e6 + rng.randn(n) * 2e5).clip(1e4)

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)


class TestQuaternionCore:
    """Tests for MarketQuaternion.compute()."""

    def test_output_shape(self):
        """Output should have 12 columns (4 base + 8 derivatives)."""
        df = _make_ohlcv()
        q = MarketQuaternion.compute(df)
        assert q.shape[0] == len(df)
        assert q.shape[1] == 12  # 4 base + 8 derivatives

    def test_base_only_shape(self):
        """Without derivatives, output should have 4 columns."""
        df = _make_ohlcv()
        q = MarketQuaternion.compute(df, include_derivatives=False)
        assert q.shape[1] == 4

    def test_qx_bounds(self):
        """Q_x (displacement) must be in [-1, +1]."""
        df = _make_ohlcv(200)
        q = MarketQuaternion.compute(df, include_derivatives=False)
        valid = q["Q_x"].dropna()
        assert valid.min() >= -1.0 - 1e-10
        assert valid.max() <= 1.0 + 1e-10

    def test_qz_bounds(self):
        """Q_z (absorption) must be in [-1, +1]."""
        df = _make_ohlcv(200)
        q = MarketQuaternion.compute(df, include_derivatives=False)
        valid = q["Q_z"].dropna()
        assert valid.min() >= -1.0 - 1e-10
        assert valid.max() <= 1.0 + 1e-10

    def test_bullish_bar_positive_qx(self):
        """A bar with close > open should produce Q_x > 0."""
        dates = pd.date_range("2024-01-01", periods=30, freq="D", tz="UTC")
        df = pd.DataFrame({
            "open": [100] * 30,
            "high": [105] * 30,
            "low": [98] * 30,
            "close": [104] * 30,  # Clearly bullish
            "volume": [1e6] * 30,
        }, index=dates)
        q = MarketQuaternion.compute(df, include_derivatives=False)
        # After warmup period, Q_x should be positive
        assert q["Q_x"].iloc[-1] > 0

    def test_high_volume_positive_qy(self):
        """A volume spike should produce Q_y > 0."""
        dates = pd.date_range("2024-01-01", periods=80, freq="D", tz="UTC")
        volume = [1e6] * 70 + [5e6] * 10  # Spike in last 10 bars
        df = pd.DataFrame({
            "open": [100] * 80,
            "high": [102] * 80,
            "low": [98] * 80,
            "close": [101] * 80,
            "volume": volume,
        }, index=dates)
        q = MarketQuaternion.compute(df, include_derivatives=False)
        # Last bar should have high intensity
        assert q["Q_y"].iloc[-1] > 0

    def test_rotation_angle_nonnegative(self):
        """Q_rotation_angle must be >= 0 (arccos property)."""
        df = _make_ohlcv(200)
        q = MarketQuaternion.compute(df)
        valid = q["Q_rotation_angle"].dropna()
        assert valid.min() >= -1e-10

    def test_extras_added(self):
        """Extra dimensions should appear in output."""
        df = _make_ohlcv(50)
        extras = {
            "vix_zscore": pd.Series(np.random.randn(50), index=df.index),
            "skew_delta": pd.Series(np.random.randn(50), index=df.index),
        }
        q = MarketQuaternion.compute(df, extras=extras)
        assert "vix_zscore" in q.columns
        assert "skew_delta" in q.columns
        assert q.shape[1] == 14  # 12 base + 2 extras

    def test_dimension_names(self):
        """dimension_names() should match actual output columns."""
        df = _make_ohlcv(50)
        q = MarketQuaternion.compute(df)
        expected = MarketQuaternion.dimension_names()
        assert set(expected) == set(q.columns)


class TestQuaternionScorecard:
    """Tests for the self-calibrating prediction tracker."""

    def test_empty_zone_uniform_prior(self):
        """An unseen zone should return uniform 33/33/33 prior."""
        sc = QuaternionScorecard()
        pred = sc.get_prediction(0.5, 0.3, 1.0, -0.2)
        assert abs(pred["bull"] - 0.333) < 0.01
        assert pred["n_observations"] == 0

    def test_update_shifts_probability(self):
        """After several bullish outcomes, P(bull) should increase."""
        sc = QuaternionScorecard()
        # Same zone, 8 bullish + 2 bearish outcomes
        for _ in range(8):
            sc.update(0.5, 0.3, 1.0, -0.2, "bull")
        for _ in range(2):
            sc.update(0.5, 0.3, 1.0, -0.2, "bear")

        pred = sc.get_prediction(0.5, 0.3, 1.0, -0.2)
        assert pred["bull"] == 0.8
        assert pred["bear"] == 0.2
        assert pred["n_observations"] == 10


class TestSignalAdapter:
    """Tests for QuaternionSignalAdapter."""

    def test_signal_output_has_signal_column(self):
        """Adapter must produce a 'signal' column."""
        df = _make_ohlcv()
        adapter = QuaternionSignalAdapter(include_predictions=False)
        result = adapter.generate(df)
        assert "signal" in result.columns

    def test_signal_values_are_binary(self):
        """Signal values must be 0 or 1."""
        df = _make_ohlcv(200)
        adapter = QuaternionSignalAdapter(include_predictions=False)
        result = adapter.generate(df)
        unique_vals = set(result["signal"].unique())
        assert unique_vals.issubset({0, 1})

    def test_prediction_columns_present(self):
        """With predictions enabled, D5/D6/D7 columns should exist."""
        df = _make_ohlcv(100)
        adapter = QuaternionSignalAdapter(include_predictions=True)
        result = adapter.generate(df)
        assert "Q_pred_bull" in result.columns
        assert "Q_pred_bear" in result.columns
        assert "Q_pred_accuracy" in result.columns

    def test_required_context_empty(self):
        """Quaternion needs only OHLCV — no external context."""
        adapter = QuaternionSignalAdapter()
        assert adapter.required_context() == []
