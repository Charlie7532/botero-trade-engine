import os
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional

FACT_STORE_PATH = Path(__file__).parent / "dxy_fact_store.json"


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
    confidence_tier: str = "MODERATE"


@dataclass(frozen=True)
class DXYStateGuidance:
    state_key: str
    dxy_bin: str
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

    @property
    def bin(self) -> str:
        return self.dxy_bin

    def to_vector(self) -> Dict[str, Any]:
        return {
            "state_key": self.state_key,
            "bin": self.dxy_bin,
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
        }


class DXYLookupAdapter:
    """
    Lookup adapter for 11th METAR station: DXY (US Dollar Index).
    Reads harmonized V3 fact store with dual-layer architecture:
      - Standard layer: zz25, zz50, zz75 (fwd 1d/3d/5d returns with Bayesian Shrinkage m=10)
      - Kinematic layer: physical ZigZag legs + structural_momentum
    """

    def __init__(self):
        with open(FACT_STORE_PATH, "r", encoding="utf-8") as f:
            self._data = json.load(f)

        doc = self._data.get("_documentation", {})
        thresh = doc.get("dimension_thresholds_definition", {})

        # Default Gaussian sigma edges for DXY (Standardized station_labels_d1 schema)
        self.edges_d1 = thresh.get("dxy_edges_d1", thresh.get("d1_edges_full_population", [76.1231, 84.2773, 95.963, 108.56, 135.5228]))
        self.edges_d2 = thresh.get("dxy_edges_d2", thresh.get("d2_edges_gauss_sigma", [-1.82, -0.72, 0.73, 1.80]))
        self.edges_d3 = thresh.get("dxy_edges_d3", thresh.get("d3_vol_edges_gauss_sigma", [0.0114, 0.1024, 0.8888, 1.6066]))

        self.labels_d1 = thresh.get("dxy_labels_d1", thresh.get("d1_labels", [
            "DEEP_DOLLAR_CRUSH", "WEAK_DOLLAR", "MODERATE_LOW_DOLLAR",
            "MODERATE_HIGH_DOLLAR", "ELEVATED_DOLLAR_STRESS", "DOLLAR_SPIKE_CRISIS"
        ]))
        self.labels_d2 = thresh.get("dxy_labels_d2", thresh.get("d2_labels", [
            "FAST_CRUSH_3D", "DECELERATING_DOWN_3D", "STABLE_CONTINUATION_3D",
            "ACCELERATING_UP_3D", "FAST_SPIKE_3D"
        ]))
        self.labels_d3 = thresh.get("dxy_labels_d3", thresh.get("d3_labels", [
            "VOL_EXTREME_SQUEEZE", "VOL_MODERATE_COMPRESSION", "VOL_NEUTRAL_BASELINE",
            "VOL_ACCELERATING_EXPANSION", "VOL_PEAK_DECELERATION"
        ]))
        self.states = self._data.get("states", {})

    def _classify_d1(self, v: float) -> str:
        for idx, e in enumerate(self.edges_d1):
            if v < e:
                return self.labels_d1[idx]
        return self.labels_d1[-1]

    def _classify_d2(self, v: float) -> str:
        for idx, e in enumerate(self.edges_d2):
            if v < e:
                return self.labels_d2[idx]
        return self.labels_d2[-1]

    def _classify_d3(self, vol_norm: float) -> str:
        for idx, e in enumerate(self.edges_d3):
            if vol_norm < e:
                return self.labels_d3[idx]
        return self.labels_d3[-1]

    def lookup_dxy_guidance(
        self,
        val: Optional[float] = None,
        d3_speed: float = 0.0,
        vol_norm: float = 1.0,
        **kwargs
    ) -> Optional[DXYStateGuidance]:
        if val is None:
            for alt_k in ["dxy_val", "val", "dxy_index", "usd_val"]:
                if alt_k in kwargs and kwargs[alt_k] is not None:
                    val = kwargs[alt_k]
                    break
        if d3_speed == 0.0:
            for alt_s in ["dxy_d3", "diff3", "d2_speed"]:
                if alt_s in kwargs and kwargs[alt_s] is not None:
                    d3_speed = kwargs[alt_s]
                    break

        if val is None:
            val = 95.0  # Default neutral DXY

        cat_d1 = self._classify_d1(val)
        cat_d2 = self._classify_d2(d3_speed)
        cat_d3 = self._classify_d3(vol_norm)

        target_key = f"{cat_d1}__{cat_d2}__{cat_d3}"
        matched_key = target_key if target_key in self.states else None
        state = self.states.get(target_key)

        # Fallbacks for unpopulated states
        if not state:
            matched_key = f"{cat_d1}__{cat_d2}__VOL_NEUTRAL_BASELINE"
            state = self.states.get(matched_key)
        if not state:
            matching = [k for k in self.states.keys() if k.startswith(f"{cat_d1}__{cat_d2}")]
            if matching:
                matched_key = matching[0]
                state = self.states.get(matched_key)
        if not state:
            matching = [k for k in self.states.keys() if k.startswith(f"{cat_d1}")]
            if matching:
                matched_key = matching[0]
                state = self.states.get(matched_key)

        if not state:
            return None

        def _make_scale(d: dict) -> ScaleGuidance:
            return ScaleGuidance(
                p_bull=d.get("p_bull", 0.5),
                p_bear=d.get("p_bear", 0.5),
                e_ret_max=d.get("e_ret_max", 0.0),
                e_ret_min=d.get("e_ret_min", 0.0),
                ev_net=d.get("ev_net", 0.0),
                e_days=d.get("e_days", 1.0),
                ev_per_day=d.get("ev_per_day", 0.0),
                rr_asymmetry=d.get("rr_asymmetry", 1.0),
                confidence_tier=d.get("confidence_tier", "MODERATE"),
            )

        stats = state.get("stats", {})
        return DXYStateGuidance(
            state_key=matched_key,
            dxy_bin=cat_d1,
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
        )


dxy_lookup = DXYLookupAdapter()
