"""
Tests for volume_dynamics.py

Validates:
  - KalmanVolumeTracker: state initialization, velocity estimation,
    early rotation detection
  - SectorRegimeDetector: Wyckoff 4-state classification
  - SectorFlowEngine: global volume heatmap construction
    (domestic + international ETFs, flow_signal, sorting)
"""
import pytest
import pandas as pd
import numpy as np

from backend.infrastructure.data_providers.volume_dynamics import (
    KalmanVolumeTracker,
    SectorRegimeDetector,
    VolumeDynamicsReport,
)
from backend.infrastructure.data_providers.sector_flow import SectorFlowEngine


# ================================================================
# KalmanVolumeTracker Tests
# ================================================================

class TestKalmanVolumeTracker:

    def test_first_observation_returns_zero_velocity(self):
        """First observation: no history → velocity must be 0."""
        tracker = KalmanVolumeTracker()
        state = tracker.update('XLK', 1.2)
        assert state['velocity'] == 0.0
        assert state['history_len'] == 1

    def test_velocity_positive_on_increasing_rvol(self):
        """Rising rvol series should produce positive velocity estimate."""
        tracker = KalmanVolumeTracker()
        for rvol in [1.0, 1.1, 1.25, 1.45, 1.70]:
            state = tracker.update('XLF', rvol)
        assert state['velocity'] > 0, "Rising rvol must yield positive velocity"

    def test_velocity_negative_on_decreasing_rvol(self):
        """Falling rvol series should produce negative velocity estimate."""
        tracker = KalmanVolumeTracker()
        for rvol in [2.5, 2.1, 1.8, 1.4, 1.0]:
            state = tracker.update('EEM', rvol)
        assert state['velocity'] < 0, "Falling rvol must yield negative velocity"

    def test_kalman_smooths_spike(self):
        """A sudden spike followed by normal values should not permanently shift estimate."""
        tracker = KalmanVolumeTracker()
        for _ in range(5):
            tracker.update('XLV', 1.0)    # Establish baseline
        tracker.update('XLV', 5.0)        # Spike
        state = tracker.update('XLV', 1.0)  # Back to normal
        # Kalman estimate should be pulled back, not pinned at spike
        assert state['rel_vol'] < 4.0, "Kalman should smooth out the spike"

    def test_independent_state_per_etf(self):
        """Different ETFs must maintain independent Kalman states."""
        tracker = KalmanVolumeTracker()
        for rvol in [1.0, 1.3, 1.6, 2.0]:
            tracker.update('XLK', rvol)   # Rising
        for rvol in [2.0, 1.7, 1.3, 1.0]:
            tracker.update('EWZ', rvol)   # Falling

        xlk_vel = tracker._states['XLK']['x'][1]
        ewz_vel = tracker._states['EWZ']['x'][1]
        assert xlk_vel > 0, "XLK should have positive velocity"
        assert ewz_vel < 0, "EWZ should have negative velocity"

    def test_bulk_update(self):
        """bulk_update processes all ETFs and returns a state dict."""
        tracker = KalmanVolumeTracker()
        readings = {'XLK': 1.5, 'EEM': 2.1, 'VGK': 0.8}
        results = tracker.bulk_update(readings)
        assert set(results.keys()) == {'XLK', 'EEM', 'VGK'}
        for etf, state in results.items():
            assert 'velocity' in state
            assert 'wyckoff_state' in state

    def test_early_rotation_signals_empty_at_start(self):
        """With no history, no early rotation signals should be emitted."""
        tracker = KalmanVolumeTracker()
        tracker.update('XLF', 1.3)  # Only 1 observation each
        tracker.update('EEM', 1.5)
        signals = tracker.get_early_rotation_signals()
        assert signals == [], "One-observation ETFs cannot emit rotation signal"

    def test_early_rotation_signal_detected(self):
        """An ETF with consistently rising rvol < 2.5x should trigger early signal."""
        tracker = KalmanVolumeTracker()
        for rvol in [1.0, 1.1, 1.2, 1.35, 1.5, 1.65]:
            tracker.update('XLI', rvol)
        signals = tracker.get_early_rotation_signals(min_velocity=0.05, min_confidence=0.0)
        tickers = [s['etf'] for s in signals]
        assert 'XLI' in tickers, "Steadily rising rvol < 2.5x should appear in early signals"

    def test_late_signal_not_in_early_signals(self):
        """ETF already at high rvol (>= 2.5x) should not appear as early signal."""
        tracker = KalmanVolumeTracker()
        for rvol in [1.0, 1.5, 2.0, 2.6, 3.0, 3.5]:
            tracker.update('MCHI', rvol)
        signals = tracker.get_early_rotation_signals(min_velocity=0.05, min_confidence=0.0)
        tickers = [s['etf'] for s in signals]
        assert 'MCHI' not in tickers, "rvol >= 2.5x is too late for early signal"


# ================================================================
# SectorRegimeDetector Tests
# ================================================================

class TestSectorRegimeDetector:

    def test_accumulation_early_rising_volume(self):
        """Low rvol accelerating with positive price should be ACCUMULATION."""
        state = SectorRegimeDetector.classify(
            rel_vol=1.3, velocity=0.2, acceleration=0.05, change_pct=0.5
        )
        assert state == 'ACCUMULATION'

    def test_markup_confirmed_trend(self):
        """High rvol + rising price = MARKUP (trend established)."""
        state = SectorRegimeDetector.classify(
            rel_vol=1.8, velocity=0.1, acceleration=0.0, change_pct=1.5
        )
        assert state == 'MARKUP'

    def test_distribution_high_vol_negative_velocity(self):
        """Very high rvol + decelerating = DISTRIBUTION."""
        state = SectorRegimeDetector.classify(
            rel_vol=2.5, velocity=-0.3, acceleration=-0.1, change_pct=None
        )
        assert state == 'DISTRIBUTION'

    def test_distribution_high_vol_falling_price(self):
        """High rvol + falling price = DISTRIBUTION."""
        state = SectorRegimeDetector.classify(
            rel_vol=1.8, velocity=0.0, acceleration=0.0, change_pct=-1.2
        )
        assert state == 'DISTRIBUTION'

    def test_markdown_low_vol_falling_price(self):
        """Low volume + falling price = MARKDOWN."""
        state = SectorRegimeDetector.classify(
            rel_vol=0.6, velocity=-0.05, acceleration=0.0, change_pct=-1.0
        )
        assert state == 'MARKDOWN'

    def test_consolidation_default(self):
        """Neutral conditions should default to CONSOLIDATION."""
        state = SectorRegimeDetector.classify(
            rel_vol=1.0, velocity=0.01, acceleration=0.0, change_pct=0.1
        )
        assert state == 'CONSOLIDATION'


# ================================================================
# SectorFlowEngine.get_global_volume_heatmap Tests
# ================================================================

class TestGlobalVolumeHeatmap:

    def _make_mcp_items(self, tickers_data: list[dict]) -> list[dict]:
        """Helper: creates minimal MCP response items."""
        return tickers_data

    def test_domestic_etfs_parsed(self):
        """Domestic XL ETFs should appear in heatmap from MCP response."""
        engine = SectorFlowEngine()
        mcp_items = [
            {'ticker': 'XLK', 'relative_volume': 1.8, 'change': 0.7},
            {'ticker': 'XLF', 'relative_volume': 0.9, 'change': -0.2},
        ]
        df = engine.get_global_volume_heatmap(
            mcp_response=mcp_items, include_dynamics=False
        )
        assert not df.empty
        assert 'XLK' in df['etf'].values
        assert 'XLF' in df['etf'].values

    def test_international_etfs_parsed(self):
        """International ETFs (EEM, EFA, VGK…) must be correctly identified."""
        engine = SectorFlowEngine()
        mcp_items = [
            {'ticker': 'EEM', 'relative_volume': 2.3, 'change': -1.1},
            {'ticker': 'EFA', 'relative_volume': 0.7, 'change': 0.2},
            {'ticker': 'VGK', 'relative_volume': 1.6, 'change': 0.5},
        ]
        df = engine.get_global_volume_heatmap(
            mcp_response=mcp_items, include_dynamics=False
        )
        int_rows = df[df['universe'] == 'International']
        assert len(int_rows) == 3

    def test_flow_signal_accumulation_active(self):
        """High rvol + positive change should yield ACCUMULATION_ACTIVE."""
        engine = SectorFlowEngine()
        mcp_items = [{'ticker': 'XLK', 'relative_volume': 2.0, 'change': 0.8}]
        df = engine.get_global_volume_heatmap(mcp_response=mcp_items, include_dynamics=False)
        assert df.iloc[0]['flow_signal'] == 'ACCUMULATION_ACTIVE'

    def test_flow_signal_distribution(self):
        """High rvol + negative change  should yield DISTRIBUTION."""
        engine = SectorFlowEngine()
        mcp_items = [{'ticker': 'EEM', 'relative_volume': 2.1, 'change': -1.5}]
        df = engine.get_global_volume_heatmap(mcp_response=mcp_items, include_dynamics=False)
        assert df.iloc[0]['flow_signal'] == 'DISTRIBUTION'

    def test_sorted_by_rel_vol_without_dynamics(self):
        """Without dynamics, DataFrame should be sorted descending by rel_vol."""
        engine = SectorFlowEngine()
        mcp_items = [
            {'ticker': 'XLK', 'relative_volume': 1.2, 'change': 0.1},
            {'ticker': 'EEM', 'relative_volume': 2.5, 'change': -0.5},
            {'ticker': 'XLF', 'relative_volume': 0.8, 'change': 0.2},
        ]
        df = engine.get_global_volume_heatmap(mcp_response=mcp_items, include_dynamics=False)
        rvols = df['rel_vol'].tolist()
        assert rvols == sorted(rvols, reverse=True)

    def test_unknown_ticker_ignored(self):
        """Tickers not in the ETF registry should be silently dropped."""
        engine = SectorFlowEngine()
        mcp_items = [
            {'ticker': 'AAPL', 'relative_volume': 3.0, 'change': 1.5},  # Not an ETF
            {'ticker': 'XLK', 'relative_volume': 1.5, 'change': 0.3},
        ]
        df = engine.get_global_volume_heatmap(mcp_response=mcp_items, include_dynamics=False)
        assert 'AAPL' not in df['etf'].values
        assert 'XLK' in df['etf'].values

    def test_empty_mcp_returns_empty_df(self):
        """Empty MCP response with no yfinance fallback should return empty DF."""
        engine = SectorFlowEngine()
        df = engine.get_global_volume_heatmap(mcp_response=[], include_dynamics=False)
        assert df.empty

    def test_includes_dynamics_adds_columns(self):
        """With include_dynamics=True, vel_rvol and wyckoff_state columns are present."""
        engine = SectorFlowEngine()
        mcp_items = [
            {'ticker': 'XLK', 'relative_volume': 1.5, 'change': 0.4},
            {'ticker': 'EEM', 'relative_volume': 1.8, 'change': -0.6},
        ]
        df = engine.get_global_volume_heatmap(mcp_response=mcp_items, include_dynamics=True)
        assert 'vel_rvol' in df.columns
        assert 'wyckoff_state' in df.columns

    def test_international_all_8_etfs_recognized(self):
        """All 8 international ETFs in INTERNATIONAL_ETFS must be accepted."""
        engine = SectorFlowEngine()
        intl_tickers = list(SectorFlowEngine.INTERNATIONAL_ETFS.values())
        mcp_items = [
            {'ticker': t, 'relative_volume': 1.0, 'change': 0.0}
            for t in intl_tickers
        ]
        df = engine.get_global_volume_heatmap(mcp_response=mcp_items, include_dynamics=False)
        found = set(df['etf'].values)
        assert set(intl_tickers).issubset(found), \
            f"Missing ETFs: {set(intl_tickers) - found}"
