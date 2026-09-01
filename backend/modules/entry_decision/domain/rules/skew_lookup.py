import os
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional

from backend.modules.entry_decision.domain.rules.sigma_overflow import validate_overflow
from backend.modules.entry_decision.domain.rules.metar_classifier import classify_bin, make_state_key, resolve_label

FACT_STORE_PATH = Path(__file__).parent / "skew_fact_store.json"


@dataclass(frozen=True)
class ScaleGuidance:
    p_bull: float
    p_bear: float
    e_ret_max: float
    e_ret_min: float
    ev_net: float
    e_days: float
    ev_per_day: float
    rr_asymmetry: float


@dataclass(frozen=True)
class SkewStateGuidance:
    state_key: str
    skew_bin: str
    velocity_vector: str
    pivot_vector: str
    n: int
    mean_val: float
    std_val: float
    divergence_regime: str
    operational_guidance: str
    zz25: ScaleGuidance
    zz50: ScaleGuidance
    zz75: ScaleGuidance
    zigzag_kinematic: Optional[Dict[str, Any]] = None
    sigma_depth_d1: Optional[float] = None
    sigma_depth_d2: Optional[float] = None
    sigma_depth_d3: Optional[float] = None
    overflow_flag: Optional[str] = None  # "UPPER"|"LOWER"|"MULTI"|None

    @property
    def bin(self) -> str:
        return self.skew_bin

    @property
    def sv5_bin(self) -> str:
        return self.skew_bin

    def to_vector(self) -> Dict[str, Any]:
        return {
            "state_key": self.state_key,
            "bin": self.skew_bin,
            "velocity_vector": self.velocity_vector,
            "pivot_vector": self.pivot_vector,
            "n": self.n,
            "mean_val": self.mean_val,
            "std_val": self.std_val,
            "divergence_regime": self.divergence_regime,
            "operational_guidance": self.operational_guidance,
            "zz25": self.zz25.__dict__,
            "zz50": self.zz50.__dict__,
            "zz75": self.zz75.__dict__,
            "p_bull": {"zz25": self.zz25.p_bull, "zz50": self.zz50.p_bull, "zz75": self.zz75.p_bull},
            "p_bear": {"zz25": self.zz25.p_bear, "zz50": self.zz50.p_bear, "zz75": self.zz75.p_bear},
            "ev_net": {"zz25": self.zz25.ev_net, "zz50": self.zz50.ev_net, "zz75": self.zz75.ev_net},
            "e_days": {"zz25": self.zz25.e_days, "zz50": self.zz50.e_days, "zz75": self.zz75.e_days},
            "ev_per_day": {"zz25": self.zz25.ev_per_day, "zz50": self.zz50.ev_per_day, "zz75": self.zz75.ev_per_day},
            "primary_p_bull": self.zz50.p_bull,
            "primary_ev_net": self.zz50.ev_net,
            "primary_e_days": self.zz50.e_days,
            "primary_capital_velocity": self.zz50.ev_per_day,
            "zigzag_kinematic": self.zigzag_kinematic,
            "sigma_depth_d1": self.sigma_depth_d1,
            "sigma_depth_d2": self.sigma_depth_d2,
            "sigma_depth_d3": self.sigma_depth_d3,
            "overflow_flag": self.overflow_flag,
        }


class SkewLookupAdapter:
    def __init__(self):
        with open(FACT_STORE_PATH, "r", encoding="utf-8") as f:
            self._data = json.load(f)

        doc = self._data.get("_documentation", {})
        self.edges_d1 = doc.get("dimension_thresholds_definition", {}).get("skew_edges_d1", [114.67, 119.99, 130.28, 144.48, 159.31])
        self.edges_d2 = doc.get("dimension_thresholds_definition", {}).get("skew_edges_d2", [-11.62, -4.56, 4.57, 11.36])
        self.edges_d3 = doc.get("dimension_thresholds_definition", {}).get("skew_edges_d3", [0.0169, 0.1233, 1.0492, 1.8934])
        self.labels_d1 = doc.get("dimension_thresholds_definition", {}).get("skew_labels_d1", ['EXTREME_CONFIDENCE', 'CONFIDENCE', 'NEUTRAL_CONFIDENT', 'NEUTRAL_PARANOID', 'PARANOIA', 'EXTREME_PARANOIA'])
        self.labels_d2 = doc.get("dimension_thresholds_definition", {}).get("skew_labels_d2", ['FAST_CRUSH_3D', 'DECELERATING_DOWN_3D', 'STABLE_CONTINUATION_3D', 'ACCELERATING_UP_3D', 'FAST_SPIKE_3D'])
        self.labels_d3 = doc.get("dimension_thresholds_definition", {}).get("skew_labels_d3", ['VOL_EXTREME_SQUEEZE', 'VOL_MODERATE_COMPRESSION', 'VOL_NEUTRAL_BASELINE', 'VOL_ACCELERATING_EXPANSION', 'VOL_PEAK_DECELERATION'])
        self.states = self._data.get("states", {})

    def _classify_d1(self, v: float) -> str:
        return resolve_label(classify_bin(v, self.edges_d1), self.labels_d1)

    def _classify_d2(self, v: float) -> str:
        return resolve_label(classify_bin(v, self.edges_d2), self.labels_d2)

    def _classify_d3(self, vol_norm: float, vol_d3: float = 0.0) -> str:
        return resolve_label(classify_bin(vol_norm, self.edges_d3), self.labels_d3)
    def lookup_skew_guidance(
        self,
        val: float = None,
        d3_speed: float = 0.0,
        vol_norm: float = 1.0,
        vol_d3: float = 0.0,
        **kwargs
    ) -> Optional[SkewStateGuidance]:
        if val is None:
            for alt_k in ["fg_val", "vix_val", "pcr_val", "skew_val", "vvix_val", "hyg_val", "credit_ratio", "rot_val", "rotation_val", "turbulence_val", "spread_value"]:
                if alt_k in kwargs and kwargs[alt_k] is not None:
                    val = kwargs[alt_k]
                    break
        if d3_speed == 0.0:
            for alt_s in ["fg_d3", "vix_d3", "pcr_d3", "skew_d3", "vvix_d3", "credit_d3", "rot_d3", "rotation_d3", "turbulence_d3", "spread_d3"]:
                if alt_s in kwargs and kwargs[alt_s] is not None:
                    d3_speed = kwargs[alt_s]
                    break

        if val is None:
            val = 0.0

        cat_d1 = self._classify_d1(val)
        cat_d2 = self._classify_d2(d3_speed)
        cat_d3 = self._classify_d3(vol_norm, vol_d3)
        bin_d1 = classify_bin(val, self.edges_d1)
        bin_d2 = classify_bin(d3_speed, self.edges_d2)
        bin_d3 = classify_bin(vol_norm, self.edges_d3)

        target_key = make_state_key(bin_d1, bin_d2, bin_d3)
        matched_key = target_key if target_key in self.states else None
        state = self.states.get(target_key)

        if not state:
            matched_key = make_state_key(bin_d1, bin_d2, 2)
            state = self.states.get(matched_key)
        if not state:
            matching = [k for k in self.states.keys() if k.startswith(f"{bin_d1}__{bin_d2}")]
            if matching:
                matched_key = matching[0]
                state = self.states.get(matched_key)
        if not state:
            matching = [k for k in self.states.keys() if k.startswith(f"{bin_d1}__")]
            if matching:
                matched_key = matching[0]
                state = self.states.get(matched_key)

        if not state:
            return None

        def _make_scale(d: dict) -> ScaleGuidance:
            return ScaleGuidance(
                p_bull=d["p_bull"], p_bear=d["p_bear"], e_ret_max=d["e_ret_max"],
                e_ret_min=d["e_ret_min"], ev_net=d["ev_net"], e_days=d["e_days"],
                ev_per_day=d["ev_per_day"], rr_asymmetry=d["rr_asymmetry"]
            )

        d1_depth, f1 = validate_overflow("skew", "d1", val)
        d2_depth, f2 = validate_overflow("skew", "d2", d3_speed)
        d3_depth, f3 = validate_overflow("skew", "d3", vol_norm)
        flags = [f for f in (f1, f2, f3) if f]
        overflow_flag = "MULTI" if len(flags) >= 2 else (flags[0] if flags else None)

        stats = state.get("stats", {})
        return SkewStateGuidance(
            state_key=matched_key,
            skew_bin=cat_d1,
            velocity_vector=cat_d2,
            pivot_vector=cat_d3,
            n=state.get("n", 0),
            mean_val=stats.get("mean", 0.0),
            std_val=stats.get("std", 0.0),
            divergence_regime=state.get("divergence_regime", "NEUTRAL"),
            operational_guidance=state.get("operational_guidance", "STK_HOLD_STABLE"),
            zz25=_make_scale(state["zz25"]),
            zz50=_make_scale(state["zz50"]),
            zz75=_make_scale(state["zz75"]),
            zigzag_kinematic=state.get("zigzag_kinematic"),
            sigma_depth_d1=d1_depth,
            sigma_depth_d2=d2_depth,
            sigma_depth_d3=d3_depth,
            overflow_flag=overflow_flag,
        )


skew_lookup = SkewLookupAdapter()
