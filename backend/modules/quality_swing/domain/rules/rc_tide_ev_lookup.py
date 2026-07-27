"""
Real EV Lookup Adapter — Pure Domain Rule for Quality Swing
============================================================
Loads rc_tide_ev_derived.json and provides point-in-time Expected Value (EV)
and Dual Confluence Signal (P(bull) x EV) queries with:
  1. Cascading Fallback Hierarchy (L3 -> L2 -> L1 -> L0)
  2. Risk/Reward Asymmetry Ratio (E[ret_max] / |E[ret_min]|)
  3. Action Taxonomy Standard Compliance (STK_ACCUMULATE_STRUCTURAL, STK_BUY_DIP_TACTICAL, etc.)

Clean Architecture: Pure domain rule. Loads JSON once, no IO after init.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union

logger = logging.getLogger(__name__)

_DERIVED_TABLE: Optional[dict] = None
_DERIVED_PATH = Path(__file__).parent / "rc_tide_ev_derived.json"


@dataclass(frozen=True)
class RealEVSignal:
    """Result of Real Point-in-Time EV lookup."""
    state_key: str          # e.g. "T+++|C+++|<"
    level: str              # "zz25", "zz50", "zz75"
    fallback_level: str     # "L3", "L2", "L1", "L0"
    signal: str             # "ACCUMULATE", "BUY_DIP", "NEUTRAL", "TRIM"
    action_code: str        # Taxonomy action code (e.g. STK_BUY_DIP_TACTICAL)
    
    p_bull: float           # P(next = MIN / floor)
    p_bear: float           # P(next = MAX / ceiling)
    ev: float               # Point-in-Time Real EV net
    sharpe: float           # Real EV / std(real_return)
    e_ret_min: float        # Expected real drawdown to next MIN pivot
    e_ret_max: float        # Expected real gain to next MAX pivot
    e_days: float           # Expected days to next pivot
    rr_asymmetry: float     # E[ret_max] / |E[ret_min]|
    ev_per_day: float       # EV / e_days
    n_samples: int          # Sample size for this state/level
    is_rare_state: bool     # Low-N tail event flag
    
    is_unobserved_state: bool = False
    fallback_reason: str = "EXACT_L3_MATCH"
    
    @property
    def is_accumulate(self) -> bool:
        return self.action_code in ("STK_ACCUMULATE_STRUCTURAL", "STK_BUY_DIP_TACTICAL", "STK_ACCUMULATE_PASSIVE") or self.signal in ("ACCUMULATE", "BUY_DIP")

    @property
    def is_trim(self) -> bool:
        return self.action_code in ("STK_TRIM_TACTICAL", "STK_DISTRIBUTE_DECAY") or self.signal == "TRIM"

    @property
    def is_high_asymmetry(self) -> bool:
        return self.rr_asymmetry >= 2.5 and self.p_bull >= 0.50


def _ensure_table_loaded() -> dict:
    """Load rc_tide_ev_derived.json lazily as a singleton."""
    global _DERIVED_TABLE
    if _DERIVED_TABLE is None:
        if not _DERIVED_PATH.exists():
            logger.warning(f"rc_tide_ev_derived.json not found at {_DERIVED_PATH}")
            return {}
        with open(_DERIVED_PATH, "r", encoding="utf-8") as f:
            _DERIVED_TABLE = json.load(f)
    return _DERIVED_TABLE


def _classify_sigma_bin(val: Union[str, float, int]) -> str:
    """Convert numeric continuous vwap_sigma_wave or string to bin label."""
    if isinstance(val, (int, float)):
        if val < -1.0:
            return "<<"
        elif val < -0.3:
            return "<"
        elif val <= 0.3:
            return "~"
        elif val <= 1.0:
            return ">"
        else:
            return ">>"
    return str(val)


def lookup_real_ev(
    level: str = "zz25",
    t_slope: Optional[str] = None,
    c_slope: Optional[str] = None,
    svw: Optional[Union[str, float]] = None,
    min_l3_samples: int = 1,
    **kwargs,
) -> Optional[RealEVSignal]:
    """Query Real EV table with cascading fallbacks L3 -> L2 -> L1 -> L0.

    Accepts both short (t_slope, c_slope, svw) and full parameter names
    (tide_slope, current_slope, vwap_sigma_wave), and handles float vwap_sigma_wave.
    """
    table = _ensure_table_loaded()
    if not table:
        return None

    raw_t = t_slope if t_slope is not None else kwargs.get("tide_slope", "T~")
    raw_c = c_slope if c_slope is not None else kwargs.get("current_slope", "C~")
    raw_svw = svw if svw is not None else kwargs.get("vwap_sigma_wave", "~")

    atr_pct = kwargs.get("atr_pct", 0.01)

    if isinstance(raw_t, (int, float)):
        from backend.modules.quality_swing.domain.rules.rc_slope_classifier import _classify_one
        resolved_t = _classify_one(float(raw_t), "T", atr_pct)
    else:
        resolved_t = str(raw_t)

    if isinstance(raw_c, (int, float)):
        from backend.modules.quality_swing.domain.rules.rc_slope_classifier import _classify_one
        resolved_c = _classify_one(float(raw_c), "C", atr_pct)
    else:
        resolved_c = str(raw_c)

    resolved_svw = _classify_sigma_bin(raw_svw)

    l3_key = f"{resolved_t}|{resolved_c}|{resolved_svw}"
    l2_key = f"{resolved_t}|{resolved_c}"
    l1_key = resolved_t

    l3_states = table.get("l3_full_state", {})
    l2_states = table.get("l2_mid_macro", {})
    l1_states = table.get("l1_macro", {})
    l0_global = table.get("l0_global", {})

    target_data = None
    fallback_level = "L0"
    matched_key = l3_key
    is_unobserved = False
    fallback_reason = "EXACT_L3_MATCH"

    # 1. Check L3
    if l3_key in l3_states:
        lvl_data = l3_states[l3_key].get(level)
        if lvl_data and lvl_data.get("n", 0) >= min_l3_samples:
            target_data = lvl_data
            fallback_level = "L3"

    # 2. Fallback to L2
    if target_data is None:
        is_unobserved = True
        fallback_reason = f"UNOBSERVED_L3_FALLBACK_TO_L2 ({l3_key})"
        if l2_key in l2_states:
            lvl_data = l2_states[l2_key].get(level)
            if lvl_data and lvl_data.get("n", 0) >= 1:
                target_data = lvl_data
                fallback_level = "L2"
                matched_key = l2_key

    # 3. Fallback to L1
    if target_data is None:
        fallback_reason = f"UNOBSERVED_L2_FALLBACK_TO_L1 ({l2_key})"
        if l1_key in l1_states:
            lvl_data = l1_states[l1_key].get(level)
            if lvl_data and lvl_data.get("n", 0) >= 1:
                target_data = lvl_data
                fallback_level = "L1"
                matched_key = l1_key

    # 4. Fallback to L0
    if target_data is None:
        fallback_reason = f"UNOBSERVED_HIERARCHY_FALLBACK_TO_L0 ({l3_key})"
        target_data = l0_global.get(level, {})
        fallback_level = "L0"
        matched_key = "GLOBAL"

    if not target_data:
        return None

    p_bull = target_data.get("p_bull", 0.5)
    p_bear = target_data.get("p_bear", 0.5)
    ev_net = target_data.get("ev_net", 0.0)
    e_ret_max = target_data.get("e_ret_max", 0.0)
    e_ret_min = target_data.get("e_ret_min", 0.0)
    e_days = target_data.get("e_days", 10.0)
    ev_per_day = target_data.get("ev_per_day", 0.0)
    rr_asymmetry = target_data.get("rr_asymmetry", 1.0)
    sharpe = target_data.get("sharpe", 0.0)
    n_samples = target_data.get("n", 0)
    is_rare = target_data.get("is_rare_state", False)

    # Dynamic Institutional Action Taxonomy Classification
    if resolved_t in ("T---", "T--") and ev_net < 0.0:
        signal = "BLOCK"
        action_code = "STK_BLOCK_CRISIS"
    elif ev_net >= 0.005 and rr_asymmetry >= 1.5:
        signal = "ACCUMULATE"
        action_code = "STK_ACCUMULATE_STRUCTURAL"
    elif ev_net >= 0.002 or (resolved_svw in ("<<", "<") and ev_net > 0.0):
        signal = "BUY_DIP"
        action_code = "STK_BUY_DIP_TACTICAL"
    elif ev_net <= -0.003 or resolved_svw in (">>", ">"):
        signal = "TRIM"
        action_code = "STK_TRIM_TACTICAL"
    else:
        signal = "NEUTRAL"
        action_code = "STK_HOLD_STABLE"

    return RealEVSignal(
        state_key=matched_key,
        level=level,
        fallback_level=fallback_level,
        signal=signal,
        action_code=action_code,
        p_bull=p_bull,
        p_bear=p_bear,
        ev=ev_net,
        sharpe=sharpe,
        e_ret_min=e_ret_min,
        e_ret_max=e_ret_max,
        e_days=e_days,
        rr_asymmetry=rr_asymmetry,
        ev_per_day=ev_per_day,
        n_samples=n_samples,
        is_rare_state=is_rare,
        is_unobserved_state=is_unobserved,
        fallback_reason=fallback_reason,
    )
