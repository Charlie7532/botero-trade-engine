#!/usr/bin/env python3
"""
Decay Check — Cascade Conviction (Hypothesis-Governance System Directive)
==========================================================================
Periodically re-validates the IC of cascade_conviction against baseline ICs.
If degradation exceeds the allowed threshold (e.g. 10%), triggers an alert
and logs the event to backend/modules/entry_decision/domain/rules/decay_check_log.json.

Target Baselines:
  - cascade_50:     0.325
  - cascade_75:     0.260
  - cascade_50to75: 0.339
"""
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

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
logger = logging.getLogger("DecayCheckCascadeConviction")

RULES_DIR = root_dir / "backend" / "modules" / "entry_decision" / "domain" / "rules"
CALIBRATION_FILE = RULES_DIR / "cascade_calibration.json"
LOG_FILE = RULES_DIR / "decay_check_log.json"

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
    "bsi":            {"ticker": "S5FI",           "adapter_cls": BSILookupAdapter,            "method": "lookup_bsi_guidance"},
    "dxy":            {"ticker": "DXY",            "adapter_cls": DXYLookupAdapter,            "method": "lookup_dxy_guidance"},
}

GRUPO_A_PREDICTORS = {"vix", "bsi", "fg", "credit", "rotation"}


def compute_ic(score, target):
    valid = ~np.isnan(score) & ~np.isnan(target)
    s, t = score[valid], target[valid]
    if len(s) < 5 or np.std(s) == 0 or np.std(t) == 0:
        return 0.0
    ic, _ = spearmanr(s, t)
    return float(ic) if not np.isnan(ic) else 0.0


def main():
    logger.info("═" * 80)
    logger.info("AUTOMATIC DECAY CHECK — CASCADE CONVICTION")
    logger.info("═" * 80)

    # 1. Load Calibration
    if not CALIBRATION_FILE.exists():
        logger.error(f"❌ Calibration file not found at {CALIBRATION_FILE}. Run generate_cascade_calibration.py first.")
        sys.exit(1)

    with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
        calibration = json.load(f)

    baseline = calibration.get("baseline_ic_in_sample", calibration.get("baseline_ic", {"cascade_50": 0.4155, "cascade_75": 0.3463, "cascade_50to75": 0.4113}))
    decay_threshold = calibration.get("decay_threshold", 0.10)

    d1_mean = calibration.get("d1_bear_5", {}).get("mean", 0.3299)
    d1_std = calibration.get("d1_bear_5", {}).get("std", 0.2856)
    dom25_mean = calibration.get("domino_zz25", {}).get("mean", 0.0532)
    dom25_std = calibration.get("domino_zz25", {}).get("std", 0.0350)
    dom50_mean = calibration.get("domino_zz50", {}).get("mean", 0.1003)
    dom50_std = calibration.get("domino_zz50", {}).get("std", 0.0643)

    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)

    legs25 = repo.get_confirmed_legs("SPY", "zz25")
    legs50 = repo.get_confirmed_legs("SPY", "zz50")
    legs75 = repo.get_confirmed_legs("SPY", "zz75")

    starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)
    starts75 = set(pd.to_datetime(l.start_timestamp).date() for l in legs75)

    df25 = pd.DataFrame([
        {"start_timestamp": l.start_timestamp, "start_type": l.start_type, "prev_leg_return": l.prev_leg_return} for l in legs25
    ]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)
    df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
    df25["abs_prev_leg_return"] = df25["prev_leg_return"].abs()
    df25["cascade_50"] = df25["pivot_date"].apply(
        lambda d: int(any(d + timedelta(days=i) in starts50 for i in range(-3, 4)))
    )
    df25["cascade_75"] = df25["pivot_date"].apply(
        lambda d: int(any(d + timedelta(days=i) in starts75 for i in range(-3, 4)))
    )

    df50_legs = pd.DataFrame([
        {"start_timestamp": pd.to_datetime(l.start_timestamp), "prev_leg_return_zz50": l.prev_leg_return}
        for l in legs50
    ]).dropna().sort_values("start_timestamp").reset_index(drop=True)
    df50_legs["abs_prev_leg_return_zz50"] = df50_legs["prev_leg_return_zz50"].abs()

    df25_sorted = df25.sort_values("start_timestamp").copy()
    df25_sorted["ts"] = pd.to_datetime(df25_sorted["start_timestamp"])
    df50_sorted = df50_legs.sort_values("start_timestamp").copy()
    df50_sorted["ts"] = pd.to_datetime(df50_sorted["start_timestamp"])

    df25_merged = pd.merge_asof(
        df25_sorted,
        df50_sorted[["ts", "abs_prev_leg_return_zz50"]],
        on="ts",
        direction="backward"
    ).fillna({"abs_prev_leg_return_zz50": dom50_mean})

    df50 = pd.DataFrame([
        {"start_timestamp": l.start_timestamp, "start_type": l.start_type, "prev_leg_return": l.prev_leg_return} for l in legs50
    ]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)
    df50["pivot_date"] = pd.to_datetime(df50["start_timestamp"]).dt.date
    df50["abs_prev_leg_return"] = df50["prev_leg_return"].abs()
    df50["cascade_50to75"] = df50["pivot_date"].apply(
        lambda d: int(any(d + timedelta(days=i) in starts75 for i in range(-3, 4)))
    )

    # Load indicator series
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

    def build_obs_df(pivots_df):
        obs = []
        for idx, row in pivots_df.iterrows():
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

            p_type = row.get("start_type", "MIN")
            type_mask_cfg = calibration.get("type_mask", {}).get(p_type, {
                "w_bear": 0.66, "w_dom": 0.34,
                "w_bear_c75": 0.50, "w_dom_c75": 0.50,
                "stations": ["vix", "bsi", "fg", "credit", "rotation"] if p_type == "MIN" else ["vix", "bsi", "credit", "rotation"]
            })
            allowed = set(type_mask_cfg.get("stations", GRUPO_A_PREDICTORS))
            w_bear = float(type_mask_cfg.get("w_bear", 0.66))
            w_dom = float(type_mask_cfg.get("w_dom", 0.34))
            w_bear_c75 = float(type_mask_cfg.get("w_bear_c75", 0.50))
            w_dom_c75 = float(type_mask_cfg.get("w_dom_c75", 0.50))

            m_votes = [v for c, v in votes.items() if c in allowed]
            if not m_votes: continue
            m_bear = sum(1 for v in m_votes if v < 0)

            rec = {
                "pivot_date": pd_,
                "pivot_type": p_type,
                "abs_prev_leg_return": row["abs_prev_leg_return"],
                "abs_prev_leg_return_zz50": row.get("abs_prev_leg_return_zz50", dom50_mean),
                "d1_bear_5": m_bear / len(m_votes),
                "w_bear": w_bear,
                "w_dom": w_dom,
                "w_bear_c75": w_bear_c75,
                "w_dom_c75": w_dom_c75,
            }
            for col in ["cascade_50", "cascade_75", "cascade_50to75"]:
                if col in row:
                    rec[col] = row[col]
            obs.append(rec)
        return pd.DataFrame(obs)

    df_obs_25 = build_obs_df(df25_merged)
    df_obs_50 = build_obs_df(df50)

    # Compute scores using calibration z-score parameters
    z_b5_25 = (df_obs_25["d1_bear_5"] - d1_mean) / d1_std
    z_dom25 = (df_obs_25["abs_prev_leg_return"] - dom25_mean) / dom25_std
    z_dom50_25 = (df_obs_25["abs_prev_leg_return_zz50"] - dom50_mean) / dom50_std

    c50_scores = df_obs_25["w_bear"] * z_b5_25 + df_obs_25["w_dom"] * z_dom25
    c75_scores = df_obs_25["w_bear_c75"] * z_b5_25 + df_obs_25["w_dom_c75"] * z_dom50_25

    z_b5_50 = (df_obs_50["d1_bear_5"] - d1_mean) / d1_std
    z_dom50 = (df_obs_50["abs_prev_leg_return"] - dom50_mean) / dom50_std
    c50to75_scores = 0.15 * z_b5_50 + 0.85 * z_dom50

    # Current IC measurements
    current_c50_ic = compute_ic(c50_scores, df_obs_25["cascade_50"].values)
    current_c75_ic = compute_ic(c75_scores, df_obs_25["cascade_75"].values)
    current_c50to75_ic = compute_ic(c50to75_scores, df_obs_50["cascade_50to75"].values)

    # Baseline comparison (In-Sample Baseline)
    b50 = baseline.get("cascade_50", 0.4155)
    b75 = baseline.get("cascade_75", 0.3465)
    b50to75 = baseline.get("cascade_50to75", 0.4113)

    deg_c50 = (b50 - current_c50_ic) / b50 if b50 > 0 else 0.0
    deg_c75 = (b75 - current_c75_ic) / b75 if b75 > 0 else 0.0
    deg_c50to75 = (b50to75 - current_c50to75_ic) / b50to75 if b50to75 > 0 else 0.0

    max_degradation = max(deg_c50, deg_c75, deg_c50to75)
    alert = bool(max_degradation > decay_threshold)

    logger.info("\n📊 CURRENT IN-SAMPLE IC vs IN-SAMPLE BASELINE:")
    logger.info(f"  cascade_50:     Current IC = {current_c50_ic:+.4f} | Baseline = {b50:+.4f} | Degradation = {deg_c50:+.2%}")
    logger.info(f"  cascade_75:     Current IC = {current_c75_ic:+.4f} | Baseline = {b75:+.4f} | Degradation = {deg_c75:+.2%}")
    logger.info(f"  cascade_50to75: Current IC = {current_c50to75_ic:+.4f} | Baseline = {b50to75:+.4f} | Degradation = {deg_c50to75:+.2%}")
    logger.info(f"  Max Degradation: {max_degradation:+.2%} (Threshold = {decay_threshold:.0%})")
    logger.info(f"  Status: {'🚨 DECAY ALERT TRIGGERED' if alert else '✅ SIGNAL HEALTHY (NO DECAY)'}")

    # Append to log
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_entry = {
        "date": now_str,
        "c50_ic": round(current_c50_ic, 4),
        "c75_ic": round(current_c75_ic, 4),
        "c50to75_ic": round(current_c50to75_ic, 4),
        "degradation_pct": round(max_degradation, 4),
        "alert": alert,
    }

    log_data = []
    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                log_data = json.load(f)
        except Exception:
            log_data = []

    # Replace entry for today or append
    log_data = [e for e in log_data if e.get("date") != now_str]
    log_data.append(log_entry)

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2)
    logger.info(f"💾 Updated log at {LOG_FILE}")

    # Update calibration last_checked
    calibration["last_checked"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(CALIBRATION_FILE, "w", encoding="utf-8") as f:
        json.dump(calibration, f, indent=2)
    logger.info(f"💾 Updated last_checked in {CALIBRATION_FILE}")


if __name__ == "__main__":
    main()
