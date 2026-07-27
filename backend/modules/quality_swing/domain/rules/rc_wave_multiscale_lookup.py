"""
Wave Multiscale Lookup Adapter — Pure Domain Rule for Quality Swing
====================================================================
Loads `rc_wave_multiscale_tree.json` and provides point-in-time Expected Value (EV)
and Micro-Wave Timing queries with:
  1. Multi-Resolution Fallback Cascade (L1 -> L2 -> L3 -> Global)
  2. Pure Quantitative Data Lookup (zero narrative text in JSON)
  3. External Python Signal Cataloger Delegation (SignalCataloger)
  4. Rare State Trapping (N < 30) for High-Priority Emergency Alerts (WAVE_ALERT_*)

Clean Architecture: Pure domain rule. Loads JSON lazily once, zero IO after init.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.modules.quality_swing.domain.rules.signal_cataloger import (
    WaveSignalCataloger,
    WaveFeatureVector,
)

logger = logging.getLogger(__name__)

_WAVE_TREE: Optional[dict] = None
_WAVE_TREE_PATH = Path(__file__).parent / "rc_wave_multiscale_tree.json"


@dataclass(frozen=True)
class RealWaveMultiscaleSignal:
    """Result of Pure Domain Wave Multiscale Lookup."""
    state_key: str          # e.g. "L1:W+++|σVc:<<|σc:<<|vel:▼"
    level: str              # "L1", "L2", "L3", "GLOBAL"
    signal_name: str        # e.g. "EXHAUSTION_BOTTOM", "RARE_CAPITULATION"
    action_code: str        # e.g. "WAVE_EXHAUSTION_BOTTOM", "WAVE_ALERT_RARE_CAPITULATION"
    urgency_level: str      # IMMEDIATE, HIGH, PASSIVE, NORMAL
    
    p_bull: float           # P(next pivot = MAX)
    p_bear: float           # P(next pivot = MIN)
    e_ret_max: float        # Expected return to next MAX pivot
    e_ret_min: float        # Expected drawdown to next MIN pivot
    rr_asymmetry: float     # e_ret_max / |e_ret_min|
    sharpe: float           # Sharpe ratio of micro-wave
    n_samples: int          # Sample count in Vault
    bot_avg_bars_to_turn: float
    top_avg_bars_to_turn: float
    
    is_rare_alert: bool = False


def _ensure_wave_tree_loaded() -> dict:
    """Load rc_wave_multiscale_tree.json lazily as a singleton."""
    global _WAVE_TREE
    if _WAVE_TREE is not None:
        return _WAVE_TREE

    if not _WAVE_TREE_PATH.exists():
        logger.warning(f"Wave Multiscale Tree JSON not found at {_WAVE_TREE_PATH}")
        _WAVE_TREE = {
            "states": {
                "GLOBAL": {
                    "n": 1000,
                    "p_bull": 0.50,
                    "p_bear": 0.50,
                    "e_ret_max": 0.025,
                    "e_ret_min": -0.025,
                    "rr_asymmetry": 1.0,
                    "sharpe": 1.0,
                    "bot_avg_bars_to_turn": 2.0,
                    "top_avg_bars_to_turn": 2.0,
                }
            }
        }
        return _WAVE_TREE

    with open(_WAVE_TREE_PATH, "r", encoding="utf-8") as f:
        _WAVE_TREE = json.load(f)

    n_states = len(_WAVE_TREE.get("states", {}))
    logger.info(f"Loaded Wave Multiscale Tree with {n_states} states")
    return _WAVE_TREE


def lookup_wave_multiscale_signal(
    wave_slope: float,
    vwap_sigma_current: float,
    sigma_current: float,
    vel_svw: float,
) -> Optional[RealWaveMultiscaleSignal]:
    """Look up Wave Micro-Timing Signal from the Pure Quantitative Tree."""
    tree = _ensure_wave_tree_loaded()
    states = tree.get("states", {})
    if not states:
        return None

    # Classify continuous floats into discrete bins
    from backend.modules.quality_swing.domain.rules.rc_wave_lookup import (
        _classify_wave_slope,
        _classify_sigma,
        _classify_vel_svw,
    )
    w_bin = _classify_wave_slope(wave_slope)
    svc_bin = _classify_sigma(vwap_sigma_current)
    sc_bin = _classify_sigma(sigma_current)
    vel_bin = _classify_vel_svw(vel_svw)

    l1_key = f"L1:{w_bin}|σVc:{svc_bin}|σc:{sc_bin}|vel:{vel_bin}"
    level = "L1"
    state_data = states.get(l1_key)

    # Cascading Fallback L1 -> L2 -> L3 -> Global
    if not state_data:
        l2_key = f"L2:{w_bin}|σVc:{svc_bin}"
        level = "L2"
        state_data = states.get(l2_key)
        if not state_data:
            l3_key = f"L3:{w_bin}"
            level = "L3"
            state_data = states.get(l3_key)
            if not state_data:
                state_data = {
                    "n": 1000,
                    "p_bull": 0.50,
                    "p_bear": 0.50,
                    "e_ret_max": 0.025,
                    "e_ret_min": -0.025,
                    "rr_asymmetry": 1.0,
                    "sharpe": 1.0,
                    "bot_avg_bars_to_turn": 2.0,
                    "top_avg_bars_to_turn": 2.0,
                }
                level = "GLOBAL"

    n_samples = state_data.get("n", 0)
    p_bull = state_data.get("p_bull", 0.50)
    p_bear = state_data.get("p_bear", 0.50)
    e_ret_max = state_data.get("e_ret_max", 0.025)
    e_ret_min = state_data.get("e_ret_min", -0.025)
    rr_asym = state_data.get("rr_asymmetry", 1.0)
    sharpe = state_data.get("sharpe", 1.0)

    # Delegate to external Python Signal Cataloger
    features = WaveFeatureVector(
        wave_direction=w_bin,
        wave_zone=sc_bin,
        channel_zone=svc_bin,
        momentum_state=vel_bin,
        n_samples=n_samples,
        bot_lift=p_bull / 0.5,
        top_lift=p_bear / 0.5,
        bot_clean=p_bull * 100.0,
        top_clean=p_bear * 100.0,
        asymmetry_bias="STRONG_BOTTOM" if p_bull >= 0.60 else "STRONG_TOP" if p_bear >= 0.60 else "NEUTRAL",
    )

    sig_name, action_code, urgency, scope = WaveSignalCataloger.classify(features)
    is_rare = n_samples < 30 or "WAVE_ALERT_" in action_code

    return RealWaveMultiscaleSignal(
        state_key=l1_key if level == "L1" else l2_key if level == "L2" else l3_key if level == "L3" else "GLOBAL",
        level=level,
        signal_name=sig_name,
        action_code=action_code,
        urgency_level=urgency,
        p_bull=p_bull,
        p_bear=p_bear,
        e_ret_max=e_ret_max,
        e_ret_min=e_ret_min,
        rr_asymmetry=rr_asym,
        sharpe=sharpe,
        n_samples=n_samples,
        bot_avg_bars_to_turn=state_data.get("bot_avg_bars_to_turn", 2.0),
        top_avg_bars_to_turn=state_data.get("top_avg_bars_to_turn", 2.0),
        is_rare_alert=is_rare,
    )
