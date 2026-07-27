"""
RC Real EV Unified Lookup — Pure Domain Rule
=====================================================
Loads rc_ev_unified_tree.json (4.57M samples, 712 tickers, 1993-2026)
and provides hierarchical point-in-time Real EV lookup (S1 -> S3 -> S0).

Clean Architecture: Pure domain rule. Loads JSON once, no IO after init.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from backend.modules.quality_swing.domain.rules.rc_slope_classifier import (
    _classify_one,
)

logger = logging.getLogger(__name__)

_TREE: Optional[dict] = None
_TREE_PATH = Path(__file__).parent / "rc_ev_unified_tree.json"


@dataclass(frozen=True)
class RealEVUnifiedSignal:
    p_bull: float
    p_bear: float
    ev: float
    sharpe: float
    e_ret_max: float
    e_ret_min: float
    rr_asymmetry: float
    n_samples: int
    fallback_level: str
    lookup_key: str


def _load_tree() -> dict:
    global _TREE
    if _TREE is None:
        if not _TREE_PATH.exists():
            logger.warning(f"Árbol estocástico no encontrado en {_TREE_PATH}")
            return {}
        with open(_TREE_PATH, "r") as f:
            _TREE = json.load(f)
    return _TREE


def lookup_unified_real_ev(
    tide_slope: Union[float, str],
    current_slope: Union[float, str],
    wave_slope: Union[float, str],
    sigma_current: Union[float, str] = 0.0,
    sigma_wave: Union[float, str] = 0.0,
    vwap_sigma_wave: Union[float, str] = 0.0,
    min_n: int = 10,
    atr_pct: float = 0.01,
) -> Optional[RealEVUnifiedSignal]:
    """Query hierarchical Real EV unified tree (S1 -> S3 -> S0)."""
    tree = _load_tree()
    if not tree:
        return None

    # Convert floats to string labels
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

    # S1 Full 6D
    s1_key = f"{t_lbl}|{c_lbl}|{w_lbl}|{sc_lbl}|{sw_lbl}|{svw_lbl}"
    s1_data = tree.get("s1_full", {}).get(s1_key)
    if s1_data and s1_data.get("n", 0) >= min_n:
        return RealEVUnifiedSignal(
            p_bull=s1_data["p_bull"],
            p_bear=s1_data["p_bear"],
            ev=s1_data["ev"],
            sharpe=s1_data["sharpe"],
            e_ret_max=s1_data["e_ret_max"],
            e_ret_min=s1_data["e_ret_min"],
            rr_asymmetry=s1_data["rr_asymmetry"],
            n_samples=s1_data["n"],
            fallback_level="S1_full",
            lookup_key=s1_key,
        )

    # S3 Triad 3D
    s3_key = f"{t_lbl}|{c_lbl}|{w_lbl}"
    s3_data = tree.get("s3_triad", {}).get(s3_key)
    if s3_data and s3_data.get("n", 0) >= min_n:
        return RealEVUnifiedSignal(
            p_bull=s3_data["p_bull"],
            p_bear=s3_data["p_bear"],
            ev=s3_data["ev"],
            sharpe=s3_data["sharpe"],
            e_ret_max=s3_data["e_ret_max"],
            e_ret_min=s3_data["e_ret_min"],
            rr_asymmetry=s3_data["rr_asymmetry"],
            n_samples=s3_data["n"],
            fallback_level="S3_triad",
            lookup_key=s3_key,
        )

    # S0 Global
    s0_data = tree.get("s0_global", {})
    if s0_data:
        return RealEVUnifiedSignal(
            p_bull=s0_data["p_bull"],
            p_bear=s0_data["p_bear"],
            ev=s0_data["ev"],
            sharpe=s0_data["sharpe"],
            e_ret_max=s0_data["e_ret_max"],
            e_ret_min=s0_data["e_ret_min"],
            rr_asymmetry=s0_data["rr_asymmetry"],
            n_samples=s0_data["n"],
            fallback_level="S0_global",
            lookup_key="GLOBAL",
        )

    return None
