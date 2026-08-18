#!/usr/bin/env python3
"""
Generate Cascade Calibration JSON — Empirical Z-Score Parameters & Asymmetric Tercile Edges
==========================================================================================
Measures the real empirical distributions over SPY pivots:
  - d1_bear_5 (mean, std)
  - domino_zz25 (mean, std)
  - domino_zz50 (mean, std)
  - tercile_edges [P33.33, P66.67] of cascade_conviction_50
Saves to backend/modules/entry_decision/domain/rules/cascade_calibration.json
"""
import sys
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter
from backend.modules.entry_decision.domain.rules.vvix_lookup import VVIXLookupAdapter
from backend.modules.entry_decision.domain.rules.pcr_lookup import PCRLookupAdapter
from backend.modules.entry_decision.domain.rules.fg_lookup import FGLookupAdapter
from backend.modules.entry_decision.domain.rules.sv5_turbulence_lookup import SV5TurbulenceLookupAdapter
from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter
from backend.modules.entry_decision.domain.rules.credit_lookup import CreditLookupAdapter
from backend.modules.entry_decision.domain.rules.yield_curve_lookup import YieldCurveLookupAdapter
from backend.modules.entry_decision.domain.rules.rotation_lookup import RotationLookupAdapter
from backend.modules.entry_decision.domain.rules.bsi_lookup import BSILookupAdapter
from backend.modules.entry_decision.domain.rules.dxy_lookup import DXYLookupAdapter

from backend.modules.entry_decision.domain.services.convergence_compositor import d1_directional_vote

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GenerateCascadeCalibration")

STATION_CONFIG = {
    "vix":            {"ticker": "VIX",            "adapter_cls": VIXLookupAdapter,            "method": "lookup_vix_guidance"},
    "vvix":           {"ticker": "VVIX",           "adapter_cls": VVIXLookupAdapter,           "method": "lookup_vvix_guidance"},
    "pcr":            {"ticker": "CBOE_PCR",       "adapter_cls": PCRLookupAdapter,            "method": "lookup_pcr_guidance"},
    "fg":             {"ticker": "FG",             "adapter_cls": FGLookupAdapter,             "method": "lookup_fg_guidance"},
    "sv5_turbulence": {"ticker": "SV5_TURBULENCE", "adapter_cls": SV5TurbulenceLookupAdapter, "method": "lookup_sv5_turbulence_guidance"},
    "skew":           {"ticker": "SKEW",           "adapter_cls": SkewLookupAdapter,           "method": "lookup_skew_guidance"},
    "credit":         {"ticker": "CREDIT_RATIO",   "adapter_cls": CreditLookupAdapter,         "method": "lookup_credit_guidance"},
    "yield_curve":    {"ticker": "YIELD_SPREAD",   "adapter_cls": YieldCurveLookupAdapter,     "method": "lookup_yield_curve_guidance"},
    "rotation":       {"ticker": "ROTATION_INDEX", "adapter_cls": RotationLookupAdapter,       "method": "lookup_rotation_guidance"},
    "bsi":            {"ticker": "S5TW",           "adapter_cls": BSILookupAdapter,            "method": "lookup_bsi_guidance"},
    "dxy":            {"ticker": "DXY",            "adapter_cls": DXYLookupAdapter,            "method": "lookup_dxy_guidance"},
}

GRUPO_A_PREDICTORS = {"vix", "bsi", "fg", "credit", "rotation"}


def main():
    logger.info("═" * 80)
    logger.info("GENERATING CASCADE CALIBRATION (EMPIRICAL DISTRIBUTIONS)")
    logger.info("═" * 80)

    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    legs25 = repo.get_confirmed_legs("SPY", "zz25")
    legs50 = repo.get_confirmed_legs("SPY", "zz50")

    df25 = pd.DataFrame([
        {"start_timestamp": l.start_timestamp, "prev_leg_return": l.prev_leg_return} for l in legs25
    ]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)
    df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
    df25["abs_prev_leg_return"] = df25["prev_leg_return"].abs()

    df50 = pd.DataFrame([
        {"start_timestamp": l.start_timestamp, "prev_leg_return": l.prev_leg_return} for l in legs50
    ]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)
    df50["abs_prev_leg_return"] = df50["prev_leg_return"].abs()

    # Load indicators
    logger.info("📊 Loading indicator time series...")
    indicator_series = {}
    for code, cfg in STATION_CONFIG.items():
        df_ind = store.load_bars(cfg["ticker"], "1d")
        if df_ind is not None and not df_ind.empty:
            s = df_ind["close"].copy()
            s.index = [d.date() if hasattr(d, 'date') else d for d in pd.to_datetime(s.index)]
            indicator_series[code] = s

    all_dates = set()
    for s in indicator_series.values():
        all_dates.update(s.index)
    date_features = pd.DataFrame(index=sorted(all_dates))
    for code, s in indicator_series.items():
        vel = s.diff(3)
        std_2, std_10 = s.rolling(2).std(), s.rolling(10).std()
        vol = (std_2 / std_10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        date_features[f"{code}_val"] = s
        date_features[f"{code}_vel"] = vel
        date_features[f"{code}_vol"] = vol

    adapters = {code: cfg["adapter_cls"]() for code, cfg in STATION_CONFIG.items()}

    records = []
    for idx, row in df25.iterrows():
        pd_ = row["pivot_date"]
        if pd_ not in date_features.index:
            continue
        feats = date_features.loc[pd_]

        votes = {}
        for code, adapter in adapters.items():
            val = feats.get(f"{code}_val")
            vel = feats.get(f"{code}_vel", 0.0)
            vol = feats.get(f"{code}_vol", 1.0)
            if pd.isna(val): continue
            if pd.isna(vel): vel = 0.0
            if pd.isna(vol): vol = 1.0

            try:
                method_name = STATION_CONFIG[code]["method"]
                lookup_fn = getattr(adapter, method_name)
                res = lookup_fn(val=float(val), d3_speed=float(vel), vol_norm=float(vol), vol_d3=float(vol))
                if res and res.state_key:
                    votes[code] = d1_directional_vote(res.state_key)
            except Exception:
                continue

        a_votes = [v for c, v in votes.items() if c in GRUPO_A_PREDICTORS]
        if not a_votes: continue
        a_bear = sum(1 for v in a_votes if v < 0)

        records.append({
            "pivot_date": pd_,
            "abs_prev_leg_return": row["abs_prev_leg_return"],
            "d1_bear_5": a_bear / len(a_votes),
        })

    df_obs = pd.DataFrame(records)
    logger.info(f"  ✅ {len(df_obs)} valid ZZ25 pivots with full votes")

    d1_bear_mean = float(df_obs["d1_bear_5"].mean())
    d1_bear_std = float(df_obs["d1_bear_5"].std())

    dom25_mean = float(df25["abs_prev_leg_return"].mean())
    dom25_std = float(df25["abs_prev_leg_return"].std())

    dom50_mean = float(df50["abs_prev_leg_return"].mean())
    dom50_std = float(df50["abs_prev_leg_return"].std())

    # Compute raw cascade_conviction_50 score for tercile edges
    z_b5 = (df_obs["d1_bear_5"] - d1_bear_mean) / d1_bear_std
    z_dom25 = (df_obs["abs_prev_leg_return"] - dom25_mean) / dom25_std
    scores_50 = 0.66 * z_b5 + 0.34 * z_dom25

    edges = np.quantile(scores_50, [0.3333, 0.6667])
    tercile_edges = [round(float(edges[0]), 3), round(float(edges[1]), 3)]

    calibration = {
        "_documentation": {
            "model_purpose": "Cascade Conviction Z-Score Calibration & Asymmetric Tercile Edges",
            "sample_size_pivots": len(df_obs),
            "updated_at": pd.Timestamp.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "type_mask": {
            "MIN": {
                "w_bear": 0.66,
                "w_dom": 0.34,
                "w_bear_c75": 0.50,
                "w_dom_c75": 0.50,
                "w_bear_50to75": 0.15,
                "w_dom_50to75": 0.85,
                "stations": ["vix", "bsi", "fg", "credit", "rotation"]
            },
            "MAX": {
                "w_bear": 0.66,
                "w_dom": 0.34,
                "w_bear_c75": 0.50,
                "w_dom_c75": 0.50,
                "w_bear_50to75": 0.15,
                "w_dom_50to75": 0.85,
                "stations": ["vix", "bsi", "credit", "rotation"]
            }
        },
        "d1_bear_5": {
            "mean": round(d1_bear_mean, 4),
            "std": round(d1_bear_std, 4),
        },
        "domino_zz25": {
            "mean": round(dom25_mean, 4),
            "std": round(dom25_std, 4),
        },
        "domino_zz50": {
            "mean": round(dom50_mean, 4),
            "std": round(dom50_std, 4),
        },
        "tercile_edges": tercile_edges,
        "baseline_ic_in_sample": {
            "cascade_50": 0.4155,
            "cascade_75": 0.3463,
            "cascade_50to75": 0.4113,
        },
        "baseline_ic_oos": {
            "cascade_50": 0.3245,
            "cascade_75": 0.2596,
            "cascade_50to75": 0.3388,
        },
        "decay_threshold": 0.10,
        "last_checked": None,
    }

    logger.info("\n📊 REAL EMPIRICAL MEASUREMENTS:")
    logger.info(f"  d1_bear_5:    mean = {calibration['d1_bear_5']['mean']:.4f}, std = {calibration['d1_bear_5']['std']:.4f}")
    logger.info(f"  domino_zz25:  mean = {calibration['domino_zz25']['mean']:.4f}, std = {calibration['domino_zz25']['std']:.4f}")
    logger.info(f"  domino_zz50:  mean = {calibration['domino_zz50']['mean']:.4f}, std = {calibration['domino_zz50']['std']:.4f}")
    logger.info(f"  tercile_edges: [t1/t2 = {tercile_edges[0]}, t2/t3 = {tercile_edges[1]}]")

    output_path = root_dir / "backend" / "modules" / "entry_decision" / "domain" / "rules" / "cascade_calibration.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(calibration, f, indent=2)

    logger.info(f"\n💾 Saved calibration to {output_path}")


if __name__ == "__main__":
    main()
