"""
Unit tests for Oracle Forensic Backtest System.
Verifies multi-horizon signal classifications, Dalio diagnostics, and report cards.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import date
from unittest.mock import patch, MagicMock

from backend.modules.shared.domain.ports.time_series_port import TimeSeriesPort
from backend.modules.simulation.application.use_cases.oracle_trainer import OracleTrainer
from backend.modules.simulation.domain.entities.indicator_snapshot import IndicatorSnapshot
from backend.modules.simulation.domain.entities.signal_forensic_label import SignalForensicLabel, HorizonSnapshot
from backend.modules.simulation.domain.entities.entry_report_card import EntryReportCard
from backend.modules.simulation.domain.entities.exit_report_card import ExitReportCard


# ═══════════════════════════════════════════════════════════
# MOCK INFRASTRUCTURE FOR THE UNIT TESTS
# ═══════════════════════════════════════════════════════════

class MockTimeSeriesStore(TimeSeriesPort):
    """Mock implementation of TimeSeriesPort returning synthetic bar history."""
    
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def save_bars(self, ticker: str, tf: str, df: pd.DataFrame) -> None:
        pass

    def load_bars(self, ticker: str, tf: str, start: date = None, end: date = None) -> pd.DataFrame:
        return self.df

    def bars_last_date(self, ticker: str, tf: str) -> date:
        return date(2026, 5, 20)

    def save_macro(self, name: str, df: pd.DataFrame) -> None:
        pass

    def load_macro(self, name: str) -> pd.DataFrame:
        return pd.DataFrame()

    def save_mcp_snapshot(self, category: str, ticker: str, data: any) -> None:
        pass

    def load_mcp_snapshot(self, category: str, ticker: str, dt: str) -> any:
        return None

    def load_mcp_latest(self, category: str, ticker: str) -> any:
        return None

    def load_mcp_range(self, category: str, ticker: str, start: str, end: str) -> list:
        return []


class MockAdapter:
    """Mock Signal Adapter returning a single signal at a specific Timestamp index."""
    
    def __init__(self, signal_time: pd.Timestamp, signal_val: int):
        self.signal_time = signal_time
        self.signal_val = signal_val

    def generate(self, ohlc: pd.DataFrame) -> pd.DataFrame:
        df = pd.DataFrame(index=ohlc.index)
        df["signal"] = 0
        df["confidence"] = 0.8
        if self.signal_time in df.index:
            df.loc[self.signal_time, "signal"] = self.signal_val
        return df


def create_synthetic_bars(n_bars: int = 300, base_price: float = 100.0) -> pd.DataFrame:
    """Create a clean, standard synthetic bar history."""
    dates = pd.date_range(start="2026-01-01", periods=n_bars, freq="D")
    df = pd.DataFrame({
        "open": [base_price] * n_bars,
        "high": [base_price] * n_bars,
        "low": [base_price] * n_bars,
        "close": [base_price] * n_bars,
        "volume": [10000.0] * n_bars
    }, index=dates)
    return df


# ═══════════════════════════════════════════════════════════
# CLASSIFICATION TEST CASES
# ═══════════════════════════════════════════════════════════

class TestOracleClassifications:
    """Verifies that multi-horizon classifications map perfectly to the domain spec."""

    def test_classify_entry_golden_run(self):
        trainer = OracleTrainer(MagicMock())
        horizons = {
            10: HorizonSnapshot(bars=10, return_pct=4.2, max_up_pct=5.0, max_down_pct=-0.5, bars_to_max_up=3, bars_to_max_down=1)
        }
        res = trainer._classify_entry(horizons)
        assert res == "GOLDEN_RUN"

    def test_classify_entry_solid_move(self):
        trainer = OracleTrainer(MagicMock())
        horizons = {
            10: HorizonSnapshot(bars=10, return_pct=1.8, max_up_pct=2.5, max_down_pct=-1.5, bars_to_max_up=3, bars_to_max_down=1)
        }
        res = trainer._classify_entry(horizons)
        assert res == "SOLID_MOVE"

    def test_classify_entry_slow_grind(self):
        trainer = OracleTrainer(MagicMock())
        horizons = {
            10: HorizonSnapshot(bars=10, return_pct=0.7, max_up_pct=1.2, max_down_pct=-0.8, bars_to_max_up=3, bars_to_max_down=1)
        }
        res = trainer._classify_entry(horizons)
        assert res == "SLOW_GRIND"

    def test_classify_entry_miss(self):
        trainer = OracleTrainer(MagicMock())
        horizons = {
            10: HorizonSnapshot(bars=10, return_pct=0.2, max_up_pct=0.6, max_down_pct=-0.4, bars_to_max_up=3, bars_to_max_down=1)
        }
        res = trainer._classify_entry(horizons)
        assert res == "MISS"

    def test_classify_entry_trap(self):
        trainer = OracleTrainer(MagicMock())
        horizons = {
            10: HorizonSnapshot(bars=10, return_pct=-1.5, max_up_pct=1.2, max_down_pct=-2.0, bars_to_max_up=3, bars_to_max_down=1)
        }
        res = trainer._classify_entry(horizons)
        assert res == "TRAP"

    def test_classify_entry_false_signal(self):
        trainer = OracleTrainer(MagicMock())
        horizons = {
            10: HorizonSnapshot(bars=10, return_pct=-2.5, max_up_pct=0.4, max_down_pct=-3.0, bars_to_max_up=3, bars_to_max_down=1)
        }
        res = trainer._classify_entry(horizons)
        assert res == "FALSE_SIGNAL"

    # Exits

    def test_classify_exit_saved_us(self):
        trainer = OracleTrainer(MagicMock())
        horizons = {
            10: HorizonSnapshot(bars=10, return_pct=-3.5, max_up_pct=0.5, max_down_pct=-4.0, bars_to_max_up=3, bars_to_max_down=1)
        }
        res = trainer._classify_exit(horizons)
        assert res == "SAVED_US"

    def test_classify_exit_good_warning(self):
        trainer = OracleTrainer(MagicMock())
        horizons = {
            10: HorizonSnapshot(bars=10, return_pct=-1.5, max_up_pct=0.5, max_down_pct=-2.0, bars_to_max_up=3, bars_to_max_down=1)
        }
        res = trainer._classify_exit(horizons)
        assert res == "GOOD_WARNING"

    def test_classify_exit_early_but_right(self):
        trainer = OracleTrainer(MagicMock())
        horizons = {
            10: HorizonSnapshot(bars=10, return_pct=-0.7, max_up_pct=0.2, max_down_pct=-1.0, bars_to_max_up=3, bars_to_max_down=1)
        }
        res = trainer._classify_exit(horizons)
        assert res == "EARLY_BUT_RIGHT"

    def test_classify_exit_neutral(self):
        trainer = OracleTrainer(MagicMock())
        horizons = {
            10: HorizonSnapshot(bars=10, return_pct=0.0, max_up_pct=0.4, max_down_pct=-0.4, bars_to_max_up=3, bars_to_max_down=1)
        }
        res = trainer._classify_exit(horizons)
        assert res == "NEUTRAL_EXIT"

    def test_classify_exit_false_alarm(self):
        trainer = OracleTrainer(MagicMock())
        horizons = {
            10: HorizonSnapshot(bars=10, return_pct=1.2, max_up_pct=1.8, max_down_pct=-0.2, bars_to_max_up=3, bars_to_max_down=1)
        }
        res = trainer._classify_exit(horizons)
        assert res == "FALSE_ALARM"

    def test_classify_exit_missed_upside(self):
        trainer = OracleTrainer(MagicMock())
        horizons = {
            10: HorizonSnapshot(bars=10, return_pct=3.5, max_up_pct=4.0, max_down_pct=-0.2, bars_to_max_up=3, bars_to_max_down=1)
        }
        res = trainer._classify_exit(horizons)
        assert res == "MISSED_UPSIDE"


# ═══════════════════════════════════════════════════════════
# FAILURES AND DIAGNOSTICS
# ═══════════════════════════════════════════════════════════

class TestDalioFailureDiagnostics:
    """Checks the Dalio forensic diagnosis and foreseeability classification rules."""

    def _setup_label(self, direction: int, classification: str = "TRAP") -> tuple[OracleTrainer, pd.DataFrame, SignalForensicLabel]:
        trainer = OracleTrainer(MagicMock())
        ohlc = create_synthetic_bars(250)
        
        # Target signal index 200
        sig_time = ohlc.index[200]
        
        snapshot = IndicatorSnapshot(
            sigma_tide=0.0,
            sigma_wave=0.0,
            tide_slope=0.0,
            wave_slope=0.0,
            tide_accel=0.0,
            below_vwap=False,
            vol_up_down_ratio=1.0,
            wave_flip=False,
            wave_flip_direction=0,
            rvol=1.0,
            rsi_value=50.0,
            wyckoff_state="ACCUMULATION",
            kalman_velocity=0.0,
            vol_regime="NORMAL",
            regime="FLAT",
            fear_level=2,
            fear_label="NEUTRAL",
            slope_conjugation=0.0
        )
        
        label = SignalForensicLabel(
            ticker="AAPL",
            signal_name="test_signal",
            signal_direction=direction,
            signal_confidence=0.5,
            signal_time=sig_time,
            signal_price=100.0,
            snapshot=snapshot,
            classification=classification
        )
        
        return trainer, ohlc, label

    # ── Entry Failure Diagnostics (+1) ──

    def test_entry_earnings_shock(self):
        trainer, ohlc, label = self._setup_label(direction=1)
        # Earnings gap: next open is < -3% from close[200] (100.0)
        ohlc.loc[ohlc.index[201], "open"] = 96.0
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "EARNINGS_SHOCK"
        assert foresee == "UNFORESEEABLE"

    def test_entry_black_swan(self):
        trainer, ohlc, label = self._setup_label(direction=1)
        # Next low crashes > -5% intraday, no gap
        ohlc.loc[ohlc.index[201], "open"] = 100.0
        ohlc.loc[ohlc.index[201], "low"] = 94.0
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "BLACK_SWAN"
        assert foresee == "UNFORESEEABLE"

    def test_entry_bear_regime_ignored(self):
        trainer, ohlc, label = self._setup_label(direction=1)
        label.snapshot.fear_level = 5  # PANIC
        label.snapshot.sigma_tide = 0.5
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "BEAR_REGIME_IGNORED"
        assert foresee == "FORESEEABLE"

    def test_entry_greed_exhaustion(self):
        trainer, ohlc, label = self._setup_label(direction=1)
        label.snapshot.fear_level = 0  # GREED
        label.snapshot.sigma_tide = 1.2
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "GREED_EXHAUSTION"
        assert foresee == "FORESEEABLE"

    def test_entry_resistance_entry(self):
        trainer, ohlc, label = self._setup_label(direction=1)
        label.snapshot.sigma_tide = 1.8  # Well above 1.5 resistance limit
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "RESISTANCE_ENTRY"
        assert foresee == "FORESEEABLE"

    def test_entry_distribution_volume(self):
        trainer, ohlc, label = self._setup_label(direction=1)
        # High volume (>2.0 RVOL) + Negative price bar
        ohlc.loc[ohlc.index[200], "volume"] = 30000.0  # avg_vol is 10000.0, so RVOL = 3.0
        ohlc.loc[ohlc.index[200], "close"] = 99.0      # less than close[199] (100.0)
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "DISTRIBUTION_VOLUME"
        assert foresee == "FORESEEABLE"

    def test_entry_climax_volume_trap(self):
        trainer, ohlc, label = self._setup_label(direction=1, classification="TRAP")
        # Climax volume: RVOL > 2.5
        ohlc.loc[ohlc.index[200], "volume"] = 30000.0  # RVOL = 3.0
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "CLIMAX_VOLUME_TRAP"
        assert foresee == "FORESEEABLE"

    def test_entry_greed_trap(self):
        trainer, ohlc, label = self._setup_label(direction=1, classification="TRAP")
        label.snapshot.fear_level = 1  # CONFIDENCE
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "GREED_TRAP"
        assert foresee == "FORESEEABLE"

    def test_entry_low_rvol_entry(self):
        trainer, ohlc, label = self._setup_label(direction=1)
        # Low RVOL: rvol < 0.5
        ohlc.loc[ohlc.index[200], "volume"] = 3000.0   # RVOL = 0.3
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "LOW_RVOL_ENTRY"
        assert foresee == "FORESEEABLE"

    def test_entry_low_volatility_regime(self):
        trainer, ohlc, label = self._setup_label(direction=1, classification="MISS")
        # LOW_VOLATILITY_REGIME: atr_pct < 0.8%
        # High and Low are equal, so average HL range is 0.0, which means atr_pct = 0.0 < 0.8%
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "LOW_VOLATILITY_REGIME"
        assert foresee == "FORESEEABLE"

    def test_entry_consolidation_range(self):
        trainer, ohlc, label = self._setup_label(direction=1, classification="MISS")
        # CONSOLIDATION_RANGE: atr_pct >= 0.8%
        # Modify HL range for past 14 bars to make atr_pct > 1.0%
        for i in range(185, 201):
            ohlc.loc[ohlc.index[i], "high"] = 101.5
            ohlc.loc[ohlc.index[i], "low"] = 99.5
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "CONSOLIDATION_RANGE"
        assert foresee == "FORESEEABLE"

    # ── Exit Failure Diagnostics (-1) ──

    def test_exit_earnings_catalyst(self):
        trainer, ohlc, label = self._setup_label(direction=-1, classification="FALSE_ALARM")
        # Earnings gap: next open is > 3% above close[200]
        ohlc.loc[ohlc.index[201], "open"] = 104.0
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "EARNINGS_CATALYST"
        assert foresee == "UNFORESEEABLE"

    def test_exit_bull_momentum_intact(self):
        trainer, ohlc, label = self._setup_label(direction=-1, classification="FALSE_ALARM")
        label.snapshot.fear_level = 1
        label.snapshot.sigma_tide = 0.5
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "BULL_MOMENTUM_INTACT"
        assert foresee == "FORESEEABLE"

    def test_exit_fear_contrarian_error(self):
        trainer, ohlc, label = self._setup_label(direction=-1, classification="FALSE_ALARM")
        label.snapshot.fear_level = 3
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "FEAR_CONTRARIAN_ERROR"
        assert foresee == "FORESEEABLE"

    def test_exit_low_conviction_noise(self):
        trainer, ohlc, label = self._setup_label(direction=-1, classification="FALSE_ALARM")
        label.signal_confidence = 0.10
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "LOW_CONVICTION_NOISE"
        assert foresee == "FORESEEABLE"

    def test_exit_volume_absent(self):
        trainer, ohlc, label = self._setup_label(direction=-1, classification="FALSE_ALARM")
        ohlc.loc[ohlc.index[200], "volume"] = 5000.0   # RVOL = 0.5 < 0.7
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "VOLUME_ABSENT"
        assert foresee == "FORESEEABLE"

    def test_exit_support_bounce(self):
        trainer, ohlc, label = self._setup_label(direction=-1, classification="FALSE_ALARM")
        label.snapshot.sigma_tide = -0.5
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "SUPPORT_BOUNCE"
        assert foresee == "FORESEEABLE"

    def test_exit_accumulation_disguised(self):
        trainer, ohlc, label = self._setup_label(direction=-1, classification="FALSE_ALARM")
        label.snapshot.wyckoff_state = "DISTRIBUTION"
        label.snapshot.fear_level = 2

        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "ACCUMULATION_DISGUISED"
        assert foresee == "FORESEEABLE"

    def test_exit_low_volatility_regime(self):
        trainer, ohlc, label = self._setup_label(direction=-1, classification="NEUTRAL_EXIT")
        # atr_pct = 0.0 < 0.8%
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "LOW_VOLATILITY_REGIME"
        assert foresee == "FORESEEABLE"

    def test_exit_range_bound(self):
        trainer, ohlc, label = self._setup_label(direction=-1, classification="NEUTRAL_EXIT")
        # Modify HL range to make atr_pct >= 0.8%
        for i in range(185, 201):
            ohlc.loc[ohlc.index[i], "high"] = 101.5
            ohlc.loc[ohlc.index[i], "low"] = 99.5
        
        diag, foresee = trainer.diagnose_failure(ohlc, label)
        assert diag == "RANGE_BOUND"
        assert foresee == "FORESEEABLE"


# ═══════════════════════════════════════════════════════════
# END TO END EVALUATION INTEGRATION FLOW
# ═══════════════════════════════════════════════════════════

class TestOracleTrainerIntegration:
    """Simulates an end-to-end evaluation cycle with patched snapshot engine."""

    @patch("backend.modules.simulation.application.use_cases.oracle_trainer.compute_vol_regime_snapshot")
    def test_evaluate_entries_end_to_end(self, mock_vol_regime):
        # Setup mock vol regime snapshot return to prevent index crashes
        mock_snapshot = MagicMock()
        mock_snapshot.quality_regime = 0
        mock_vol_regime.return_value = mock_snapshot

        # Create synthetic database bars
        ohlc = create_synthetic_bars(250)
        
        # Inject one GOLDEN_RUN entry signal at index 200
        sig_time = ohlc.index[200]
        
        # Modify close prices to generate a +4% return at index 210 (10 bars forward)
        # So return_pct = 4.0% >= 3.0%, and low prices are high enough that MAE > -1.0%
        ohlc.loc[ohlc.index[210], "close"] = 104.0
        for i in range(201, 211):
            ohlc.loc[ohlc.index[i], "low"] = 99.5
            ohlc.loc[ohlc.index[i], "high"] = 104.5

        # Initialize trainer and mock database
        store = MockTimeSeriesStore(ohlc)
        trainer = OracleTrainer(store)

        # Mock `_build_snapshot` to bypass long tide regression channel fitting
        dummy_snapshot = IndicatorSnapshot(
            sigma_tide=-1.5,
            sigma_wave=-1.8,
            tide_slope=0.02,
            wave_slope=0.01,
            tide_accel=0.0,
            below_vwap=True,
            vol_up_down_ratio=1.5,
            wave_flip=True,
            wave_flip_direction=1,
            rvol=1.2,
            rsi_value=32.0,
            wyckoff_state="ACCUMULATION",
            kalman_velocity=0.0,
            vol_regime="NORMAL",
            regime="BULL",
            fear_level=4,
            fear_label="ANXIETY",
            slope_conjugation=-0.01
        )
        
        adapter = MockAdapter(sig_time, signal_val=1)

        with patch.object(trainer, "_build_snapshot", return_value=dummy_snapshot):
            labels, report_card = trainer.evaluate_entries(
                ticker="AAPL",
                tf="1d",
                signal_name="rsi_intelligence",
                adapter=adapter
            )

        # Assertions on Signal Forensic Labels
        assert len(labels) == 1
        lbl = labels[0]
        assert lbl.ticker == "AAPL"
        assert lbl.signal_direction == 1
        assert lbl.signal_time == sig_time
        assert lbl.signal_price == 100.0
        assert lbl.classification == "GOLDEN_RUN"
        assert lbl.snapshot.sigma_tide == -1.5

        # Assertions on Entry Report Card
        assert isinstance(report_card, EntryReportCard)
        assert report_card.ticker == "AAPL"
        assert report_card.n_signals == 1
        assert report_card.golden_rate == 100.0
        assert report_card.trap_rate == 0.0
        assert report_card.grade == "A"
        assert report_card.verdict == "ELITE"

    @patch("backend.modules.simulation.application.use_cases.oracle_trainer.compute_vol_regime_snapshot")
    def test_evaluate_exits_end_to_end(self, mock_vol_regime):
        # Setup mock vol regime snapshot return
        mock_snapshot = MagicMock()
        mock_snapshot.quality_regime = 0
        mock_vol_regime.return_value = mock_snapshot

        # Create synthetic database bars
        ohlc = create_synthetic_bars(250)
        
        # Inject one SAVED_US exit signal at index 200
        sig_time = ohlc.index[200]
        
        # Modify close prices to generate a -4% return at index 210 (10 bars forward)
        # So return_pct = -4.0% <= -3.0% (SAVED_US)
        ohlc.loc[ohlc.index[210], "close"] = 96.0

        # Initialize trainer and mock database
        store = MockTimeSeriesStore(ohlc)
        trainer = OracleTrainer(store)

        # Mock snapshot
        dummy_snapshot = IndicatorSnapshot(
            sigma_tide=1.5,
            sigma_wave=1.8,
            tide_slope=-0.02,
            wave_slope=-0.01,
            tide_accel=0.0,
            below_vwap=False,
            vol_up_down_ratio=0.8,
            wave_flip=True,
            wave_flip_direction=-1,
            rvol=1.5,
            rsi_value=72.0,
            wyckoff_state="DISTRIBUTION",
            kalman_velocity=0.0,
            vol_regime="NORMAL",
            regime="BEAR",
            fear_level=1,
            fear_label="CONFIDENCE",
            slope_conjugation=0.01
        )
        
        adapter = MockAdapter(sig_time, signal_val=-1)

        with patch.object(trainer, "_build_snapshot", return_value=dummy_snapshot):
            labels, report_card = trainer.evaluate_exits(
                ticker="AAPL",
                tf="1d",
                signal_name="rsi_intelligence",
                adapter=adapter
            )

        # Assertions on Labels
        assert len(labels) == 1
        lbl = labels[0]
        assert lbl.ticker == "AAPL"
        assert lbl.signal_direction == -1
        assert lbl.signal_time == sig_time
        assert lbl.signal_price == 100.0
        assert lbl.classification == "SAVED_US"

        # Assertions on Exit Report Card
        assert isinstance(report_card, ExitReportCard)
        assert report_card.ticker == "AAPL"
        assert report_card.n_signals == 1
        assert report_card.save_rate == 100.0
        assert report_card.grade == "A"
        assert report_card.verdict == "ELITE"
