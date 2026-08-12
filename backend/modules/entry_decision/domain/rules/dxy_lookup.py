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
        }


class DXYLookupAdapter:
    def __init__(self, fact_store_path: Path = FACT_STORE_PATH):
        self._path = fact_store_path
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self):
        if not self._path.exists():
            raise FileNotFoundError(f"DXY Fact Store not found at {self._path}")
        with open(self._path, "r", encoding="utf-8") as f:
            raw = json.load(f)
            self._data = raw.get("states", {})
            doc = raw.get("_documentation", {})
        self.edges_d1 = doc.get("dimension_thresholds_definition", {}).get("d1_edges_gauss_sigma", [76.1231, 84.2773, 95.9630, 108.5600, 135.5228])
        self.edges_d2 = doc.get("dimension_thresholds_definition", {}).get("d2_edges_gauss_sigma", [-1.8200, -0.7200, 0.7300, 1.8000])
        self.edges_d3 = doc.get("dimension_thresholds_definition", {}).get("d3_vol_edges_gauss_sigma", [0.0114, 0.1024, 0.8888, 1.6066])

    def lookup_dxy_guidance(
        self,
        val: float,
        d3_speed: float,
        vol_norm: float = 1.0,
        vol_d3: float = 0.0,
    ) -> Optional[DXYStateGuidance]:

        # D1 Edges (Gaussian canonical)
        if val < self.edges_d1[0]:
            d1_bin = "DEEP_DOLLAR_CRUSH"
        elif val < self.edges_d1[1]:
            d1_bin = "WEAK_DOLLAR"
        elif val < self.edges_d1[2]:
            d1_bin = "MODERATE_LOW_DOLLAR"
        elif val < self.edges_d1[3]:
            d1_bin = "MODERATE_HIGH_DOLLAR"
        elif val < self.edges_d1[4]:
            d1_bin = "ELEVATED_DOLLAR_STRESS"
        else:
            d1_bin = "DOLLAR_SPIKE_CRISIS"

        # D2 Edges (Delta 3d)
        if d3_speed < self.edges_d2[0]:
            d2_bin = "FAST_CRUSH_3D"
        elif d3_speed < self.edges_d2[1]:
            d2_bin = "DECELERATING_DOWN_3D"
        elif d3_speed < self.edges_d2[2]:
            d2_bin = "STABLE_CONTINUATION_3D"
        elif d3_speed < self.edges_d2[3]:
            d2_bin = "ACCELERATING_UP_3D"
        else:
            d2_bin = "FAST_SPIKE_3D"

        # D3 Edges (Vol Ratio)
        if vol_norm < self.edges_d3[0]:
            d3_bin = "VOL_EXTREME_SQUEEZE"
        elif vol_norm < self.edges_d3[1]:
            d3_bin = "VOL_MODERATE_COMPRESSION"
        elif vol_norm < self.edges_d3[2]:
            d3_bin = "VOL_NEUTRAL_BASELINE"
        elif vol_norm < self.edges_d3[3]:
            d3_bin = "VOL_ACCELERATING_EXPANSION"
        else:
            d3_bin = "VOL_PEAK_DECELERATION"

        state_key = f"{d1_bin}__{d2_bin}__{d3_bin}"
        state_data = self._data.get(state_key)

        if not state_data:
            # Fallback to matches starting with d1_bin
            matches = [k for k in self._data.keys() if k.startswith(d1_bin) and "__" in k]
            if matches:
                state_key = matches[0]
                state_data = self._data[state_key]
            else:
                # Fallback to any valid state key
                all_states = [k for k in self._data.keys() if "__" in k]
                if all_states:
                    state_key = all_states[0]
                    state_data = self._data[state_key]
                else:
                    return None

        n_samples = int(state_data.get("n", 0))
        stats = state_data.get("stats", {})
        mean_v = float(stats.get("mean", val))
        std_v = float(stats.get("std", 0.0))

        z25_raw = state_data.get("zz25", {})
        z50_raw = state_data.get("zz50", {})
        z75_raw = state_data.get("zz75", {})

        zz25 = ScaleGuidance(
            p_bull=float(z25_raw.get("p_bull", 0.5)),
            p_bear=float(z25_raw.get("p_bear", 0.5)),
            e_ret_max=float(z25_raw.get("e_ret_max", 0.015)),
            e_ret_min=float(z25_raw.get("e_ret_min", -0.015)),
            ev_net=float(z25_raw.get("ev_net", 0.0)),
            e_days=float(z25_raw.get("e_days", 1.0)),
            ev_per_day=float(z25_raw.get("ev_per_day", 0.0)),
            rr_asymmetry=float(z25_raw.get("rr_asymmetry", 1.0)),
        )

        zz50 = ScaleGuidance(
            p_bull=float(z50_raw.get("p_bull", 0.5)),
            p_bear=float(z50_raw.get("p_bear", 0.5)),
            e_ret_max=float(z50_raw.get("e_ret_max", 0.015)),
            e_ret_min=float(z50_raw.get("e_ret_min", -0.015)),
            ev_net=float(z50_raw.get("ev_net", 0.0)),
            e_days=float(z50_raw.get("e_days", 3.0)),
            ev_per_day=float(z50_raw.get("ev_per_day", 0.0)),
            rr_asymmetry=float(z50_raw.get("rr_asymmetry", 1.0)),
        )

        zz75 = ScaleGuidance(
            p_bull=float(z75_raw.get("p_bull", 0.5)),
            p_bear=float(z75_raw.get("p_bear", 0.5)),
            e_ret_max=float(z75_raw.get("e_ret_max", 0.015)),
            e_ret_min=float(z75_raw.get("e_ret_min", -0.015)),
            ev_net=float(z75_raw.get("ev_net", 0.0)),
            e_days=float(z75_raw.get("e_days", 5.0)),
            ev_per_day=float(z75_raw.get("ev_per_day", 0.0)),
            rr_asymmetry=float(z75_raw.get("rr_asymmetry", 1.0)),
        )

        return DXYStateGuidance(
            state_key=state_key,
            dxy_bin=d1_bin,
            velocity_vector=d2_bin,
            pivot_vector=d3_bin,
            n=n_samples,
            mean_val=mean_v,
            std_val=std_v,
            divergence_regime=state_data.get("divergence_regime", "GOLDILOCKS_CURRENCY_BALANCED"),
            operational_guidance=state_data.get("operational_guidance", "STK_HOLD_STABLE"),
            zz25=zz25,
            zz50=zz50,
            zz75=zz75,
        )


dxy_lookup = DXYLookupAdapter()
