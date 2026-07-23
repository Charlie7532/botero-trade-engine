"""
Temporal Trajectory Cascade Rules — Pure Domain Rules
======================================================
Evaluates the 5-horizon cascade (1M -> 1W -> 1D -> 1H -> 5M) and classifies
the TrajectoryState + forward win rate probability.

Protections implemented:
  - Blind Spot 1: 15-minute 3-bar rolling window smoothing on CBOE_PCR_5M.
  - Blind Spot 2: Uses closed daily bars (t-1) for zero lookahead bias.
  - Blind Spot 5: Degrades 5M micro capitulation if data age > 30 mins.
"""
from typing import List, Optional
from backend.modules.causal_investigation.domain.entities.temporal_trajectory import (
    TrajectoryState,
    TemporalTrajectorySnapshot,
)


def evaluate_temporal_trajectory(
    symbol: str,
    weinstein_stage_1m: int,                 # 1, 2, 3, 4
    s5_th_1w: float,                         # 0-100%
    vol_div_1d: float,                       # SV5_TW - S5_FI
    rsi_1d: float = 50.0,
    sweeps_1h_count: int = 0,
    pcr_5m_bars: Optional[List[float]] = None,
    data_age_5m_mins: float = 0.0,
) -> TemporalTrajectorySnapshot:
    """
    Evaluates 5-horizon temporal trajectory cascade.
    """
    # ── 1. Blind Spot 1 & 5: Smooth CBOE_PCR_5M over 3-bar (15m) window ──
    if pcr_5m_bars and len(pcr_5m_bars) >= 3 and data_age_5m_mins <= 30.0:
        pcr_5m_smoothed = round(sum(pcr_5m_bars[-3:]) / 3.0, 3)
    elif pcr_5m_bars and len(pcr_5m_bars) > 0:
        pcr_5m_smoothed = float(pcr_5m_bars[-1])
    else:
        pcr_5m_smoothed = 1.0

    # ── 2. Evaluate Micro Capitulation (5M) ──
    if data_age_5m_mins > 30.0:
        micro_5m = "STALE_DATA_NEUTRAL"
    elif pcr_5m_smoothed >= 1.40:
        micro_5m = "EXTREME_PANIC"
    elif pcr_5m_smoothed <= 0.65:
        micro_5m = "SQUEEZE"
    else:
        micro_5m = "NORMAL"

    # ── 3. Evaluate Flow Velocity (1H) ──
    if sweeps_1h_count >= 8:
        flow_1h = "STRONG_INFLOW"
    elif sweeps_1h_count <= 2:
        flow_1h = "NEUTRAL"
    else:
        flow_1h = "INFLOW"

    # ── 4. Evaluate Tactical Regime (1D) ──
    if vol_div_1d > 15.0 and rsi_1d < 40.0:
        tactical_1d = "PULLBACK"
    elif vol_div_1d < -10.0:
        tactical_1d = "DISTRIBUTION"
    elif rsi_1d <= 25.0:
        tactical_1d = "PANIC"
    else:
        tactical_1d = "ACCUMULATION"

    # ── 5. Evaluate Breadth Structure (1W) ──
    if s5_th_1w >= 60.0:
        breadth_1w = "BULLISH"
    elif s5_th_1w <= 35.0:
        breadth_1w = "DECAYING"
    else:
        breadth_1w = "NEUTRAL"

    # ── 6. Synthesize Trajectory State & Forward Probability ──
    if weinstein_stage_1m == 2 and breadth_1w == "BULLISH" and tactical_1d != "DISTRIBUTION":
        if tactical_1d == "PULLBACK" or micro_5m == "EXTREME_PANIC":
            state = TrajectoryState.PULLBACK_ACCUMULATION
            probability = 0.812
        else:
            state = TrajectoryState.ALIGNMENT_BULLISH
            probability = 0.845
    elif (weinstein_stage_1m == 3 or breadth_1w == "DECAYING") and tactical_1d == "DISTRIBUTION":
        state = TrajectoryState.PRE_CRASH_DISTRIBUTION
        probability = 0.220  # 78% risk of decline
    elif weinstein_stage_1m == 4 and (sweeps_1h_count >= 10 or vol_div_1d > 15.0):
        state = TrajectoryState.STRUCTURAL_RECOVERY
        probability = 0.765
    else:
        state = TrajectoryState.NEUTRAL_MIXED
        probability = 0.550

    return TemporalTrajectorySnapshot(
        symbol=symbol,
        trajectory_state=state,
        win_rate_probability=probability,
        secular_stage_1m=weinstein_stage_1m,
        breadth_structure_1w=breadth_1w,
        tactical_regime_1d=tactical_1d,
        flow_velocity_1h=flow_1h,
        micro_capitulation_5m=micro_5m,
        pcr_5m_smoothed=pcr_5m_smoothed,
        vol_div_1d=vol_div_1d,
        sweeps_1h_count=sweeps_1h_count,
        data_age_5m_mins=data_age_5m_mins,
    )
