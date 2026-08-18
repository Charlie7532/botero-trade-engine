#!/usr/bin/env python3
"""
Quick benchmark: BSI ticker comparison (S5TW vs S5FI) and final S5FI-aligned full analysis.
"""
import sys, json
from datetime import timedelta
from pathlib import Path
import numpy as np, pandas as pd
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

GRUPO_A = ["vix", "bsi", "fg", "credit", "rotation"]

def build_and_measure(bsi_ticker):
    config = {
        "vix":      {"ticker": "VIX",            "adapter_cls": VIXLookupAdapter,      "method": "lookup_vix_guidance"},
        "fg":       {"ticker": "FG",             "adapter_cls": FGLookupAdapter,       "method": "lookup_fg_guidance"},
        "credit":   {"ticker": "CREDIT_RATIO",   "adapter_cls": CreditLookupAdapter,   "method": "lookup_credit_guidance"},
        "rotation": {"ticker": "ROTATION_INDEX", "adapter_cls": RotationLookupAdapter, "method": "lookup_rotation_guidance"},
        "bsi":      {"ticker": bsi_ticker,       "adapter_cls": BSILookupAdapter,      "method": "lookup_bsi_guidance"},
    }

    store = TimescaleDataStore()
    repo = ZigzagLegRepository(store)
    legs25 = repo.get_confirmed_legs("SPY", "zz25")
    legs50 = repo.get_confirmed_legs("SPY", "zz50")
    starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)

    legs_sorted = sorted(legs25, key=lambda l: l.start_timestamp)
    df = pd.DataFrame([{"start_timestamp": l.start_timestamp, "start_type": l.start_type, "prev_leg_return": l.prev_leg_return} for l in legs_sorted])
    df["pivot_date"] = pd.to_datetime(df["start_timestamp"]).dt.date
    df["abs_prev_leg_return"] = df["prev_leg_return"].abs()
    df["cascade_50"] = df["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in starts50 for i in range(-3,4))))
    df["leg_bear"] = (df["start_type"] == "MAX").astype(int)

    indicator_series = {}
    for code, cfg in config.items():
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
        s2, s10 = s.rolling(2).std(), s.rolling(10).std()
        vol = (s2/s10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        date_features[f"{code}_val"] = s
        date_features[f"{code}_vel"] = vel
        date_features[f"{code}_vol"] = vol

    adapters = {code: cfg["adapter_cls"]() for code, cfg in config.items()}
    CALIBRATION_FILE = ROOT / "backend/modules/entry_decision/domain/rules/cascade_calibration.json"
    with open(CALIBRATION_FILE) as f:
        calib = json.load(f)

    obs = []
    for idx, row in df.iterrows():
        pd_ = row["pivot_date"]
        if pd_ not in date_features.index:
            continue
        feats = date_features.loc[pd_]
        rec = {"pivot_date": pd_, "pivot_type": row["start_type"], "leg_bear": row["leg_bear"],
               "cascade_50": row["cascade_50"], "abs_prev_leg_return": row["abs_prev_leg_return"]}
        votes = {}
        for code in GRUPO_A:
            val = feats.get(f"{code}_val"); vel = feats.get(f"{code}_vel", 0.0); vol = feats.get(f"{code}_vol", 1.0)
            if pd.isna(val): rec[f"{code}_vel"] = np.nan; rec[f"{code}_d1_vote"] = np.nan; continue
            if pd.isna(vel): vel = 0.0
            if pd.isna(vol): vol = 1.0
            rec[f"{code}_vel"] = float(vel)
            try:
                method = config[code]["method"]
                res = getattr(adapters[code], method)(val=float(val), d3_speed=float(vel), vol_norm=float(vol), vol_d3=float(vol))
                if res and res.state_key:
                    rec[f"{code}_d1_vote"] = d1_directional_vote(res.state_key)
                else:
                    rec[f"{code}_d1_vote"] = np.nan
            except Exception:
                rec[f"{code}_d1_vote"] = np.nan
        obs.append(rec)

    df_obs = pd.DataFrame(obs)
    for idx, row in df_obs.iterrows():
        p_type = row["pivot_type"]
        allowed = set(calib["type_mask"][p_type]["stations"]) if p_type in calib.get("type_mask", {}) else set(GRUPO_A)
        m_votes = [row.get(f"{code}_d1_vote", np.nan) for code in allowed]
        m_votes = [v for v in m_votes if not np.isnan(v)]
        m_bear = sum(-v for v in m_votes if v < 0)
        df_obs.at[idx, "d1_bear_5"] = (m_bear / len(m_votes)) if m_votes else np.nan

    df_obs = df_obs.dropna(subset=["d1_bear_5", "abs_prev_leg_return"]).reset_index(drop=True)
    store.close()

    d1_mean, d1_std = calib["d1_bear_5"]["mean"], calib["d1_bear_5"]["std"]
    dom25_mean, dom25_std = calib["domino_zz25"]["mean"], calib["domino_zz25"]["std"]
    w_bear, w_dom = 0.66, 0.34

    z_b = (df_obs["d1_bear_5"] - d1_mean) / d1_std
    z_d = (df_obs["abs_prev_leg_return"] - dom25_mean) / dom25_std
    c50 = w_bear * z_b + w_dom * z_d

    def ic(a,b):
        a=np.asarray(a,float);b=np.asarray(b,float)
        m=~np.isnan(a)&~np.isnan(b)
        if m.sum()<5: return np.nan, m.sum()
        return spearmanr(a[m],b[m])[0], m.sum()

    base_ic, n = ic(c50, df_obs["cascade_50"])

    # D2 direction correlations
    print(f"\nBSI ticker: {bsi_ticker} — Baseline cascade_50 IC = {base_ic:+.4f} (N={n})")
    for code in GRUPO_A:
        vel = df_obs[f"{code}_vel"]
        r_dir, _ = ic(vel, df_obs["leg_bear"])
        r_cas, _ = ic(vel, df_obs["cascade_50"])
        print(f"  {code:<10} ρ(D2,dir)={r_dir:+.4f}  ρ(D2,cas50)={r_cas:+.4f}")

    return base_ic

# Compare both tickers
ic_tw = build_and_measure("S5TW")
ic_fi = build_and_measure("S5FI")
print(f"\n═══ COMPARISON ═══")
print(f"  S5TW (authoritative): baseline IC = {ic_tw:+.4f}")
print(f"  S5FI (decay_check):   baseline IC = {ic_fi:+.4f}")
print(f"  Stored baseline:       +0.4313")
print(f"  Decay check Aug 14:    +0.4298 (S5FI)")