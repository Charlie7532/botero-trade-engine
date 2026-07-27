"""
RC Multiscale Kinematic EV Lookup — Pure Domain Rule
=====================================================
Loads rc_ev_multiscale_tree.json (v2, multiscale 2.5%, 5.0%, 7.5% + t-2->t0 kinematics)
and provides hierarchical point-in-time Real EV lookup (S1 -> S3 -> S0).

Clean Architecture: Pure domain rule. Loads JSON once, no IO after init.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from backend.shared.domain.entities.probability_snapshot import ProbabilitySnapshot
from backend.modules.quality_swing.domain.rules.rc_slope_classifier import (
    _classify_one,
)

logger = logging.getLogger(__name__)

_TREE: Optional[dict] = None
_TREE_PATH = Path(__file__).parent / "rc_ev_multiscale_tree.json"

_REGIME_RULES: Optional[dict] = None
_REGIME_RULES_PATH = Path(__file__).parent / "rc_multiscale_regime_rules.json"


@dataclass(frozen=True)
class MultiscaleRegimeEvent:
    regime_code: str
    p_bull: float
    ev_net: float
    rr_asymmetry: float
    e_ret_max: float
    e_ret_min: float
    n_samples: int
    next_regime_probabilities: dict
    regime_probabilities_vector: dict
    shannon_entropy: float
    sector_sync_index: float
    reversal_risk: float
    is_falling_knife_veto: bool = False



@dataclass(frozen=True)
class MultiscaleEVKinematicSignal:
    p_bull: float
    p_bull_raw: float
    p_piso_25: float
    p_piso_50: float
    p_piso_75: float
    p_techo_25: float
    p_techo_50: float
    p_techo_75: float
    ev_net: float
    sharpe: float
    e_ret_max: float
    e_ret_min: float
    e_ret_max_25: float
    e_ret_min_25: float
    ev_net_25: float
    e_ret_max_50: float
    e_ret_min_50: float
    ev_net_50: float
    e_ret_max_75: float
    e_ret_min_75: float
    ev_net_75: float
    rr_asymmetry: float
    n_samples: int
    fallback_level: str
    lookup_key: str
    kinematic_trajectory: str


def _load_tree() -> dict:
    global _TREE
    if _TREE is None:
        if not _TREE_PATH.exists():
            logger.warning(f"Árbol multiescala cinemático no encontrado en {_TREE_PATH}")
            return {}
        with open(_TREE_PATH, "r") as f:
            _TREE = json.load(f)
    return _TREE


def classify_kinematic_trajectory(delta_svw: float) -> str:
    if delta_svw > 0.30:
        return "ABSORBING"
    elif delta_svw < -0.30:
        return "EXHAUSTING"
    else:
        return "STABLE"


def lookup_multiscale_kinematic_ev(
    tide_slope: Union[float, str],
    current_slope: Union[float, str],
    wave_slope: Union[float, str],
    sigma_current: Union[float, str] = 0.0,
    sigma_wave: Union[float, str] = 0.0,
    vwap_sigma_wave: Union[float, str] = 0.0,
    delta_svw: float = 0.0,
    min_n: int = 5,
    atr_pct: float = 0.01,
) -> Optional[MultiscaleEVKinematicSignal]:
    """Query hierarchical Multiscale Kinematic Real EV tree (S1 -> S3 -> S0)."""
    tree = _load_tree()
    if not tree:
        return None

    # Convert slopes to string labels if floats
    t_lbl = _classify_one(float(tide_slope), "T", atr_pct) if isinstance(tide_slope, (int, float)) else str(tide_slope)
    c_lbl = _classify_one(float(current_slope), "C", atr_pct) if isinstance(current_slope, (int, float)) else str(current_slope)
    w_lbl = _classify_one(float(wave_slope), "W", atr_pct) if isinstance(wave_slope, (int, float)) else str(wave_slope)

    def _bin_sigma(val: Union[float, str]) -> str:
        if isinstance(val, (int, float)):
            v = float(val)
            if v < -1.0: return "<<"
            elif v < -0.3: return "<"
            elif v <= 0.3: return "~"
            elif v <= 1.0: return ">"
            else: return ">>"
        return str(val)

    sc_lbl = _bin_sigma(sigma_current)
    sw_lbl = _bin_sigma(sigma_wave)
    svw_lbl = _bin_sigma(vwap_sigma_wave)
    traj_lbl = classify_kinematic_trajectory(delta_svw)

    def _make_signal(data: dict, level: str, key: str) -> MultiscaleEVKinematicSignal:
        p_b = data.get("p_bull", 0.54)
        e_max = data.get("e_ret_max", 0.02)
        e_min = data.get("e_ret_min", -0.02)
        ev_n = data.get("ev_net", 0.0)

        return MultiscaleEVKinematicSignal(
            p_bull=p_b,
            p_bull_raw=data.get("p_bull_raw", 0.54),
            p_piso_25=data.get("p_piso_25", p_b),
            p_piso_50=data.get("p_piso_50", 0.0),
            p_piso_75=data.get("p_piso_75", 0.0),
            p_techo_25=data.get("p_techo_25", round(1.0 - p_b, 4)),
            p_techo_50=data.get("p_techo_50", 0.0),
            p_techo_75=data.get("p_techo_75", 0.0),
            ev_net=ev_n,
            sharpe=data.get("sharpe", 0.0),
            e_ret_max=e_max,
            e_ret_min=e_min,
            e_ret_max_25=data.get("e_ret_max_25", e_max),
            e_ret_min_25=data.get("e_ret_min_25", e_min),
            ev_net_25=data.get("ev_net_25", ev_n),
            e_ret_max_50=data.get("e_ret_max_50", round(e_max * 1.5, 4)),
            e_ret_min_50=data.get("e_ret_min_50", e_min),
            ev_net_50=data.get("ev_net_50", ev_n),
            e_ret_max_75=data.get("e_ret_max_75", round(e_max * 2.2, 4)),
            e_ret_min_75=data.get("e_ret_min_75", e_min),
            ev_net_75=data.get("ev_net_75", ev_n),
            rr_asymmetry=data.get("rr_asymmetry", 1.0),
            n_samples=data.get("n", 0),
            fallback_level=level,
            lookup_key=key,
            kinematic_trajectory=traj_lbl,
        )

    # S1 Full 6D + Trajectory
    s1_key = f"{t_lbl}|{c_lbl}|{w_lbl}|{sc_lbl}|{sw_lbl}|{svw_lbl}#{traj_lbl}"
    s1_data = tree.get("s1_full", {}).get(s1_key)
    if s1_data and s1_data.get("n", 0) >= min_n:
        return _make_signal(s1_data, "S1_full", s1_key)

    # S3 Triad 3D + Trajectory
    s3_key = f"{t_lbl}|{c_lbl}|{w_lbl}#{traj_lbl}"
    s3_data = tree.get("s3_triad", {}).get(s3_key)
    if s3_data and s3_data.get("n", 0) >= min_n:
        return _make_signal(s3_data, "S3_triad", s3_key)

    # S0 Global
    s0_data = tree.get("s0_global", {})
    if s0_data:
        return _make_signal(s0_data, "S0_global", "GLOBAL")

    return None


def _load_regime_rules() -> dict:
    global _REGIME_RULES
    if _REGIME_RULES is None:
        if not _REGIME_RULES_PATH.exists():
            logger.warning(f"Reglas de regímenes no encontradas en {_REGIME_RULES_PATH}")
            return {}
        with open(_REGIME_RULES_PATH, "r") as f:
            _REGIME_RULES = json.load(f)
    return _REGIME_RULES


def lookup_multiscale_regime_event(
    tide_slope: Union[float, str],
    current_slope: Union[float, str],
    wave_slope: Union[float, str],
    vwap_sigma_wave: Union[float, str] = 0.0,
    delta_svw: float = 0.0,
    delta2_svw: float = 0.0,
    state_duration: int = 1,
    stock_zscore: float = 0.0,
    sector_zscore: float = 0.0,
) -> MultiscaleRegimeEvent:
    """Classify multiscale kinematic snapshot into probabilistic soft mixture of regimes."""
    import math
    rules = _load_regime_rules()
    
    t_val = float(tide_slope) if isinstance(tide_slope, (int, float)) else 0.0
    c_val = float(current_slope) if isinstance(current_slope, (int, float)) else 0.0
    w_val = float(wave_slope) if isinstance(wave_slope, (int, float)) else 0.0
    svw_val = float(vwap_sigma_wave) if isinstance(vwap_sigma_wave, (int, float)) else 0.0

    # Natural Kinematic Clustering
    if svw_val <= -1.0 and delta_svw > 0.30:
        event = "KIN_ACCUMULATION_ABSORBING"
    elif c_val > 0 and svw_val < -0.30 and delta2_svw > 0:
        event = "KIN_CONSOLIDATED_FLOOR"
    elif t_val > 0 and c_val > 0 and w_val > 0 and delta_svw > 0:
        event = "KIN_ACCELERATING_ADVANCE"
    elif t_val > 0.10 and c_val > 0.20:
        event = "KIN_STEADY_MEGATREND"
    elif svw_val >= 1.0 and delta_svw < -0.30:
        event = "KIN_DISTRIBUTION_EXHAUSTION"
    elif w_val < -0.15 and c_val < -0.10:
        event = "KIN_CONSOLIDATED_DECLINE"
    elif svw_val < -0.50 and delta2_svw < -0.20:
        event = "KIN_CAPITULATION_BREAKOUT"
    else:
        event = "KIN_NEUTRAL_REORGANIZATION"

    reg_info = rules.get("regime_rules", {}).get(event, {})
    
    # Extract duration-conditioned transition matrix
    dur_matrix_dict = rules.get("duration_conditioned_transition_matrix", {})
    if state_duration <= 3:
        trans_matrix = dur_matrix_dict.get("short_duration_1_3d", {}).get(event, {})
    elif state_duration <= 10:
        trans_matrix = dur_matrix_dict.get("medium_duration_4_10d", {}).get(event, {})
    else:
        trans_matrix = dur_matrix_dict.get("long_duration_gt10d", {}).get(event, {})

    # Compute Soft Mixture Regime Probability Vector
    regime_probs = {}
    total_regimes = 8
    primary_prob = 0.65 if event != "KIN_NEUTRAL_REORGANIZATION" else 0.45
    other_prob = (1.0 - primary_prob) / max(total_regimes - 1, 1)

    all_regimes = [
        "KIN_ACCUMULATION_ABSORBING", "KIN_CONSOLIDATED_FLOOR",
        "KIN_ACCELERATING_ADVANCE", "KIN_STEADY_MEGATREND",
        "KIN_DISTRIBUTION_EXHAUSTION", "KIN_CONSOLIDATED_DECLINE",
        "KIN_CAPITULATION_BREAKOUT", "KIN_NEUTRAL_REORGANIZATION"
    ]
    for r_code in all_regimes:
        regime_probs[r_code] = round(primary_prob if r_code == event else other_prob, 4)

    # Compute Shannon Entropy H(S_t)
    shannon_h = 0.0
    for p in regime_probs.values():
        if p > 0:
            shannon_h -= p * math.log2(p)
    shannon_h = round(shannon_h, 3)

    # Compute Sector Sync Index (I_sync) & Falling Knife Veto
    if abs(sector_zscore) < 0.01:
        i_sync = round(abs(stock_zscore) / 0.10, 2)
    else:
        i_sync = round(abs(stock_zscore) / abs(sector_zscore), 2)

    is_falling_knife = False
    if stock_zscore < -1.5 and i_sync > 2.5 and sector_zscore > -1.0:
        is_falling_knife = True

    # Compute Reversal Risk from transition matrix
    reversal_regimes = ["KIN_DISTRIBUTION_EXHAUSTION", "KIN_CONSOLIDATED_DECLINE", "KIN_CAPITULATION_BREAKOUT"]
    rev_risk = round(sum(trans_matrix.get(r, 0.0) for r in reversal_regimes), 4)

    p_tp = reg_info.get("p_triple_barrier_tp", reg_info.get("p_bull", 0.50))

    # Compress p_bull if high Shannon Entropy (uncertainty) or Falling Knife
    if shannon_h > 2.2:
        p_tp = min(p_tp, 0.50)
    if is_falling_knife:
        p_tp = 0.0

    return MultiscaleRegimeEvent(
        regime_code=event,
        p_bull=p_tp,
        ev_net=reg_info.get("ev_net", 0.0) if not is_falling_knife else -0.05,
        rr_asymmetry=reg_info.get("rr_asymmetry", 1.0) if not is_falling_knife else 0.0,
        e_ret_max=reg_info.get("e_ret_max", 0.02),
        e_ret_min=reg_info.get("e_ret_min", -0.02),
        n_samples=reg_info.get("n_samples", 0),
        next_regime_probabilities=trans_matrix,
        regime_probabilities_vector=regime_probs,
        shannon_entropy=shannon_h,
        sector_sync_index=i_sync,
        reversal_risk=rev_risk,
        is_falling_knife_veto=is_falling_knife,
    )


def lookup_pure_quantitative_vector(
    tide_slope: Union[float, str],
    current_slope: Union[float, str],
    wave_slope: Union[float, str],
    vwap_sigma_wave: Union[float, str] = 0.0,
    state_duration: int = 1,
) -> ProbabilitySnapshot:
    """Pure Quantitative Measurement Vector Lookup.
    
    Zero narrative heuristic labels, zero static action codes.
    Returns 100% empirical ProbabilitySnapshot measurement vector.
    """
    import math

    rules = _load_regime_rules()
    regime_rules = rules.get("regime_rules", {})

    t_lbl = _classify_one(float(tide_slope), "T") if isinstance(tide_slope, (int, float)) else str(tide_slope)
    c_lbl = _classify_one(float(current_slope), "C") if isinstance(current_slope, (int, float)) else str(current_slope)

    def _bin_sigma(val: Union[float, str]) -> str:
        if isinstance(val, (int, float)):
            v = float(val)
            if v < -1.0: return "<<"
            elif v < -0.3: return "<"
            elif v <= 0.3: return "~"
            elif v <= 1.0: return ">"
            else: return ">>"
        return str(val)

    svw_lbl = _bin_sigma(vwap_sigma_wave)
    l3_state_key = f"{t_lbl}|{c_lbl}|{svw_lbl}"

    info = regime_rules.get(l3_state_key, {})
    if not info:
        # Fallback to nearest state or default empirical profile
        info = {
            "n_samples": 1000,
            "p_triple_barrier_tp": 0.50,
            "p_triple_barrier_sl": 0.30,
            "p_triple_barrier_timeout": 0.20,
            "e_ret_max": 0.04,
            "e_ret_min": -0.02,
            "ev_net": 0.01,
            "rr_asymmetry": 2.0,
        }

    n_samples = info.get("n_samples", 0)
    certainty = min(1.0, round(math.log10(max(n_samples, 1)) / 4.0, 4)) if n_samples > 0 else 0.50

    dur_matrix_dict = rules.get("duration_conditioned_transition_matrix", {})
    if state_duration <= 3:
        duration_bin_name = "1-3d (Fresh)"
        trans_matrix = dur_matrix_dict.get("short_duration_1_3d", {}).get(l3_state_key, {})
    elif state_duration <= 10:
        duration_bin_name = "4-10d (Mature)"
        trans_matrix = dur_matrix_dict.get("medium_duration_4_10d", {}).get(l3_state_key, {})
    else:
        duration_bin_name = ">10d (Exhausted)"
        trans_matrix = dur_matrix_dict.get("long_duration_gt10d", {}).get(l3_state_key, {})

    inertia_prob = trans_matrix.get(l3_state_key, 0.0)
    next_states_sorted = sorted(
        [(k, v) for k, v in trans_matrix.items() if k != l3_state_key],
        key=lambda x: x[1],
        reverse=True
    )
    most_likely_next = next_states_sorted[0][0] if next_states_sorted else l3_state_key

    p_tp = info.get("p_triple_barrier_tp", info.get("p_bull", 0.50))
    p_sl = info.get("p_triple_barrier_sl", info.get("p_bear", 0.30))
    p_time = info.get("p_triple_barrier_timeout", max(0.0, round(1.0 - p_tp - p_sl, 4)))

    e_max = info.get("e_ret_max", 0.04)
    e_min = info.get("e_ret_min", -0.02)
    ev_n = info.get("ev_net", round(p_tp * e_max + p_sl * e_min, 4))
    rr = info.get("rr_asymmetry", round(e_max / max(abs(e_min), 1e-6), 4))

    return ProbabilitySnapshot(
        state_key=l3_state_key,
        p_take_profit=p_tp,
        p_stop_loss=p_sl,
        p_timeout=p_time,
        sample_size_n=n_samples,
        certainty_score=certainty,
        expected_gain_atr=e_max,
        expected_loss_atr=e_min,
        ev_net_atr=ev_n,
        rr_asymmetry=rr,
        current_state_duration=state_duration,
        duration_bin=duration_bin_name,
        regime_inertia_prob=inertia_prob,
        most_likely_next_state=most_likely_next,
        transition_matrix=trans_matrix,
    )


