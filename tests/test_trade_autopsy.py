"""
Tests for trade_autopsy.py — MFE/MAE Analysis + Error Classification

Validates:
  - MFE/MAE computation for LONG trades
  - Entry Efficiency, Stop Efficiency, Edge Ratio calculations
  - Heuristic error classification:
      SIN_EDGE, FALSO_BREAKOUT, ENTRADA_TARDIA, STOP_TIGHT,
      TIMING_PERFECTO, BUENA_EJECUCION, GANANCIA_DESPERDICIADA
  - Batch analysis and systemic weakness detection
"""
import pytest
import pandas as pd

from backend.application.trade_autopsy import TradeAutopsy, TradeAutopsyResult


class TestMFEMAECalculation:

    def test_mfe_is_highest_point(self):
        """MFE should be the highest price reached during the trade."""
        autopsy = TradeAutopsy()
        result = autopsy.analyze(
            trade_id="t1", ticker="AAPL",
            entry_price=100, exit_price=105,
            initial_stop=95,
            price_series=[100, 102, 108, 106, 105],  # Peak at 108
        )
        assert result.mfe_price == 108
        assert result.mfe_pct == pytest.approx(8.0, rel=0.01)

    def test_mae_is_lowest_point(self):
        """MAE should be the lowest price reached during the trade."""
        autopsy = TradeAutopsy()
        result = autopsy.analyze(
            trade_id="t2", ticker="MSFT",
            entry_price=200, exit_price=210,
            initial_stop=190,
            price_series=[200, 195, 193, 205, 210],  # Trough at 193
        )
        assert result.mae_price == 193
        assert result.mae_pct == pytest.approx(-3.5, rel=0.01)

    def test_bars_to_mfe_correct(self):
        """bars_to_mfe should be the index of the highest price."""
        autopsy = TradeAutopsy()
        result = autopsy.analyze(
            trade_id="t3", ticker="GOOG",
            entry_price=150, exit_price=155,
            initial_stop=145,
            price_series=[150, 151, 160, 157, 155],  # Peak at index 2
        )
        assert result.bars_to_mfe == 2
        assert result.total_bars == 5


class TestDerivedMetrics:

    def test_entry_efficiency_perfect(self):
        """When PnL = MFE, entry efficiency should be ~1.0."""
        autopsy = TradeAutopsy()
        result = autopsy.analyze(
            trade_id="t4", ticker="NVDA",
            entry_price=100, exit_price=110,
            initial_stop=95,
            price_series=[100, 105, 110],  # Exit at peak
        )
        assert result.entry_efficiency == pytest.approx(1.0, abs=0.01)

    def test_entry_efficiency_low_when_gave_back(self):
        """When we gave back most gains, efficiency should be low."""
        autopsy = TradeAutopsy()
        result = autopsy.analyze(
            trade_id="t5", ticker="META",
            entry_price=100, exit_price=101,
            initial_stop=95,
            # MFE = 10%, but we only captured 1%
            price_series=[100, 105, 110, 108, 103, 101],
        )
        assert result.entry_efficiency < 0.15

    def test_edge_ratio_high_for_strong_trade(self):
        """Strong trade: big MFE, small MAE → high edge ratio."""
        autopsy = TradeAutopsy()
        result = autopsy.analyze(
            trade_id="t6", ticker="AMZN",
            entry_price=100, exit_price=108,
            initial_stop=97,
            price_series=[100, 99.5, 101, 104, 108],  # Small dip, big run
        )
        assert result.edge_ratio > 10.0  # MFE=8%, MAE=-0.5%

    def test_edge_ratio_below_1_no_edge(self):
        """Losing trade where MAE > MFE → edge ratio < 1."""
        autopsy = TradeAutopsy()
        result = autopsy.analyze(
            trade_id="t7", ticker="TSLA",
            entry_price=100, exit_price=95,
            initial_stop=92,
            price_series=[100, 100.5, 98, 96, 95],  # MFE=0.5%, MAE=-5%
        )
        assert result.edge_ratio < 1.0


class TestErrorClassification:

    def test_timing_perfecto(self):
        """High entry efficiency + high edge ratio → TIMING_PERFECTO."""
        autopsy = TradeAutopsy()
        result = autopsy.analyze(
            trade_id="t8", ticker="AAPL",
            entry_price=100, exit_price=109,
            initial_stop=96,
            price_series=[100, 103, 106, 110, 109],  # MFE=10%, PnL=9%
        )
        assert result.error_class == "TIMING_PERFECTO"
        assert result.was_winner

    def test_sin_edge_classification(self):
        """Edge ratio < 1 → SIN_EDGE."""
        autopsy = TradeAutopsy()
        result = autopsy.analyze(
            trade_id="t9", ticker="F",
            entry_price=100, exit_price=94,
            initial_stop=92,
            # MFE tiny (0.5%), MAE brutal (-6%)
            price_series=[100, 100.5, 98, 96, 94],
        )
        assert result.error_class == "SIN_EDGE"
        assert not result.was_winner

    def test_falso_breakout_classification(self):
        """Quick spike then reversal → FALSO_BREAKOUT."""
        autopsy = TradeAutopsy()
        result = autopsy.analyze(
            trade_id="t10", ticker="GME",
            entry_price=100, exit_price=96,
            initial_stop=94,
            # Spike to 104 in 2 bars, then crashed (edge_ratio > 1 but 
            # the peak was in bar 2 out of 8)
            price_series=[100, 103, 104, 101, 99, 98, 97, 96],
        )
        assert result.error_class == "FALSO_BREAKOUT"

    def test_stop_tight_classification(self):
        """MAE far exceeds stop distance → STOP_TIGHT."""
        autopsy = TradeAutopsy()
        result = autopsy.analyze(
            trade_id="t11", ticker="BA",
            entry_price=100, exit_price=97,
            initial_stop=99,  # Very tight: only $1 stop (1%)
            # Price goes up to 106 (+6% MFE), dips to 96 (-4% MAE), exits at 97
            # edge_ratio = 6/4 = 1.5 > 1 (not SIN_EDGE)
            # stop_eff = 4% / 1% = 4.0 > 1.5 (STOP_TIGHT)
            # bars_to_mfe = 3 out of 7 (not FALSO_BREAKOUT)
            # entry_eff < 0 so ENTRADA_TARDIA could trigger, but stop_eff dominates
            price_series=[100, 102, 104, 106, 102, 96, 97],
        )
        assert result.error_class == "STOP_TIGHT"

    def test_ganancia_desperdiciada(self):
        """Winner but low entry efficiency → GANANCIA_DESPERDICIADA."""
        autopsy = TradeAutopsy()
        result = autopsy.analyze(
            trade_id="t12", ticker="NFLX",
            entry_price=100, exit_price=101,
            initial_stop=95,
            # MFE = 12% but we only captured 1%
            price_series=[100, 104, 108, 112, 108, 104, 101],
        )
        assert result.error_class == "GANANCIA_DESPERDICIADA"
        assert result.was_winner

    def test_insufficient_data(self):
        """Less than 2 bars → INSUFFICIENT_DATA."""
        autopsy = TradeAutopsy()
        result = autopsy.analyze(
            trade_id="t13", ticker="X",
            entry_price=100, exit_price=100,
            initial_stop=95,
            price_series=[100],
        )
        assert result.error_class == "INSUFFICIENT_DATA"


class TestBatchAnalysis:

    def test_batch_returns_dataframe(self):
        """analyze_batch should return a DataFrame with all results."""
        autopsy = TradeAutopsy()
        trades = [
            {"trade_id": "b1", "ticker": "A", "entry_price": 100,
             "exit_price": 110, "initial_stop": 95,
             "price_series": [100, 105, 110]},
            {"trade_id": "b2", "ticker": "B", "entry_price": 100,
             "exit_price": 95, "initial_stop": 92,
             "price_series": [100, 98, 95]},
        ]
        df = autopsy.analyze_batch(trades)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "error_class" in df.columns
        assert "edge_ratio" in df.columns

    def test_systemic_weakness_with_enough_data(self):
        """get_systemic_weakness should find dominant error class."""
        autopsy = TradeAutopsy()
        # Create 6 trades where most are SIN_EDGE losers
        trades = []
        for i in range(6):
            trades.append({
                "trade_id": f"sw-{i}", "ticker": f"T{i}",
                "entry_price": 100, "exit_price": 94,
                "initial_stop": 92,
                "price_series": [100, 100.2, 98, 96, 94],  # SIN_EDGE
            })
        # Add 1 winner
        trades.append({
            "trade_id": "sw-win", "ticker": "W",
            "entry_price": 100, "exit_price": 108,
            "initial_stop": 95,
            "price_series": [100, 104, 108],
        })

        df = autopsy.analyze_batch(trades)
        weakness = autopsy.get_systemic_weakness(df)
        assert weakness["dominant_error"] == "SIN_EDGE"
        assert weakness["total_losers"] == 6
