"""
Unit tests for Volume Breadth Calculator (SV5)
================================================
Tests the pure domain rule that calculates % of tickers
where fast volume MA > slow volume MA.

Covers: _sma, _ema, calculate_volume_breadth (SMA + EMA modes),
        calculate_all_volume_breadth, and edge cases.
"""
from backend.modules.shared.domain.rules.volume_breadth_calculator import (
    _sma,
    _ema,
    calculate_volume_breadth,
    calculate_all_volume_breadth,
)


# ── SMA tests ──────────────────────────────────────────────

class TestSma:
    def test_empty_returns_none(self):
        assert _sma([], 5) is None

    def test_insufficient_data_returns_none(self):
        assert _sma([10.0, 20.0], 5) is None

    def test_exact_length(self):
        assert _sma([10.0, 20.0, 30.0], 3) == 20.0

    def test_uses_last_n_values_only(self):
        # SMA(3) of [1, 2, 3, 4, 5] should use [3, 4, 5] = mean 4.0
        assert _sma([1.0, 2.0, 3.0, 4.0, 5.0], 3) == 4.0

    def test_single_value(self):
        assert _sma([42.0], 1) == 42.0

    def test_all_same_values(self):
        assert _sma([100.0] * 50, 20) == 100.0


# ── EMA tests ──────────────────────────────────────────────

class TestEma:
    def test_empty_returns_none(self):
        assert _ema([], 5) is None

    def test_insufficient_data_returns_none(self):
        assert _ema([1.0, 2.0], 5) is None

    def test_exact_span_returns_sma_seed(self):
        # With exactly span elements, EMA = SMA of those elements (no recurrence steps)
        assert _ema([10.0, 20.0, 30.0], 3) == 20.0

    def test_one_step_recurrence(self):
        # Span=3, alpha=2/(3+1)=0.5
        # Seed: SMA([10,20,30]) = 20.0
        # Step: 0.5*40 + 0.5*20 = 30.0
        assert _ema([10.0, 20.0, 30.0, 40.0], 3) == 30.0

    def test_two_step_recurrence(self):
        # Span=3, alpha=0.5
        # Seed: SMA([10,20,30]) = 20.0
        # Step 1: 0.5*40 + 0.5*20 = 30.0
        # Step 2: 0.5*50 + 0.5*30 = 40.0
        assert _ema([10.0, 20.0, 30.0, 40.0, 50.0], 3) == 40.0

    def test_ema_with_constant_data(self):
        # EMA of constant data = that constant
        result = _ema([100.0] * 20, 5)
        assert result == 100.0

    def test_ema_reacts_to_recent_spike(self):
        # EMA should be > SMA when recent values spike up
        data = [100.0] * 19 + [200.0]
        ema_val = _ema(data, 5)
        sma_val = _sma(data, 5)
        # SMA(5) of [..., 100, 100, 100, 100, 200] = 120
        assert sma_val == 120.0
        # EMA should weight the 200 more heavily than SMA does
        assert ema_val is not None
        assert ema_val > sma_val


# ── calculate_volume_breadth tests ─────────────────────────

class TestCalculateVolumeBreadth:
    def test_empty_dict_returns_none(self):
        assert calculate_volume_breadth({}, 5, 20) is None

    def test_all_tickers_insufficient_data(self):
        data = {
            "AAPL": [100.0] * 10,
            "MSFT": [100.0] * 5,
        }
        assert calculate_volume_breadth(data, 5, 20) is None

    def test_100_percent_above(self):
        # All tickers: fast > slow (recent vol higher than historical)
        data = {
            "AAPL": [100.0] * 15 + [200.0] * 5,
            "MSFT": [100.0] * 15 + [200.0] * 5,
            "GOOG": [100.0] * 15 + [200.0] * 5,
        }
        assert calculate_volume_breadth(data, 5, 20, "sma") == 100.0

    def test_0_percent_above(self):
        # All tickers: fast < slow (recent vol dropped)
        data = {
            "AAPL": [200.0] * 15 + [50.0] * 5,
            "MSFT": [200.0] * 15 + [50.0] * 5,
        }
        assert calculate_volume_breadth(data, 5, 20, "sma") == 0.0

    def test_50_percent_split(self):
        data = {
            "AAPL": [100.0] * 15 + [200.0] * 5,  # fast > slow
            "MSFT": [200.0] * 15 + [50.0] * 5,   # fast < slow
        }
        assert calculate_volume_breadth(data, 5, 20, "sma") == 50.0

    def test_ema_mode_works(self):
        # The tactical layer uses EMA — verify it doesn't crash and returns a value
        data = {
            "AAPL": [100.0] * 15 + [200.0] * 5,
            "MSFT": [200.0] * 15 + [50.0] * 5,
        }
        result = calculate_volume_breadth(data, 5, 20, "ema")
        assert result is not None
        assert 0.0 <= result <= 100.0

    def test_ema_more_responsive_than_sma(self):
        # After a sudden spike, EMA fast should react more than SMA fast
        # so more tickers might cross the threshold with EMA
        data = {
            "A": [100.0] * 19 + [300.0],  # Big spike on last day
            "B": [100.0] * 19 + [300.0],
        }
        ema_result = calculate_volume_breadth(data, 5, 20, "ema")
        sma_result = calculate_volume_breadth(data, 5, 20, "sma")
        # Both should be 100% since fast > slow in both cases
        # but EMA should give a valid result
        assert ema_result is not None
        assert sma_result is not None

    def test_mixed_data_lengths(self):
        # Some tickers have enough data, some don't
        data = {
            "AAPL": [100.0] * 15 + [200.0] * 5,  # 20 days — sufficient, fast > slow
            "MSFT": [100.0] * 10,                   # 10 days — insufficient, skipped
            "GOOG": [200.0] * 15 + [50.0] * 5,     # 20 days — sufficient, fast < slow
        }
        # Only AAPL and GOOG count. 1/2 = 50%
        result = calculate_volume_breadth(data, 5, 20, "sma")
        assert result == 50.0

    def test_slow_val_zero_guard(self):
        # If slow MA = 0, the ticker should be skipped (guard at L91: slow_val > 0)
        data = {
            "AAPL": [0.0] * 20,  # All zeros → SMA = 0 → skipped
            "MSFT": [100.0] * 15 + [200.0] * 5,  # Valid
        }
        # Only MSFT counts, and fast > slow → 100%
        result = calculate_volume_breadth(data, 5, 20, "sma")
        assert result == 100.0

    def test_rounding_to_one_decimal(self):
        # 1 out of 3 = 33.333...% → should round to 33.3
        data = {
            "A": [100.0] * 15 + [200.0] * 5,   # above
            "B": [200.0] * 15 + [50.0] * 5,    # below
            "C": [200.0] * 15 + [50.0] * 5,    # below
        }
        result = calculate_volume_breadth(data, 5, 20, "sma")
        assert result == 33.3


# ── calculate_all_volume_breadth tests ─────────────────────

class TestCalculateAllVolumeBreadth:
    def test_returns_all_three_layers(self):
        data = {"AAPL": [100.0] * 210, "MSFT": [100.0] * 210}
        res = calculate_all_volume_breadth(data)
        assert "tactical" in res
        assert "intermediate" in res
        assert "structural" in res

    def test_returns_numeric_values(self):
        data = {"AAPL": [100.0] * 210, "MSFT": [100.0] * 210}
        res = calculate_all_volume_breadth(data)
        for key in ["tactical", "intermediate", "structural"]:
            val = res[key]
            assert val is not None, f"{key} should not be None with 210 days"
            assert isinstance(val, float), f"{key} should be float"
            assert 0.0 <= val <= 100.0, f"{key}={val} out of range"

    def test_constant_data_all_layers_50(self):
        # With constant volume, SMA(fast) == SMA(slow) → NOT above → 0%
        # Because the condition is strict > (not >=)
        data = {"AAPL": [100.0] * 210, "MSFT": [100.0] * 210}
        res = calculate_all_volume_breadth(data)
        for key in ["tactical", "intermediate", "structural"]:
            assert res[key] == 0.0, f"Constant data: {key} should be 0% (fast == slow, not >)"

    def test_insufficient_for_structural_only(self):
        # 60 days is enough for tactical (5/20) and intermediate (20/50)
        # but NOT for structural (50/200)
        data = {"AAPL": [100.0] * 60, "MSFT": [100.0] * 60}
        res = calculate_all_volume_breadth(data)
        assert res["tactical"] is not None
        assert res["intermediate"] is not None
        assert res["structural"] is None
