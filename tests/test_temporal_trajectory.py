"""
Unit Tests — Temporal Trajectory Cascade (1M -> 1W -> 1D -> 1H -> 5M)
========================================================================
Tests 5-horizon trajectory classification, 15m CBOE_PCR_5M smoothing,
and data age degradation.
"""
import pytest
from backend.modules.causal_investigation.domain.entities.temporal_trajectory import (
    TrajectoryState,
    TemporalTrajectorySnapshot,
)
from backend.modules.causal_investigation.domain.rules.temporal_trajectory_rules import (
    evaluate_temporal_trajectory,
)


def test_alignment_bullish_cascade():
    """Test 1: Full bullish alignment across all 5 horizons -> ALIGNMENT_BULLISH."""
    snap = evaluate_temporal_trajectory(
        symbol="XLK",
        weinstein_stage_1m=2,
        s5_th_1w=75.0,
        vol_div_1d=5.0,
        rsi_1d=60.0,
        sweeps_1h_count=10,
        pcr_5m_bars=[0.75, 0.70, 0.65],
        data_age_5m_mins=5.0,
    )
    assert snap.trajectory_state == TrajectoryState.ALIGNMENT_BULLISH
    assert snap.win_rate_probability == 0.845
    assert snap.micro_capitulation_5m == "NORMAL"
    assert snap.pcr_5m_smoothed == 0.70


def test_pullback_accumulation_cascade():
    """Test 2: Stage 2 + 1D Dip (RSI 35) + 5M Capitulation (PCR 5M > 1.40) -> PULLBACK_ACCUMULATION."""
    snap = evaluate_temporal_trajectory(
        symbol="NVDA",
        weinstein_stage_1m=2,
        s5_th_1w=65.0,
        vol_div_1d=18.0,
        rsi_1d=35.0,
        sweeps_1h_count=5,
        pcr_5m_bars=[1.35, 1.45, 1.55],  # 3-bar smoothed = 1.45 (EXTREME_PANIC)
        data_age_5m_mins=8.0,
    )
    assert snap.trajectory_state == TrajectoryState.PULLBACK_ACCUMULATION
    assert snap.win_rate_probability == 0.812
    assert snap.micro_capitulation_5m == "EXTREME_PANIC"
    assert snap.pcr_5m_smoothed == 1.45


def test_blind_spot_1_smoothing_prevents_single_bar_noise():
    """Test 3: Single 5M bar spike (1.60) surrounded by low PCR (0.80, 0.80) -> Smoothed 1.06 (NOT EXTREME_PANIC)."""
    snap = evaluate_temporal_trajectory(
        symbol="AAPL",
        weinstein_stage_1m=2,
        s5_th_1w=70.0,
        vol_div_1d=0.0,
        pcr_5m_bars=[0.80, 0.80, 1.60],  # Smoothed = 1.066
        data_age_5m_mins=2.0,
    )
    assert snap.pcr_5m_smoothed == 1.067
    assert snap.micro_capitulation_5m == "NORMAL"


def test_blind_spot_5_stale_5m_data_degrades_gracefully():
    """Test 4: 5M data older than 30 mins degrades to STALE_DATA_NEUTRAL."""
    snap = evaluate_temporal_trajectory(
        symbol="MSFT",
        weinstein_stage_1m=2,
        s5_th_1w=65.0,
        vol_div_1d=0.0,
        pcr_5m_bars=[1.60, 1.60, 1.60],
        data_age_5m_mins=45.0,  # >30 mins stale
    )
    assert snap.micro_capitulation_5m == "STALE_DATA_NEUTRAL"


def test_pre_crash_distribution_cascade():
    """Test 5: Stage 3 + Decaying Breadth + Distribution -> PRE_CRASH_DISTRIBUTION."""
    snap = evaluate_temporal_trajectory(
        symbol="XLY",
        weinstein_stage_1m=3,
        s5_th_1w=30.0,
        vol_div_1d=-15.0,
        sweeps_1h_count=1,
    )
    assert snap.trajectory_state == TrajectoryState.PRE_CRASH_DISTRIBUTION
    assert snap.win_rate_probability == 0.220


def test_structural_recovery_cascade():
    """Test 6: Stage 4 secular trend + massive institutional sweep inflow (10+) -> STRUCTURAL_RECOVERY."""
    snap = evaluate_temporal_trajectory(
        symbol="XLV",
        weinstein_stage_1m=4,
        s5_th_1w=40.0,
        vol_div_1d=20.0,
        sweeps_1h_count=12,
    )
    assert snap.trajectory_state == TrajectoryState.STRUCTURAL_RECOVERY
    assert snap.win_rate_probability == 0.765


def test_neutral_mixed_cascade():
    """Test 7: Unclear or conflicting indicators -> NEUTRAL_MIXED."""
    snap = evaluate_temporal_trajectory(
        symbol="XLE",
        weinstein_stage_1m=1,
        s5_th_1w=50.0,
        vol_div_1d=0.0,
        sweeps_1h_count=3,
    )
    assert snap.trajectory_state == TrajectoryState.NEUTRAL_MIXED
    assert snap.win_rate_probability == 0.550

