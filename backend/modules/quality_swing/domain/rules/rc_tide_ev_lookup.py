"""
Real EV Lookup Adapter — Pure Domain Rule for Quality Swing
============================================================
Loads rc_tide_ev_derived.json and provides point-in-time Expected Value (EV)
and Dual Confluence Signal (P(bull) x EV) queries with:
  1. Cascading Fallback Hierarchy (L3 -> L2 -> L1 -> L0)
  2. Dynamic Flexible Fatigue Evaluation (based on run_length delta EV)
  3. Risk/Reward Asymmetry Ratio (E[ret_max] / |E[ret_min]|)

Clean Architecture: Pure domain rule. Loads JSON once, no IO after init.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_DERIVED_TABLE: Optional[dict] = None
_DERIVED_PATH = Path(__file__).parent / "rc_tide_ev_derived.json"

RUN_BUCKET_KEYS = [
    (1, 1, "1"),
    (2, 2, "2"),
    (3, 4, "3-4"),
    (5, 7, "5-7"),
    (8, 10, "8-10"),
    (11, 9999, "11+"),
]


@dataclass(frozen=True)
class RealEVSignal:
    """Result of Real Point-in-Time EV lookup."""
    state_key: str          # e.g. "T+++|C+++|<"
    level: str              # "zz25", "zz50", "zz75"
    fallback_level: str     # "L3", "L2", "L1", "L0"
    signal: str             # "ACCUMULATE", "BUY_DIP", "NEUTRAL", "TRIM"
    
    p_bull: float           # P(next = MAX)
    p_bear: float           # P(next = MIN)
    ev: float               # Point-in-Time Real EV
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
    
    # Unobserved State Notification & Fallback Context
    is_unobserved_state: bool = False
    fallback_reason: str = "EXACT_L3_MATCH"
    
    @property
    def is_accumulate(self) -> bool:
        return (self.action_code in ("STK_ACCUMULATE_STRUCTURAL", "STK_BUY_DIP_TACTICAL", "STK_ACCUMULATE_PASSIVE") or self.signal in ("ACCUMULATE", "BUY_DIP")) and self.fatigue_type != "FATIGUE_RISK"

    @property
    def is_trim(self) -> bool:
        return self.action_code in ("STK_TRIM_TACTICAL", "STK_DISTRIBUTE_DECAY") or self.signal == "TRIM" or (self.fatigue_type == "FATIGUE_RISK" and self.ev < 0.002)


    @property
    def is_high_asymmetry(self) -> bool:
        return self.rr_asymmetry >= 2.5 and self.p_bull >= 0.50


def _ensure_table_loaded() -> dict:
    """Load rc_ev_derived.json lazily as a singleton."""
    global _DERIVED_TABLE
    if _DERIVED_TABLE is None:
        if not _DERIVED_PATH.exists():
            logger.warning(f"rc_ev_derived.json not found at {_DERIVED_PATH}")
            return {}
        with open(_DERIVED_PATH) as f:
            _DERIVED_TABLE = json.load(f)
    return _DERIVED_TABLE


def _get_run_bucket_label(run_length: int) -> str:
    """Map run_length to bucket string label."""
    for lo, hi, label in RUN_BUCKET_KEYS:
        if lo <= run_length <= hi:
            return label
    return "11+"


def _evaluate_fatigue(fatigue_buckets: dict, run_length: int, base_ev: float) -> Tuple[str, float]:
    """Dynamically evaluate fatigue behavior based on raw bucket metrics."""
    if not fatigue_buckets or "1" not in fatigue_buckets:
        return "STABLE", 0.0

    b1_ev = fatigue_buckets["1"].get("ev", base_ev)
    b_label = _get_run_bucket_label(run_length)
    
    current_bucket = fatigue_buckets.get(b_label)
    if not current_bucket:
        return "STABLE", 0.0

    current_ev = current_bucket.get("ev", base_ev)
    delta_ev = round(current_ev - b1_ev, 6)

    if delta_ev <= -0.015:
        fatigue_type = "FATIGUE_RISK"
    elif delta_ev >= 0.010:
        fatigue_type = "ACCUMULATING"
    else:
        fatigue_type = "STABLE"

    return fatigue_type, delta_ev


def lookup_real_ev(
    t_slope: str,
    c_slope: str,
    svw: str,
    level: str = "zz50",
    run_length: int = 1,
    min_l3_samples: int = 1,
) -> Optional[RealEVSignal]:
    """Query Real EV table with cascading fallbacks L3 -> L2 -> L1 -> L0.

    Preserves extreme deviation states (n >= 1) without artificial fallback degradation.
    Notifies and logs whenever an unobserved state forces a fallback.

    Args:
        t_slope: Marea slope string (e.g. "T+++")
        c_slope: Corriente slope string (e.g. "C+++")
        svw: VWAP wave position string (e.g. "<")
        level: Zigzag scale ("zz25", "zz50", "zz75")
        run_length: Consecutive bars in current L3 state
        min_l3_samples: Minimum observations required (default 1 to preserve rare tail states)

    Returns:
        RealEVSignal instance or None if table empty.
    """
    table = _ensure_table_loaded()
    if not table:
        return None

    l3_key = f"{t_slope}|{c_slope}|{svw}"
    l2_key = f"{t_slope}|{c_slope}"
    l1_key = t_slope

    l3_states = table.get("l3_states", {})
    l2_states = table.get("l2_mid_macro", {})
    l1_states = table.get("l1_macro", {})
    l0_global = table.get("l0_global", {}).get("levels", {})

    target_data = None
    fallback_level = "L0"
    matched_key = l3_key
    is_unobserved = False
    fallback_reason = "EXACT_L3_MATCH"

    # 1. Check L3
    if l3_key in l3_states:
        lvl_data = l3_states[l3_key].get("levels", {}).get(level)
        if lvl_data and lvl_data.get("n", 0) >= min_l3_samples:
            target_data = lvl_data
            fallback_level = "L3"

    # 2. Fallback to L2
    if target_data is None:
        is_unobserved = True
        logger.info(f"⚠️ UNOBSERVED STATE ALERT: L3 state '{l3_key}' not found or n < {min_l3_samples}. Cascading fallback to L2 '{l2_key}' for long-term macro trend baseline.")
        fallback_reason = f"UNOBSERVED_L3_FALLBACK_TO_L2 ({l3_key})"
        if l2_key in l2_states:
            lvl_data = l2_states[l2_key].get("levels", {}).get(level)
            if lvl_data and lvl_data.get("n", 0) >= 1:
                target_data = lvl_data
                fallback_level = "L2"
                matched_key = l2_key

    # 3. Fallback to L1
    if target_data is None:
        logger.warning(f"⚠️ UNOBSERVED MACRO ALERT: L2 state '{l2_key}' not found. Cascading fallback to L1 '{l1_key}'.")
        fallback_reason = f"UNOBSERVED_L2_FALLBACK_TO_L1 ({l2_key})"
        if l1_key in l1_states:
            lvl_data = l1_states[l1_key].get("levels", {}).get(level)
            if lvl_data and lvl_data.get("n", 0) >= 1:
                target_data = lvl_data
                fallback_level = "L1"
                matched_key = l1_key

    # 4. Fallback to L0
    if target_data is None:
        logger.warning(f"⚠️ UNOBSERVED GLOBAL ALERT: Full state hierarchy missing for '{l3_key}'. Falling back to L0 Global Baseline.")
        fallback_reason = f"UNOBSERVED_HIERARCHY_FALLBACK_TO_L0 ({l3_key})"
        target_data = l0_global.get(level)
        fallback_level = "L0"
        matched_key = "GLOBAL"

    if not target_data:
        return None

    base_ev = target_data.get("ev", 0.0)
    p_bull = target_data.get("p_bull", 0.5)
    fatigue_buckets = target_data.get("fatigue_buckets", {})
    fatigue_type, delta_ev = _evaluate_fatigue(fatigue_buckets, run_length, base_ev)

    # Classify signal dynamically in Python (Fact Store contains pure numeric data)
    if p_bull >= 0.55 and base_ev >= 0.005:
        derived_signal = "ACCUMULATE"
    elif p_bull >= 0.52 and base_ev >= 0.002:
        derived_signal = "BUY_DIP"
    elif p_bull <= 0.45 or base_ev <= -0.005:
        derived_signal = "TRIM"
    else:
        derived_signal = "NEUTRAL"

    return RealEVSignal(
        state_key=matched_key,
        level=level,
        fallback_level=fallback_level,
        signal=derived_signal,
        p_bull=p_bull,

        p_bear=target_data.get("p_bear", 0.5),
        ev=base_ev,
        sharpe=target_data.get("sharpe", 0.0),
        e_ret_min=target_data.get("e_ret_min", 0.0),
        e_ret_max=target_data.get("e_ret_max", 0.0),
        e_days=target_data.get("e_days", 1.0),
        e_speed=target_data.get("e_speed", 0.0),
        rr_asymmetry=target_data.get("rr_asymmetry", 1.0),
        ev_per_day=target_data.get("ev_per_day", 0.0),
        n_samples=target_data.get("n", 0),
        fatigue_type=fatigue_type,
        fatigue_delta_ev=delta_ev,
        is_unobserved_state=is_unobserved,
        fallback_reason=fallback_reason,
    )
