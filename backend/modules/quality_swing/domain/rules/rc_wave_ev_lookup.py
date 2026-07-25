"""
Real Wave EV Lookup Adapter — Pure Domain Rule for Quality Swing
==================================================================
Loads rc_wave_ev_derived.json and provides point-in-time Expected Value (EV)
and Micro-Wave Timing queries with:
  1. Multi-Resolution Fallback Hierarchy (L1 -> L2 -> L3)
  2. Dynamic Fatigue Evaluation (based on run_length delta EV)
  3. Risk/Reward Asymmetry Ratio (E[ret_max] / |E[ret_min]|)
  4. Universal Wave Signal Taxonomy Mapping (WAVE_*)

Clean Architecture: Pure domain rule. Loads JSON once, no IO after init.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_WAVE_EV_TABLE: Optional[dict] = None
_WAVE_EV_PATH = Path(__file__).parent / "rc_wave_ev_derived.json"

RUN_BUCKET_KEYS = [
    (1, 1, "1"),
    (2, 2, "2"),
    (3, 4, "3-4"),
    (5, 7, "5-7"),
    (8, 10, "8-10"),
    (11, 9999, "11+"),
]


@dataclass(frozen=True)
class RealWaveEVSignal:
    """Result of Real Point-in-Time Wave EV lookup."""
    state_key: str          # e.g. "L1:W+++|σVc:<<|σc:<<|vel:▼"
    level: str              # "zz25", "zz50", "zz75"
    action_code: str        # Universal Wave Action Code: WAVE_EXHAUSTION_BOTTOM, etc.
    urgency_level: str      # IMMEDIATE, HIGH, PASSIVE, NORMAL
    
    p_bull: float           # P(next = MAX)
    p_bear: float           # P(next = MIN)
    ev: float               # Point-in-Time Real Micro EV
    sharpe: float           # Real EV / std(real_return)
    e_ret_min: float        # Expected real drawdown to next MIN pivot
    e_ret_max: float        # Expected real gain to next MAX pivot
    e_days: float           # Expected days to next pivot
    e_speed: float          # Real return speed per day
    rr_asymmetry: float     # E[ret_max] / |E[ret_min]|
    ev_per_day: float       # EV / e_days
    n_samples: int          # Sample size for this state/level
    
    # Dynamic Fatigue Analysis
    fatigue_type: str       # "ACCUMULATING", "FATIGUE_RISK", "STABLE"
    fatigue_delta_ev: float # EV(run_bucket) - EV(bucket_1)
    
    is_unobserved_state: bool = False


def _ensure_wave_ev_loaded() -> dict:
    """Load rc_wave_ev_derived.json lazily as a singleton."""
    global _WAVE_EV_TABLE
    if _WAVE_EV_TABLE is not None:
        return _WAVE_EV_TABLE

    if not _WAVE_EV_PATH.exists():
        logger.warning(f"Wave EV derived table not found at {_WAVE_EV_PATH}")
        _WAVE_EV_TABLE = {"states": {}}
        return _WAVE_EV_TABLE

    with open(_WAVE_EV_PATH, "r", encoding="utf-8") as f:
        _WAVE_EV_TABLE = json.load(f)

    n_states = len(_WAVE_EV_TABLE.get("states", {}))
    logger.info(f"Loaded Wave EV derived table with {n_states} states")
    return _WAVE_EV_TABLE


def lookup_real_wave_ev(
    wave_slope: float,
    vwap_sigma_current: float,
    sigma_current: float,
    vel_svw: float,
    level: str = "zz50",
    run_length: int = 1,
) -> Optional[RealWaveEVSignal]:
    """Look up point-in-time Micro-Wave Expected Value (EV)."""
    table = _ensure_wave_ev_loaded()
    states = table.get("states", {})
    if not states:
        return None

    # Classify bins to construct key
    from backend.modules.quality_swing.domain.rules.rc_wave_lookup import (
        _classify_wave_slope,
        _classify_sigma,
        _classify_vel,
    )
    w_bin = _classify_wave_slope(wave_slope)
    svc_bin = _classify_sigma(vwap_sigma_current)
    sc_bin = _classify_sigma(sigma_current)
    v_bin = _classify_vel(vel_svw)

    state_key = f"L1:{w_bin}|σVc:{svc_bin}|σc:{sc_bin}|vel:{v_bin}"
    state_data = states.get(state_key)

    # Fallback to L2 or L3 if state not found
    is_unobserved = False
    if not state_data:
        l2_key = f"L2:{w_bin}|σVc:{svc_bin}"
        state_data = states.get(l2_key)
        if not state_data:
            l3_key = f"L3:σVc:{svc_bin}"
            state_data = states.get(l3_key)
            if not state_data:
                return None
        is_unobserved = True

    level_data = state_data.get("derived_levels", {}).get(level, {})
    if not level_data:
        return None

    # Fatigue Analysis
    fb_data = level_data.get("fatigue_buckets", {})
    bucket_1_ev = fb_data.get("1", {}).get("ev", level_data.get("ev", 0.0))
    
    # Find matching bucket for run_length
    curr_ev = level_data.get("ev", 0.0)
    for r_min, r_max, b_key in RUN_BUCKET_KEYS:
        if r_min <= run_length <= r_max:
            if b_key in fb_data:
                curr_ev = fb_data[b_key].get("ev", curr_ev)
            break

    delta_ev = curr_ev - bucket_1_ev
    if delta_ev < -0.01:
        fatigue = "FATIGUE_RISK"
    elif delta_ev > 0.01:
        fatigue = "ACCUMULATING"
    else:
        fatigue = "STABLE"

    # Classify Wave Action Code via SignalCataloger
    from backend.modules.quality_swing.domain.rules.signal_cataloger import (
        SignalCataloger,
        WaveFeatureVector,
    )
    identity = state_data.get("identity", {})
    features = WaveFeatureVector(
        wave_direction=identity.get("wave_direction", "NEUTRAL"),
        wave_zone=identity.get("wave_zone", "FAIR_VALUE"),
        channel_zone=identity.get("channel_zone", "FAIR_VALUE"),
        momentum_state=identity.get("momentum_state", "NEUTRAL"),
        n_samples=state_data.get("n_total", 0),
        bot_lift=level_data.get("p_bull", 0.5) / 0.5,
        top_lift=level_data.get("p_bear", 0.5) / 0.5,
        bot_clean=level_data.get("p_bull", 0.5) * 100.0,
        top_clean=level_data.get("p_bear", 0.5) * 100.0,
        asymmetry_bias="STRONG_BOTTOM" if level_data.get("p_bull", 0.5) > 0.6 else "NEUTRAL",
    )
    _, action_code, urgency, _ = SignalCataloger.classify_wave(features)

    return RealWaveEVSignal(
        state_key=state_key,
        level=level,
        action_code=action_code,
        urgency_level=urgency,
        p_bull=level_data.get("p_bull", 0.5),
        p_bear=level_data.get("p_bear", 0.5),
        ev=curr_ev,
        sharpe=level_data.get("sharpe", 0.0),
        e_ret_min=level_data.get("e_ret_min", 0.0),
        e_ret_max=level_data.get("e_ret_max", 0.0),
        e_days=level_data.get("e_days", 1.0),
        e_speed=level_data.get("e_speed", 0.0),
        rr_asymmetry=level_data.get("rr_asymmetry", 1.0),
        ev_per_day=level_data.get("ev_per_day", 0.0),
        n_samples=level_data.get("n", 0),
        fatigue_type=fatigue,
        fatigue_delta_ev=delta_ev,
        is_unobserved_state=is_unobserved,
    )
