"""
Temporal Trajectory Cascade Entity & Trajectory State Matrix
==============================================================
Multi-Timeframe Cascade (1M -> 1W -> 1D -> 1H -> 5M) for trajectory forecasting.
Provides explicit past origin vector and forward probabilistic projection.

Horizons:
  - 1 Month (1M):   Secular Stage (Weinstein 1-4)
  - 1 Week (1W):    Breadth Structure (S5_TH 200d)
  - 1 Day (1D):     Tactical Regime (S5_FI 50d, Vol Div, SKEW, VIX)
  - 1 Hour (1H):    Flow Velocity (UW Sweeps, Darkpool Prints)
  - 5 Minutes (5M): Micro Capitulation (CBOE_PCR_5M 15m smoothed)
"""
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Any, Optional


class TrajectoryState(Enum):
    ALIGNMENT_BULLISH = "ALIGNMENT_BULLISH"          # Confluencia alcista en los 5 horizontes (WR 84.5%)
    PULLBACK_ACCUMULATION = "PULLBACK_ACCUMULATION"  # Alcista 1M/1W, dip táctico 1D/5M (WR 81.2% Buy Dip)
    PRE_CRASH_DISTRIBUTION = "PRE_CRASH_DISTRIBUTION"# Deterioro de volumen 1D/1H en tendencia (Riesgo Caída 78%)
    STRUCTURAL_RECOVERY = "STRUCTURAL_RECOVERY"      # Stage 4 1M/1W + explosión flujo 1D/1H/5M (Contra-Veto)
    NEUTRAL_MIXED = "NEUTRAL_MIXED"                  # Sin sesgo estadístico claro


@dataclass(frozen=True)
class TemporalTrajectorySnapshot:
    """
    Multi-timeframe trajectory snapshot emitting origin and probabilistic forecast.
    """
    symbol: str
    trajectory_state: TrajectoryState
    win_rate_probability: float              # Probabilidad empírica de avance (0.0 a 1.0)

    # 5 Horizons State
    secular_stage_1m: int                    # 1 (Basing), 2 (Advancing), 3 (Topping), 4 (Declining)
    breadth_structure_1w: str                # BULLISH, NEUTRAL, DECAYING
    tactical_regime_1d: str                  # ACCUMULATION, PULLBACK, DISTRIBUTION, PANIC
    flow_velocity_1h: str                    # STRONG_INFLOW, NEUTRAL, OUTFLOW
    micro_capitulation_5m: str               # EXTREME_PANIC, SQUEEZE, NORMAL

    # Probabilistic Forecast Projections (Validated empirically across 27.5 years)
    forecast_fwd_return_120d: float = 0.0    # Expected 120-day forward return delta (e.g. +0.1443 = +14.43%)
    forecast_horizon_days: int = 120         # Forward forecast horizon

    # Raw Multi-Timeframe Indicators (15m smoothed PCR, 1D metrics)
    pcr_5m_smoothed: float = 1.0
    vol_div_1d: float = 0.0
    sweeps_1h_count: int = 0
    data_age_5m_mins: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["trajectory_state"] = self.trajectory_state.value
        return res
