#!/usr/bin/env python3
"""
D2 (velocity) direction analysis — Botero Trade Grupo A stations.
Step 1-3 + baseline reproduction.

Target: direction of the NEXT zigzag leg (bull/bear), i.e. start_type of the leg
whose start IS the pivot. Verified against the empirical finding:
  VIX D2 velocity -> next-leg direction  rho ~= -0.29
"""
import sys, json, math
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.services.convergence_compositor import d1_directional_vote

from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter
from backend.modules.entry_decision.domain.rules.fg_lookup import FGLookupAdapter
from backend.modules.entry_decision.domain.rules.credit_lookup import CreditLookupAdapter
from backend.modules.entry_decision.domain.rules.rotation_lookup import RotationLookupAdapter
from backend.modules.entry_decision.domain.rules.bsi_lookup import BSILookupAdapter

RULES = ROOT / "backend/modules/entry_decision/domain/rules"
CALIBRATION_FILE = RULES / "cascade_calibration.json"

# NOTE: decay_check STATION_CONFIG uses S5FI for BSI (documented discrepancy).
# We use S5TW (authoritative BSI ticker) for BSI but note both.
STATION_CONFIG = {
    "vix":      {"ticker": "VIX",            "adapter_cls": VIXLookupAdapter,      "method": "lookup_vix_guidance"},
    "fg":       {"ticker": "FG",             "adapter_cls": FGLookupAdapter,       "method": "lookup_fg_guidance"},
    "credit":   {"ticker": "CREDIT_RATIO",   "adapter_cls": CreditLookupAdapter,   "method": "lookup_credit_guidance"},
    "rotation": {"ticker": "ROTATION_INDEX", "adapter_cls": RotationLookupAdapter, "method": "lookup_rotation_guidance"},
    "bsi":      {"ticker": "S5TW",           "adapter_cls": BSILookupAdapter,      "method": "lookup_bsi_guidance"},
}

GRUPO_A = ["vix", "bsi", "fg", "credit", "rotation"]


def compute_ic(score, target):
    s = np.asarray(score, dtype=float)
    t = np.asarray(target, dtype=float)
    m = ~np.isnan(s) & ~np.isnan(t)
    if m.sum() < 5 or np.std(s[m]) == 0 or np.std(t[m]) == 0:
        return 0.0, m.sum()
    r, p = spearmanr(s[m], t[m])
    return (float(r) if not np.isnan(r) else 0.0), m.sum()


def main():
    with open(CALIBRATION_FILE) as f:
        calib = json.load(f)
    d1_mean, d1_std = calib["d1_bear_5"]["mean"], calib["d1_bear_5"]["std"]
    dom25_mean, dom25_std = calib["domino_zz25"]["mean"], calib["domino_zz25"]["std"]

    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)
    legs25 = repo.get_confirmed_legs("SPY", "zz25")
    legs50 = repo.get_confirmed_legs("SPY", "zz50")
    starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)

    # Ordered chronological dataframe of legs
    legs_sorted = sorted(legs25, key=lambda l: l.start_timestamp)
    df = pd.DataFrame([
        {"start_timestamp": l.start_timestamp, "start_type": l.start_type,
         "prev_leg_return": l.prev_leg_return}
        for l in legs_sorted
    ])
    df["pivot_date"] = pd.to_datetime(df["start_timestamp"]).dt.date
    df["abs_prev_leg_return"] = df["prev_leg_return"].abs()
    df["cascade_50"] = df["pivot_date"].apply(
        lambda d: int(any(d + timedelta(days=i) in starts50 for i in range(-3, 4)))
    )
    # Target: next-leg direction. "bear" = start_type == "MAX"
    df["leg_bear"] = (df["start_type"] == "MAX").astype(int)          # direction of leg starting at this pivot
    df["next_leg_bear"] = df["leg_bear"].shift(-1)                    # direction of the FOLLOWING leg

    # Indicator series
    indicator_series = {}
    for code, cfg in STATION_CONFIG.items():
        df_ind = store.load_bars(cfg["ticker"], "1d")
        if df_ind is not None and not df_ind.empty:
            s = df_ind["close"].copy()
            s.index = [d.date() if hasattr(d, "date") else d for d in pd.to_datetime(s.index)]
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

    obs = []
    for idx, row in df.iterrows():
        pd_ = row["pivot_date"]
        if pd_ not in date_features.index:
            continue
        feats = date_features.loc[pd_]
        rec = {
            "pivot_date": pd_, "pivot_type": row["start_type"],
            "leg_bear": row["leg_bear"], "next_leg_bear": row["next_leg_bear"],
            "cascade_50": row["cascade_50"],
            "abs_prev_leg_return": row["abs_prev_leg_return"],
        }
        votes = {}
        for code in GRUPO_A:
            val = feats.get(f"{code}_val")
            vel = feats.get(f"{code}_vel", 0.0)
            vol = feats.get(f"{code}_vol", 1.0)
            if pd.isna(val):
                rec[f"{code}_sk"] = None
                rec[f"{code}_vel"] = np.nan
                rec[f"{code}_val"] = np.nan
                continue
            if pd.isna(vel): vel = 0.0
            if pd.isna(vol): vol = 1.0
            rec[f"{code}_vel"] = float(vel)
            rec[f"{code}_val"] = float(val)
            try:
                method = STATION_CONFIG[code]["method"]
                res = getattr(adapters[code], method)(val=float(val), d3_speed=float(vel), vol_norm=float(vol), vol_d3=float(vol))
                if res and res.state_key:
                    rec[f"{code}_sk"] = res.state_key
                    votes[code] = d1_directional_vote(res.state_key)
                else:
                    rec[f"{code}_sk"] = None
            except Exception:
                rec[f"{code}_sk"] = None
        # type mask aware fractional bear count (same as decay check)
        p_type = row["start_type"]
        allowed = set(calib.get("type_mask", {}).get(p_type, {}).get("stations", GRUPO_A))
        m_votes = [v for c, v in votes.items() if c in allowed]
        m_bear = sum(-v for v in m_votes if v < 0)
        rec["d1_bear_5"] = (m_bear / len(m_votes)) if m_votes else np.nan
        obs.append(rec)

    df_obs = pd.DataFrame(obs)
    store.close()

    # Baseline cascade_conviction reproduction
    z_bear = (df_obs["d1_bear_5"] - d1_mean) / d1_std
    z_dom = (df_obs["abs_prev_leg_return"] - dom25_mean) / dom25_std
    c50 = 0.66 * z_bear + 0.34 * z_dom
    base_ic, n = compute_ic(c50, df_obs["cascade_50"])
    print(f"═══ BASELINE REPRODUCTION ═══")
    print(f"  cascade_conviction c50 IC = {base_ic:+.4f} (N={n})  [stored baseline 0.4313]")
    print(f"  N pivots = {len(df_obs)},  MIN={ (df_obs.pivot_type=='MIN').sum() }, MAX={ (df_obs.pivot_type=='MAX').sum() }")
    print(f"  leg_bear base rate = {df_obs.leg_bear.mean():.3f}, next_leg_bear base rate = {df_obs.next_leg_bear.mean():.3f}")

    # Step 1: rho(D2 vel, direction) and rho(D1 level, direction), both targets
    print(f"\n═══ STEP 1: D2 velocity vs next-leg direction (both target defs) ═══")
    print(f"{'station':<10} {'rho(D2,leg_bear)':>16} {'p':>8} | {'rho(D2,next_leg)':>16} {'p':>8} | {'rho(D1,leg_bear)':>16} {'p':>8}")
    for code in GRUPO_A:
        vel = df_obs[f"{code}_vel"]
        lvl = df_obs[f"{code}_val"]
        r_leg, n1 = compute_ic(vel, df_obs["leg_bear"])
        r_next, n2 = compute_ic(vel, df_obs["next_leg_bear"])
        r_lvl, n3 = compute_ic(lvl, df_obs["leg_bear"])
        # p-values
        def pval(a, b):
            a = np.asarray(a, float); b = np.asarray(b, float)
            m = ~np.isnan(a) & ~np.isnan(b)
            if m.sum() < 5: return np.nan, m.sum()
            _, p = spearmanr(a[m], b[m]); return p, m.sum()
        p_leg, _ = pval(vel, df_obs["leg_bear"])
        p_next, _ = pval(vel, df_obs["next_leg_bear"])
        p_lvl, _ = pval(lvl, df_obs["leg_bear"])
        print(f"{code:<10} {r_leg:>+16.4f} {p_leg:>8.2g} | {r_next:>+16.4f} {p_next:>8.2g} | {r_lvl:>+16.4f} {p_lvl:>8.2g}")

    df_obs.to_pickle("/root/botero-trade/data/research/d2_direction_obs.pkl")
    print(f"\n💾 saved to data/research/pivots/d2_direction_obs.pkl")


if __name__ == "__main__":
    main()
