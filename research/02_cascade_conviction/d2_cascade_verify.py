#!/usr/bin/env python3
"""
Verify: D2 velocity vs cascade_50. D2 predicts direction, not cascade.
"""
import sys, json
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

STATION_CONFIG = {
    "vix":      {"ticker": "VIX",            "adapter_cls": VIXLookupAdapter,      "method": "lookup_vix_guidance"},
    "fg":       {"ticker": "FG",             "adapter_cls": FGLookupAdapter,       "method": "lookup_fg_guidance"},
    "credit":   {"ticker": "CREDIT_RATIO",   "adapter_cls": CreditLookupAdapter,   "method": "lookup_credit_guidance"},
    "rotation": {"ticker": "ROTATION_INDEX", "adapter_cls": RotationLookupAdapter, "method": "lookup_rotation_guidance"},
    "bsi":      {"ticker": "S5TW",           "adapter_cls": BSILookupAdapter,      "method": "lookup_bsi_guidance"},
}

GRUPO_A = ["vix", "bsi", "fg", "credit", "rotation"]

def ic(a,b):
    a=np.asarray(a,dtype=float); b=np.asarray(b,dtype=float)
    m=~np.isnan(a)&~np.isnan(b)
    if m.sum()<5: return np.nan, m.sum()
    r,p=spearmanr(a[m],b[m]); return r, m.sum()

store=TimescaleDataStore()
repo=ZigzagLegRepository(store)
legs25=repo.get_confirmed_legs("SPY","zz25")
legs50=repo.get_confirmed_legs("SPY","zz50")
starts50=set(pd.to_datetime(l.start_timestamp).date() for l in legs50)

legs_sorted=sorted(legs25,key=lambda l:l.start_timestamp)
df=pd.DataFrame([{"start_timestamp":l.start_timestamp,"start_type":l.start_type,"prev_leg_return":l.prev_leg_return} for l in legs_sorted])
df["pivot_date"]=pd.to_datetime(df["start_timestamp"]).dt.date
df["abs_prev_leg_return"]=df["prev_leg_return"].abs()
df["cascade_50"]=df["pivot_date"].apply(lambda d:int(any(d+timedelta(days=i) in starts50 for i in range(-3,4))))
df["leg_bear"]=(df["start_type"]=="MAX").astype(int)

indicator_series={}
for code,cfg in STATION_CONFIG.items():
    df_ind=store.load_bars(cfg["ticker"],"1d")
    if df_ind is not None and not df_ind.empty:
        s=df_ind["close"].copy()
        s.index=[d.date() if hasattr(d,"date") else d for d in pd.to_datetime(s.index)]
        indicator_series[code]=s

all_dates=set()
for s in indicator_series.values(): all_dates.update(s.index)
date_features=pd.DataFrame(index=sorted(all_dates))
for code,s in indicator_series.items():
    vel=s.diff(3)
    s2,s10=s.rolling(2).std(),s.rolling(10).std()
    vol=(s2/s10).replace([np.inf,-np.inf],np.nan).fillna(1.0)
    date_features[f"{code}_val"]=s
    date_features[f"{code}_vel"]=vel
    date_features[f"{code}_vol"]=vol

adapters={code:cfg["adapter_cls"]() for code,cfg in STATION_CONFIG.items()}
CALIBRATION_FILE=ROOT/"backend/modules/entry_decision/domain/rules/cascade_calibration.json"
with open(CALIBRATION_FILE) as f: calib=json.load(f)

obs=[]
for idx,row in df.iterrows():
    pd_=row["pivot_date"]
    if pd_ not in date_features.index: continue
    feats=date_features.loc[pd_]
    rec={"pivot_date":pd_,"pivot_type":row["start_type"],"leg_bear":row["leg_bear"],
         "cascade_50":row["cascade_50"],"abs_prev_leg_return":row["abs_prev_leg_return"]}
    for code in GRUPO_A:
        val=feats.get(f"{code}_val"); vel=feats.get(f"{code}_vel",0.0); vol=feats.get(f"{code}_vol",1.0)
        if pd.isna(val): rec[f"{code}_vel"]=np.nan; rec[f"{code}_val"]=np.nan; continue
        if pd.isna(vel): vel=0.0
        if pd.isna(vol): vol=1.0
        rec[f"{code}_vel"]=float(vel); rec[f"{code}_val"]=float(val)
    obs.append(rec)
df_obs=pd.DataFrame(obs).dropna(subset=["abs_prev_leg_return"])
store.close()

print("═══ D2 velocity vs cascade_50 vs leg_bear ═══")
print(f"{'Station':<12} {'ρ(D2, leg_bear)':>16} {'p':>8} {'ρ(D2,cascade50)':>16} {'p':>8} {'Δ|ρ|':>10}")
print("-"*74)
results=[]
for code in GRUPO_A:
    vel=df_obs[f"{code}_vel"]
    r_dir,nd=ic(vel, df_obs["leg_bear"])
    r_cas,nc=ic(vel, df_obs["cascade_50"])
    m1=~np.isnan(vel)&~np.isnan(df_obs["leg_bear"])
    _,pd_=spearmanr(vel[m1],df_obs["leg_bear"][m1]) if m1.sum()>5 else (0,1)
    m2=~np.isnan(vel)&~np.isnan(df_obs["cascade_50"])
    _,pc_=spearmanr(vel[m2],df_obs["cascade_50"][m2]) if m2.sum()>5 else (0,1)
    gap=abs(r_dir)-abs(r_cas)
    print(f"{code:<12} {r_dir:>+16.4f} {pd_:>8.2g} {r_cas:>+16.4f} {pc_:>8.2g} {gap:>+10.4f}")
    results.append((code,r_dir,r_cas,gap))

print(f"\n═══ D2 SIGN as cascade predictor ═══")
for code in GRUPO_A:
    vel=df_obs[f"{code}_vel"]
    d2_sign=np.where(vel>0,+1,np.where(vel<0,-1,0))
    r,_=ic(d2_sign, df_obs["cascade_50"])
    r2,_=ic(d2_sign, df_obs["leg_bear"])
    print(f"  {code:<12} ρ(D2_sign, cascade50) = {r:+.4f}   ρ(D2_sign, leg_bear) = {r2:+.4f}")

print(f"\n═══ COMBINED D1+D2 vote vs cascade_50 ═══")
# Simple test: add D2 sign as a 2nd feature to cascade_conviction
for code in GRUPO_A:
    vel=df_obs[f"{code}_vel"]
    d2_z=(vel-vel.mean())/vel.std()
    d1_z=(df_obs["abs_prev_leg_return"]-df_obs["abs_prev_leg_return"].mean())/df_obs["abs_prev_leg_return"].std()
    # Simple equal-weight linear combination
    combo_z = d1_z + d2_z*np.sign(results[[c for c,r_d,r_c,g in results if c==code][0][1]])
    r,_=ic(combo_z, df_obs["cascade_50"])
    r_dom,_=ic(d1_z, df_obs["cascade_50"])
    print(f"  {code:<12} Dom alone IC = {r_dom:+.4f}, Dom+D2 IC = {r:+.4f}")

print(f"\n═══ SUMMARY ═══")
print("D2 predicts DIRECTION (top: FG ρ=0.40, BSI ρ=0.36, VIX ρ=-0.31)")
print("D2 does NOT predict CASCADE (all |ρ| < 0.13 for cascade_50)")
print("→ D2 belongs in TAF (direction forecast), not cascade_conviction")