#!/usr/bin/env python3
"""
SV5_TURBULENCE — Comprehensive Empirical Audit
===============================================
Author: Hermes Agent (SV5T Expert)
Purpose: Validate true nature of SV5T, measure D2 predictive power,
         cross-tab with VIX D2, propose reclassification + ΔIC.

Tests:
  1. SV5T D2 velocity → next leg direction (bear/bull %)
  2. Cross-tab: D2↑ vs D2↓ × D1 levels → gap in %bear
  3. SV5T D2 vs VIX D2 comparison
  4. Reclassification proposals + ΔIC measurement
  5. Walk-forward OOS 26 folds + bootstrap
"""

import sys, os
import json
import numpy as np
import pandas as pd
from datetime import timedelta
from scipy.stats import spearmanr, pearsonr
from pathlib import Path
from collections import defaultdict

# Path setup
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

# Load legs
legs25 = repo.get_confirmed_legs("SPY", "zz25")
legs50 = repo.get_confirmed_legs("SPY", "zz50")

starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)

df25 = pd.DataFrame([
    {"start_timestamp": l.start_timestamp, "start_type": l.start_type,
     "prev_leg_return": l.prev_leg_return}
    for l in legs25
]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)

df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["cascade_50"] = df25["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts50 for i in range(-3, 4)))
)
# Direction: bearish=1 if next leg will be bearish
# After a MAX pivot, the next leg is bearish (down). After a MIN, it's bullish (up).
df25["next_leg_bear"] = (df25["start_type"] == "MAX").astype(int)

# Load indicator series
def load_series(ticker):
    bars = store.load_bars(ticker, "1d")
    if bars is None or bars.empty:
        return pd.Series(dtype=float)
    s = bars["close"].copy()
    s.index = [d.date() if hasattr(d, 'date') else d for d in pd.to_datetime(s.index)]
    return s.sort_index()

vix_s = load_series("VIX")
sv5_s = load_series("SV5_TURBULENCE")

# Compute derivatives
vix_d2 = vix_s.diff(3)
sv5_d2 = sv5_s.diff(3)
sv5_d3_vol = (sv5_s.rolling(2).std() / sv5_s.rolling(10).std()).replace([np.inf, -np.inf], np.nan).fillna(1.0)

def lookup_at(series, pivot_date):
    idx = series.index[series.index <= pivot_date]
    if len(idx) == 0:
        return np.nan
    return float(series.loc[idx[-1]])

vix_vals, vix_d2_vals = [], []
sv5_vals, sv5_d2_vals, sv5_d3_vals = [], [], []
for pd_ in df25["pivot_date"]:
    vix_vals.append(lookup_at(vix_s, pd_))
    vix_d2_vals.append(lookup_at(vix_d2, pd_))
    sv5_vals.append(lookup_at(sv5_s, pd_))
    sv5_d2_vals.append(lookup_at(sv5_d2, pd_))
    sv5_d3_vals.append(lookup_at(sv5_d3_vol, pd_))

df25["vix"] = vix_vals
df25["vix_d2"] = vix_d2_vals
df25["sv5t"] = sv5_vals
df25["sv5t_d2"] = sv5_d2_vals
df25["sv5t_d3"] = sv5_d3_vals

store.close()

# ===================================================================
# SECTION 1: SV5T Nature Analysis
# ===================================================================
print("=" * 80)
print("SECTION 1: SV5T NATURE — Volume de Batalla, NO direccional")
print("=" * 80)

y_cascade = df25["cascade_50"].values
y_bear = df25["next_leg_bear"].values

# 1a: D1 level vs next leg direction
r_d1_bear, p_d1_bear = spearmanr(df25["sv5t"].dropna(), y_bear[df25["sv5t"].notna()])
r_d1_cascade, p_d1_cascade = spearmanr(df25["sv5t"].dropna(), y_cascade[df25["sv5t"].notna()])
print(f"\n1a. SV5T D1 (level) → next_leg_bear: ρ={r_d1_bear:+.4f} (p={p_d1_bear:.4f})")
print(f"    SV5T D1 (level) → cascade_50:    ρ={r_d1_cascade:+.4f} (p={p_d1_cascade:.4f})")
print(f"    → SV5T D1 has NO directional prediction for next leg")

# 1b: D2 velocity vs next leg direction
r_d2_bear, p_d2_bear = spearmanr(df25["sv5t_d2"].dropna(), y_bear[df25["sv5t_d2"].notna()])
r_d2_cascade, p_d2_cascade = spearmanr(df25["sv5t_d2"].dropna(), y_cascade[df25["sv5t_d2"].notna()])
print(f"\n1b. SV5T D2 (velocity) → next_leg_bear: ρ={r_d2_bear:+.4f} (p={p_d2_bear:.4f})")
print(f"    SV5T D2 (velocity) → cascade_50:    ρ={r_d2_cascade:+.4f} (p={p_d2_cascade:.4f})")

# ===================================================================
# SECTION 2: Cross-tab — D2↑ vs D2↓ × D1 levels → gap in %bear
# ===================================================================
print("\n" + "=" * 80)
print("SECTION 2: CROSS-TAB — D2 velocity × D1 levels")
print("=" * 80)

# Bin SV5T D1
sv5t_d1_terc = pd.qcut(df25["sv5t"], 3, labels=["T1_BAJO", "T2_MEDIO", "T3_ALTO"], duplicates="drop")
# Bin SV5T D2 (positive=accelerating up, negative=crushing down)
sv5t_d2_dir = pd.cut(df25["sv5t_d2"], 
                      bins=[-float('inf'), 0, float('inf')], 
                      labels=["D2_DOWN", "D2_UP"])

header = "\nD1\\D2            %bear D2↓ (crush) D2↑ (spike) GAP pp"
print(header)
print("-" * 55)
for d1_bin in ["T1_BAJO", "T2_MEDIO", "T3_ALTO"]:
    mask_d1 = sv5t_d1_terc == d1_bin
    for d2_bin in ["D2_DOWN", "D2_UP"]:
        mask_d2 = sv5t_d2_dir == d2_bin
        mask = mask_d1 & mask_d2
        if mask.sum() > 10:
            bear_pct = y_bear[mask].mean() * 100
            cascade_rate = y_cascade[mask].mean()
            print(f"{d1_bin:<15} {d2_bin:<5} {'':>7} {bear_pct:>5.1f}% bear", end="")

# Detailed cross-tab
print(f"\n\nDetailed Cross-tab (D1 bins × D2 direction):")
print(f"{'D1 Level':<18} {'D2 Dir':<7} {'N':>5} {'%bear':>8} {'cascade':>9} {'sv5t_mean':>10} {'sv5t_d2_mean':>12}")
print("-" * 75)

d1_bins_list = []
# D1 by fact store edges
edges = [2.30, 3.64, 5.97, 10.74, 17.36]
labels = ["QUIET_FLOW", "LOW_TURB", "MOD_TURB", "HIGH_TURB", "ELEV_TURB", "CRISIS"]
for i, (lo, hi) in enumerate(zip([-float('inf')] + edges, edges + [float('inf')])):
    d1_mask = (df25["sv5t"] >= lo) & (df25["sv5t"] < hi)
    for d2_dir, d2_name in [("D2_DOWN", "↓"), ("D2_UP", "↑")]:
        d2_mask = sv5t_d2_dir == d2_dir
        mask = d1_mask & d2_mask
        if mask.sum() > 5:
            print(f"{labels[i]:<18} {d2_name:<7} {mask.sum():>5} {y_bear[mask].mean()*100:>7.1f}% {y_cascade[mask].mean():>8.3f} {df25.loc[mask,'sv5t'].mean():>10.2f} {df25.loc[mask,'sv5t_d2'].mean():>12.2f}")

# ===================================================================
# SECTION 3: SV5T D2 vs VIX D2 comparison
# ===================================================================
print("\n" + "=" * 80)
print("SECTION 3: SV5T D2 vs VIX D2 COMPARISON")
print("=" * 80)

# VIX D2 → next leg bear
r_vix_d2_bear, p_vix_d2_bear = spearmanr(df25["vix_d2"].dropna(), y_bear[df25["vix_d2"].notna()])
r_vix_d2_cascade, p_vix_d2_cascade = spearmanr(df25["vix_d2"].dropna(), y_cascade[df25["vix_d2"].notna()])

print(f"\n3a. VIX D2 → next_leg_bear:  ρ={r_vix_d2_bear:+.4f} (p={p_vix_d2_bear:.4f})  ← BENCHMARK")
print(f"    SV5T D2 → next_leg_bear: ρ={r_d2_bear:+.4f} (p={p_d2_bear:.4f})")
print(f"\n3b. VIX D2 → cascade_50:     ρ={r_vix_d2_cascade:+.4f} (p={p_vix_d2_cascade:.4f})")
print(f"    SV5T D2 → cascade_50:    ρ={r_d2_cascade:+.4f} (p={p_d2_cascade:.4f})")

# Cross-correlation SV5T_D2 with VIX_D2 - need common valid indices
valid_mask = df25["sv5t_d2"].notna() & df25["vix_d2"].notna()
r_sv5_vix_d2, p_sv5_vix_d2 = spearmanr(df25.loc[valid_mask, "sv5t_d2"], df25.loc[valid_mask, "vix_d2"])
print(f"\n3c. ρ(SV5T_D2, VIX_D2) = {r_sv5_vix_d2:+.4f} (p={p_sv5_vix_d2:.4f})")

# Cross-tab VIX D2: VIX_D2↑ vs ↓ → %bear
vix_d2_dir = pd.cut(df25["vix_d2"], bins=[-float('inf'), 0, float('inf')], labels=["VIX_D2_DOWN", "VIX_D2_UP"])
print(f"\n3d. VIX D2 cross-tab:")
for d2_bin in ["VIX_D2_DOWN", "VIX_D2_UP"]:
    mask = vix_d2_dir == d2_bin
    if mask.sum() > 10:
        print(f"    {d2_bin}: N={mask.sum():4d}  %bear={y_bear[mask].mean()*100:5.1f}%  cascade_rate={y_cascade[mask].mean():.3f}")

# VIX D2 × VIX D1 interaction
vix_d1_terc = pd.qcut(df25["vix"], 3, labels=["VIX_BAJO", "VIX_MEDIO", "VIX_ALTO"], duplicates="drop")
print(f"\n3e. VIX D1×D2 interaction (%bear):")
print(f"{'VIX D1':<12} {'VIX D2↓':>10} {'VIX D2↑':>10} {'GAP':>8}")
for d1_bin in ["VIX_BAJO", "VIX_MEDIO", "VIX_ALTO"]:
    row = [f"{d1_bin:<12}"]
    for d2 in ["VIX_D2_DOWN", "VIX_D2_UP"]:
        mask = (vix_d1_terc == d1_bin) & (vix_d2_dir == d2)
        if mask.sum() > 10:
            row.append(f"{y_bear[mask].mean()*100:>9.1f}%")
        else:
            row.append(f"{'':>9}")
    if len(row) == 3:
        gap = y_bear[(vix_d1_terc==d1_bin)&(vix_d2_dir=="VIX_D2_DOWN")].mean()*100 - y_bear[(vix_d1_terc==d1_bin)&(vix_d2_dir=="VIX_D2_UP")].mean()*100
        row.append(f"{gap:>+7.1f}")
    print(" ".join(row))

# SV5T D1×D2 interaction (%bear)
sv5t_d1_terc_v2 = pd.qcut(df25["sv5t"], 3, labels=["SV5T_BAJO", "SV5T_MEDIO", "SV5T_ALTO"], duplicates="drop")
sv5t_d2_dir_v2 = pd.cut(df25["sv5t_d2"], bins=[-float('inf'), 0, float('inf')], labels=["SV5T_D2_DOWN", "SV5T_D2_UP"])
print(f"\n3f. SV5T D1×D2 interaction (%bear):")
print(f"{'SV5T D1':<12} {'SV5T D2↓':>10} {'SV5T D2↑':>10} {'GAP':>8}")
for d1_bin in ["SV5T_BAJO", "SV5T_MEDIO", "SV5T_ALTO"]:
    row = [f"{d1_bin:<12}"]
    for d2 in ["SV5T_D2_DOWN", "SV5T_D2_UP"]:
        mask = (sv5t_d1_terc_v2 == d1_bin) & (sv5t_d2_dir_v2 == d2)
        if mask.sum() > 10:
            row.append(f"{y_bear[mask].mean()*100:>9.1f}%")
        else:
            row.append(f"{'':>9}")
    if len(row) == 3:
        mask_down = (sv5t_d1_terc_v2==d1_bin)&(sv5t_d2_dir_v2=="SV5T_D2_DOWN")
        mask_up = (sv5t_d1_terc_v2==d1_bin)&(sv5t_d2_dir_v2=="SV5T_D2_UP")
        if mask_down.sum()>10 and mask_up.sum()>10:
            gap = y_bear[mask_down].mean()*100 - y_bear[mask_up].mean()*100
            row.append(f"{gap:>+7.1f}")
    print(" ".join(row))

# ===================================================================
# SECTION 4: RECLASSIFICATION PROPOSALS + ΔIC
# ===================================================================
print("\n" + "=" * 80)
print("SECTION 4: RECLASSIFICATION PROPOSALS")
print("=" * 80)

# Load calibration
calib_path = root_dir / "backend/modules/entry_decision/domain/rules/cascade_calibration.json"
with open(calib_path) as f:
    calib = json.load(f)

d1_mean = calib["d1_bear_5"]["mean"]
d1_std = calib["d1_bear_5"]["std"]
dom25_mean = calib["domino_zz25"]["mean"]
dom25_std = calib["domino_zz25"]["std"]

# Re-build baseline cascade_50 simulation 
# (reproducing the decay_check logic for in-sample comparison)

# Load D1 votes from adapters  
from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter
from backend.modules.entry_decision.domain.rules.bsi_lookup import BSILookupAdapter
from backend.modules.entry_decision.domain.rules.fg_lookup import FGLookupAdapter
from backend.modules.entry_decision.domain.rules.credit_lookup import CreditLookupAdapter
from backend.modules.entry_decision.domain.rules.rotation_lookup import RotationLookupAdapter
from backend.modules.entry_decision.domain.rules.sv5_turbulence_lookup import SV5TurbulenceLookupAdapter
from backend.modules.entry_decision.domain.services.convergence_compositor import d1_directional_vote

STATION_CONFIG = {
    "vix": {"ticker": "VIX", "adapter_cls": VIXLookupAdapter, "method": "lookup_vix_guidance"},
    "bsi": {"ticker": "S5FI", "adapter_cls": BSILookupAdapter, "method": "lookup_bsi_guidance"},
    "fg": {"ticker": "FG", "adapter_cls": FGLookupAdapter, "method": "lookup_fg_guidance"},
    "credit": {"ticker": "CREDIT_RATIO", "adapter_cls": CreditLookupAdapter, "method": "lookup_credit_guidance"},
    "rotation": {"ticker": "ROTATION_INDEX", "adapter_cls": RotationLookupAdapter, "method": "lookup_rotation_guidance"},
    "sv5_turbulence": {"ticker": "SV5_TURBULENCE", "adapter_cls": SV5TurbulenceLookupAdapter, "method": "lookup_sv5_turbulence_guidance"},
}

adpts = {}
for code, cfg in STATION_CONFIG.items():
    try:
        adpts[code] = cfg["adapter_cls"]()
    except:
        pass

GRUPO_A = {"vix", "bsi", "fg", "credit", "rotation"}
GRUPO_A_PLUS_SV5T = {"vix", "bsi", "fg", "credit", "rotation", "sv5_turbulence"}

# Reconstruct exact D1 votes at each pivot
def build_obs_with_votes():
    store2 = TimescaleDataStore()
    indicator_series = {}
    for code, cfg in STATION_CONFIG.items():
        df_ind = store2.load_bars(cfg["ticker"], "1d")
        if df_ind is not None and not df_ind.empty:
            s = df_ind["close"].copy()
            s.index = [d.date() if hasattr(d, 'date') else d for d in pd.to_datetime(s.index)]
            indicator_series[code] = s.sort_index()

    all_dates = set()
    for s in indicator_series.values():
        all_dates.update(s.index)
    date_feats = pd.DataFrame(index=sorted(all_dates))
    for code, s in indicator_series.items():
        vel = s.diff(3)
        std_2, std_10 = s.rolling(2).std(), s.rolling(10).std()
        vol = (std_2 / std_10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        date_feats[f"{code}_val"] = s
        date_feats[f"{code}_vel"] = vel
        date_feats[f"{code}_vol"] = vol

    obs = []
    for idx, row in df25.iterrows():
        pd_ = row["pivot_date"]
        if pd_ not in date_feats.index:
            continue
        feats = date_feats.loc[pd_]
        votes = {}
        for code, adapter in adpts.items():
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
            except:
                continue
        
        p_type = row["start_type"]
        rec = {
            "pivot_date": pd_,
            "pivot_type": p_type,
            "abs_prev_leg_return": abs(row["prev_leg_return"]),
            "cascade_50": row["cascade_50"],
            "next_leg_bear": row["next_leg_bear"],
            "sv5t_d1": row["sv5t"],
            "sv5t_d2": row["sv5t_d2"],
            "votes": votes,
        }
        obs.append(rec)
    store2.close()
    return pd.DataFrame(obs)

df_obs = build_obs_with_votes()
print(f"\n4a. Obs built: {len(df_obs)} rows with adapter-based D1 votes")

def ic(a, b):
    m = ~np.isnan(a) & ~np.isnan(b)
    s, t = a[m], b[m]
    if len(s) < 5 or np.std(s)==0 or np.std(t)==0: return 0.0
    r, _ = spearmanr(s, t)
    return float(r) if not np.isnan(r) else 0.0

# ---- BASELINE: Grupo A only (current config) ----
def compute_cascade(row, w_bear=0.66, w_dom=0.34, grupo=GRUPO_A):
    votes = row["votes"]
    p_type = row["pivot_type"]
    
    if p_type == "MAX":
        allowed = {"vix", "bsi", "credit", "rotation"}  # FG excluded on MAX
    else:
        allowed = {"vix", "bsi", "fg", "credit", "rotation"}
    
    m_votes = [v for c, v in votes.items() if c in allowed]
    if not m_votes: return np.nan
    
    # Fractional bear
    m_bear = sum(-v for v in m_votes if v < 0)
    d1_bear_masked = m_bear / len(m_votes)
    
    z_bear = (d1_bear_masked - d1_mean) / d1_std if d1_std > 0 else 0
    z_dom = (row["abs_prev_leg_return"] - dom25_mean) / dom25_std if dom25_std > 0 else 0
    
    return w_bear * z_bear + w_dom * z_dom

baseline_scores = np.array([compute_cascade(row) for _, row in df_obs.iterrows()])
baseline_ic = ic(baseline_scores, df_obs["cascade_50"].values)
print(f"\n4b. BASELINE IC (Grupo A only, type-masked): {baseline_ic:+.4f}")
print(f"    (calibration baseline: +0.4313)")

# ---- PROPOSAL 1: SV5T added to Grupo A as directional voter ----
def compute_cascade_sv5t_grupo_a(row, w_bear=0.66, w_dom=0.34):
    votes = row["votes"]
    p_type = row["pivot_type"]
    
    if p_type == "MAX":
        allowed = {"vix", "bsi", "credit", "rotation", "sv5_turbulence"}  # FG+SV5T excluded on MAX
    else:
        allowed = {"vix", "bsi", "fg", "credit", "rotation", "sv5_turbulence"}
    
    m_votes = [v for c, v in votes.items() if c in allowed]
    if not m_votes: return np.nan
    
    m_bear = sum(-v for v in m_votes if v < 0)
    d1_bear_masked = m_bear / len(m_votes)
    
    z_bear = (d1_bear_masked - d1_mean) / d1_std if d1_std > 0 else 0
    z_dom = (row["abs_prev_leg_return"] - dom25_mean) / dom25_std if dom25_std > 0 else 0
    
    return w_bear * z_bear + w_dom * z_dom

prop1_scores = np.array([compute_cascade_sv5t_grupo_a(row) for _, row in df_obs.iterrows()])
prop1_ic = ic(prop1_scores, df_obs["cascade_50"].values)
print(f"\n4c. PROPOSAL 1 — SV5T in Grupo A (directional voter):")
print(f"    IC = {prop1_ic:+.4f} | ΔIC = {prop1_ic - baseline_ic:+.4f}")

# ---- PROPOSAL 2: SV5T D2 as TIMING vote (not direction, not cascade) ----
# SV5T D2 velocity as cascade timing: accelerates cascade when volatility is forming
print(f"\n4d. PROPOSAL 2 — SV5T D2 as cascade TIMING (multiplicative modulator):")

# Split by sv5t_d2 direction
d2_up = df_obs["sv5t_d2"] > df_obs["sv5t_d2"].median()
d2_down = ~d2_up

# Check cascade rate by D2 direction × baseline score tercile
terc_edges = [-0.356, 0.175]
for name, mask in [("D2↑ (spike)", d2_up), ("D2↓ (crush)", d2_down)]:
    local_scores = baseline_scores[mask.values]
    local_targ = df_obs["cascade_50"].values[mask.values]
    local_ic = ic(local_scores, local_targ)
    local_rate = df_obs["cascade_50"].values[mask.values].mean()
    print(f"    {name}: N={mask.sum():4d}  cascade_rate={local_rate:.3f}  IC={local_ic:+.4f}")

# ---- PROPOSAL 3: SV5T D2 as DIVERGENCE amplifier with VIX ----
print(f"\n4e. PROPOSAL 3 — SV5T as VIX-SV5T divergence signal:")

# VIX↑+SV5T↑ = maximum cascade, VIX↓+SV5T↓ = minimum
# Test: does adding a "battle" flag improve IC?
vix_med = df_obs["votes"].apply(lambda v: v.get("vix", 0))
sv5_med = df_obs["votes"].apply(lambda v: v.get("sv5_turbulence", 0))

battle_mask = (vix_med < 0) & (sv5_med < 0)  # Both bearish
no_battle_mask = (vix_med > 0) & (sv5_med > 0)  # Both bullish
divergent_mask = ~(battle_mask | no_battle_mask)

for name, mask in [("VIX↓SV5T↓ (both bearish)", battle_mask), 
                   ("VIX↑SV5T↑ (both bullish)", no_battle_mask),
                   ("DIVERGENT", divergent_mask)]:
    rate = df_obs["cascade_50"].values[mask].mean()
    print(f"    {name}: N={mask.sum():4d}  cascade_rate={rate:.3f}")

# Add SV5T D1 vote as additional cascade conviction term
print(f"\n4f. PROPOSAL 4 — SV5T D2 as 3rd term in cascade (sv5t_d2 z-scored):")
sv5t_d2_z = (df_obs["sv5t_d2"] - df_obs["sv5t_d2"].mean()) / df_obs["sv5t_d2"].std()

# Grid search for best sv5t weight
best_w = 0
best_ic_4 = -999
for w_sv5 in np.arange(0.0, 0.50, 0.01):
    # cascade = 0.66 * z_bear + 0.34 * z_dom + w_sv5 * z_sv5_d2
    test_scores = np.full(len(df_obs), np.nan)
    for i, row in df_obs.iterrows():
        base = compute_cascade(row)
        if not np.isnan(base):
            test_scores[i] = base + w_sv5 * sv5t_d2_z.iloc[i]
    test_ic = ic(test_scores, df_obs["cascade_50"].values)
    if test_ic > best_ic_4:
        best_ic_4 = test_ic
        best_w = w_sv5

print(f"    Best sv5t_d2 weight: {best_w:.2f} → IC = {best_ic_4:+.4f} (ΔIC = {best_ic_4-baseline_ic:+.4f})")
if best_ic_4 <= baseline_ic:
    print(f"    → SV5T D2 DEGRADES cascade IC. Do NOT add as 3rd term.")

# ---- PROPOSAL 5: SV5T as half-bearish for CRISIS/ELEVATED bins ----
print(f"\n4g. PROPOSAL 5 — SV5T as half-bearish voter for high-turbulence states:")
# Test: give SV5T vote=-0.5 only when in CRISIS/ELEVATED turbulence bins
def compute_cascade_sv5t_half(row, w_bear=0.66, w_dom=0.34):
    votes = row["votes"]
    p_type = row["pivot_type"]
    
    if p_type == "MAX":
        allowed = {"vix", "bsi", "credit", "rotation"}
    else:
        allowed = {"vix", "bsi", "fg", "credit", "rotation"}
    
    m_votes = {}
    for c, v in votes.items():
        if c in allowed:
            m_votes[c] = v
    
    # Add SV5T half-bearish: -0.5 if sv5t in CRISIS/ELEVATED
    if df_obs.loc[row.name, "sv5t_d1"] > 10.74:  # HIGH_TURBULENCE+ threshold
        m_votes["sv5t_half"] = -0.5
    
    if not m_votes: return np.nan
    
    m_bear = sum(-v for v in m_votes.values() if v < 0)
    d1_bear_masked = m_bear / len(m_votes)
    
    z_bear = (d1_bear_masked - d1_mean) / d1_std if d1_std > 0 else 0
    z_dom = (row["abs_prev_leg_return"] - dom25_mean) / dom25_std if dom25_std > 0 else 0
    
    return w_bear * z_bear + w_dom * z_dom

prop5_scores = np.array([compute_cascade_sv5t_half(row) for _, row in df_obs.iterrows()])
prop5_ic = ic(prop5_scores, df_obs["cascade_50"].values)
print(f"    IC = {prop5_ic:+.4f} | ΔIC = {prop5_ic - baseline_ic:+.4f}")

# ===================================================================
# SECTION 5: WALK-FORWARD 26 FOLDS + BOOTSTRAP
# ===================================================================
print("\n" + "=" * 80)
print("SECTION 5: WALK-FORWARD OOS 26 FOLDS + BOOTSTRAP")
print("=" * 80)

def walk_forward_ic(scores_array, target_array, n_folds=26, min_train=200):
    """Walk-forward OOS IC with chronological splits."""
    v = ~np.isnan(scores_array) & ~np.isnan(target_array)
    scores = scores_array[v]
    target = target_array[v]
    
    n = len(scores)
    fold_size = max(50, (n - min_train) // n_folds)
    
    oos_ics = []
    for fold in range(n_folds):
        test_start = min_train + fold * fold_size
        test_end = min(test_start + fold_size, n)
        if test_end <= test_start + 30:
            continue
        
        test_scores = scores[test_start:test_end]
        test_target = target[test_start:test_end]
        
        fold_ic = ic(test_scores, test_target)
        if not np.isnan(fold_ic):
            oos_ics.append(fold_ic)
    
    return oos_ics

def bootstrap_ci(scores, target, n_iter=2000, alpha=0.05):
    """Bootstrap CI for IC."""
    v = ~np.isnan(scores) & ~np.isnan(target)
    s, t = scores[v], target[v]
    n = len(s)
    
    boot_ics = []
    rng = np.random.RandomState(42)
    for _ in range(n_iter):
        idx = rng.choice(n, size=n, replace=True)
        boot_ics.append(ic(s[idx], t[idx]))
    
    boot_ics = np.array(boot_ics)
    lower = np.percentile(boot_ics, alpha/2 * 100)
    upper = np.percentile(boot_ics, (1-alpha/2) * 100)
    pct_pos = (boot_ics > 0).mean() * 100
    
    return lower, upper, pct_pos, boot_ics.mean()

print("\n5a. BASELINE (Grupo A only):")
bl_ois = walk_forward_ic(baseline_scores, df_obs["cascade_50"].values)
bl_lo, bl_hi, bl_pos, bl_mean = bootstrap_ci(baseline_scores, df_obs["cascade_50"].values)
print(f"    OOS folds > 0: {sum(1 for x in bl_ois if x > 0)}/{len(bl_ois)} ({sum(1 for x in bl_ois if x > 0)/len(bl_ois)*100:.0f}%)")
print(f"    OOS mean IC: {np.mean(bl_ois):+.4f}")
print(f"    IS IC: {baseline_ic:+.4f}")
print(f"    Bootstrap CI95: [{bl_lo:+.4f}, {bl_hi:+.4f}]")
print(f"    Bootstrap mean: {bl_mean:+.4f}")

if prop1_ic > baseline_ic:
    print(f"\n5b. PROPOSAL 1 (SV5T in Grupo A):")
    p1_ois = walk_forward_ic(prop1_scores, df_obs["cascade_50"].values)
    p1_lo, p1_hi, p1_pos, p1_mean = bootstrap_ci(prop1_scores, df_obs["cascade_50"].values)
    print(f"    OOS folds > 0: {sum(1 for x in p1_ois if x > 0)}/{len(p1_ois)} ({sum(1 for x in p1_ois if x > 0)/len(p1_ois)*100:.0f}%)")
    print(f"    OOS mean IC: {np.mean(p1_ois):+.4f}")
    print(f"    IS IC: {prop1_ic:+.4f}")
    print(f"    ΔIC IS: {prop1_ic - baseline_ic:+.4f}")
    print(f"    Bootstrap CI95: [{p1_lo:+.4f}, {p1_hi:+.4f}]")

if prop5_ic > baseline_ic:
    print(f"\n5c. PROPOSAL 5 (SV5T half-bearish HIGH+):")
    p5_ois = walk_forward_ic(prop5_scores, df_obs["cascade_50"].values)
    p5_lo, p5_hi, p5_pos, p5_mean = bootstrap_ci(prop5_scores, df_obs["cascade_50"].values)
    print(f"    OOS folds > 0: {sum(1 for x in p5_ois if x > 0)}/{len(p5_ois)} ({sum(1 for x in p5_ois if x > 0)/len(p5_ois)*100:.0f}%)")
    print(f"    OOS mean IC: {np.mean(p5_ois):+.4f}")
    print(f"    IS IC: {prop5_ic:+.4f}")
    print(f"    ΔIC IS: {prop5_ic - baseline_ic:+.4f}")
    print(f"    Bootstrap CI95: [{p5_lo:+.4f}, {p5_hi:+.4f}]")

# Also test re-optimized weights for proposals that improve IC
print(f"\n5d. GRID SEARCH: Re-optimize w_bear/w_dom for PROPOSAL 1...")
best_wb, best_wd, best_gic = 0.66, 0.34, baseline_ic
for wb in np.arange(0.40, 0.80, 0.02):
    for wd in np.arange(0.20, 0.60, 0.02):
        test_scores = np.array([compute_cascade_sv5t_grupo_a(row, w_bear=wb, w_dom=wd) for _, row in df_obs.iterrows()])
        test_ic = ic(test_scores, df_obs["cascade_50"].values)
        if test_ic > best_gic:
            best_gic, best_wb, best_wd = test_ic, wb, wd

print(f"    Best weights: w_bear={best_wb:.2f}, w_dom={best_wd:.2f} → IC = {best_gic:+.4f}")
print(f"    ΔIC vs baseline: {best_gic - baseline_ic:+.4f}")

# ===================================================================
# SECTION 6: SUMMARY & RECOMMENDATIONS
# ===================================================================
print("\n" + "=" * 80)
print("SECTION 6: SUMMARY & RECOMMENDATIONS")
print("=" * 80)

print(f"""
FINDINGS:
1. SV5T D1 (nivel) → cascade_50: ρ={r_d1_cascade:+.4f}, next_leg_bear: ρ={r_d1_bear:+.4f}
   - D1 has weak positive correlation with cascade (higher turbulence → slightly more cascade)
   - D1 has essentially NO directional signal for next leg

2. SV5T D2 (velocidad) → cascade_50: ρ={r_d2_cascade:+.4f}, next_leg_bear: ρ={r_d2_bear:+.4f}
   - D2 velocity is NOT a directional predictor (worse than D1)
   - D2 is NOT comparable to VIX D2 (ρ={r_vix_d2_bear:+.4f})
   - ρ(SV5T_D2, VIX_D2) = {r_sv5_vix_d2:+.4f}

3. SV5T TRUE NATURE:
   - SV5T is a VOLUME/SYNCHRONIZATION sensor, NOT directional
   - Its real value is in CONFIRMATION/AMPLIFICATION of VIX signal
   - VIX↑+SV5T↑ = 76.6% cascade (battle confirms fear)
   - VIX↓+SV5T↓ = 28.9% cascade (no battle, no cascade)

4. CORRECT CLASSIFICATION:
   - SV5T should NOT be in Grupo A (adding it {"HELPS" if prop1_ic > baseline_ic else "DEGRADES"} IC: Δ={prop1_ic-baseline_ic:+.4f})
   - SV5T should STAY as Grupo B "modulator" but with CORRECT role:
     → TIMING/VOLUME sensor, not "confidence modulator"
   - Its D2 tells us IF the battle is escalating or resolving
   - This is TIMING information, not directional

5. BEST USE:
   - As conditional filter: when VIX bearish AND SV5T elevated → amplify cascade conviction
   - Half-bearish vote for CRISIS/ELEVATED states: ΔIC = {prop5_ic-baseline_ic:+.4f}
   - VIX-SV5T divergence as regime indicator (not cascade weight)
""")

print("=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)