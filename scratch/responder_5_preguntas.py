import json, numpy as np, pandas as pd
from datetime import timedelta
from scipy.stats import spearmanr

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import STATION_CONFIG, d1_directional_vote, CALIBRATION_FILE

RULES = "/root/botero-trade/backend/modules/entry_decision/domain/rules"
ALL = ["vix","vvix","pcr","fg","sv5_turbulence","skew","credit","yield_curve","rotation","bsi","dxy"]
GRUPO_A = ["vix","bsi","fg","credit","rotation"]

fact_stores = {}
for code in ALL:
    with open(f"{RULES}/{code}_fact_store.json") as f:
        fact_stores[code] = json.load(f)["states"]
with open(CALIBRATION_FILE) as f: cal = json.load(f)
w_bear = cal["type_mask"]["MIN"]["w_bear"]; w_dom = cal["type_mask"]["MIN"]["w_dom"]
d1_mean = cal["d1_bear_5"]["mean"]; d1_std = cal["d1_bear_5"]["std"]
dom_mean = cal["domino_zz25"]["mean"]; dom_std = cal["domino_zz25"]["std"]

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)
legs25 = repo.get_confirmed_legs("SPY","zz25")
legs50 = repo.get_confirmed_legs("SPY","zz50")
starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)

df25 = pd.DataFrame([{"start_timestamp":l.start_timestamp,"start_type":l.start_type,"prev_leg_return":l.prev_leg_return} for l in legs25])
df25 = df25.dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["cascade_50"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in starts50 for i in range(-3,4))))
df25["next_type"] = df25["start_type"].shift(-1)
df25["next_bear"] = (df25["next_type"]=="MIN").astype(float)
df25["abs_prev_leg_return"] = np.abs(df25["prev_leg_return"])

indicator_series = {}
for code, cfg in STATION_CONFIG.items():
    s = store.load_bars(cfg["ticker"],"1d")["close"].copy()
    s.index = [d.date() if hasattr(d,'date') else d for d in pd.to_datetime(s.index)]
    indicator_series[code] = s
all_dates = set(); [all_dates.update(s.index) for s in indicator_series.values()]
date_features = pd.DataFrame(index=sorted(all_dates))
for code, s in indicator_series.items():
    vel = s.diff(3); std2=s.rolling(2).std(); std10=s.rolling(10).std()
    vol=(std2/std10).fillna(1.0)
    date_features[f"{code}_val"]=s; date_features[f"{code}_vel"]=vel; date_features[f"{code}_vol"]=vol

adapters = {code: cfg["adapter_cls"]() for code, cfg in STATION_CONFIG.items()}
store.close()

obs = []
for idx, row in df25.iterrows():
    pd_ = row["pivot_date"]
    if pd_ not in date_features.index: continue
    feats = date_features.loc[pd_]
    rec = {"cascade_50":row["cascade_50"], "next_bear":row["next_bear"], 
           "start_type":row["start_type"], "abs_prev_leg_return":row["abs_prev_leg_return"]}
    votes={}
    for code in GRUPO_A:
        val=feats.get(f"{code}_val"); vel=feats.get(f"{code}_vel",0.0); vol=feats.get(f"{code}_vol",1.0)
        if pd.isna(val): continue
        if pd.isna(vel): vel=0.0
        if pd.isna(vol): vol=1.0
        try:
            method = STATION_CONFIG[code]["method"]
            res = getattr(adapters[code], method)(val=float(val), d3_speed=float(vel), vol_norm=float(vol), vol_d3=float(vol))
            if res and res.state_key:
                votes[code]=d1_directional_vote(res.state_key)
                sk = res.state_key
                zk = fact_stores[code].get(sk, {}).get("zigzag_kinematic", {}).get("zz25", {})
                rec[f"{code}_pbull"] = zk.get("p_bull")
        except: continue
    p_type = row["start_type"]
    allowed = set(cal["type_mask"].get(p_type, {}).get("stations", GRUPO_A))
    mv=[v for c,v in votes.items() if c in allowed]
    d1b5 = sum(1 for v in mv if v<0)/len(mv) if mv else 0
    z_bear = (d1b5 - d1_mean)/d1_std
    z_dom = (row["abs_prev_leg_return"] - dom_mean)/dom_std
    rec["cascade_cc"] = w_bear*z_bear + w_dom*z_dom
    obs.append(rec)

df = pd.DataFrame(obs)

# Global p_bull from ALL 11 stations
all_pbull_cols = [f"{c}_pbull" for c in ALL if f"{c}_pbull" in df.columns]
df["global_pbull"] = df[all_pbull_cols].mean(axis=1, skipna=True)

def ic(a,b):
    a=np.asarray(a,dtype=float); b=np.asarray(b,dtype=float)
    m=~np.isnan(a)&~np.isnan(b)
    return spearmanr(a[m],b[m])[0] if m.sum()>=30 else np.nan

y_cascade = df["cascade_50"].values
y_dir = df["next_bear"].values

print("═══ PREGUNTA A: ¿Un solo score o dos targets? ═══\n")
# Test: does global_pbull correlate with cascade_cc?
r_cross = ic(df["global_pbull"], df["cascade_cc"])
print(f"Correlación state_vector ↔ cascade_conviction: ρ={r_cross:+.4f}")
print(f"→ {'ORTOGONALES (targets independientes)' if abs(r_cross)<0.2 else 'REDUNDANTES (fusionar)' if abs(r_cross)>0.5 else 'DÉBILMENTE correlacionados (complementarios)'}")

print(f"\nIC(state_vector → cascade_50) = {ic(df['global_pbull'], y_cascade):+.4f}")
print(f"IC(state_vector → direction)  = {ic(df['global_pbull'], y_dir):+.4f}")
print(f"IC(cascade_cc → cascade_50)   = {ic(df['cascade_cc'], y_cascade):+.4f}")
print(f"IC(cascade_cc → direction)    = {ic(df['cascade_cc'], y_dir):+.4f}")

print("\n═══ PREGUNTA B: ¿Complementa o reemplaza? ═══")
# When they AGREE vs DISAGREE
sv_bull = df["global_pbull"] > 0.5
cc_high = df["cascade_cc"] > 0
agree = sv_bull & cc_high
disagree = sv_bull & ~cc_high
print(f"  Ambos alcistas (agree):       cascade_rate={y_cascade[agree].mean():.1%}  N={agree.sum()}")
print(f"  State alcista, CC bajista:    cascade_rate={y_cascade[disagree].mean():.1%}  N={disagree.sum()}")

print("\n═══ PREGUNTA D: ¿D2 explícito mejora el state vector? ═══")
# State vector alone (implicit D2 via state_key) vs adding explicit D2
for code in ALL:
    vel_col = f"{code}_vel"
    if vel_col not in df.columns: continue
    vel_vals = [feats.get(vel_col, np.nan) for _, row in df.iterrows()]
    combined = df["global_pbull"].values - 0.5 * np.sign(vel_vals) * 0.1  # simple: adjust p_bull by velocity sign
    r_combined = ic(pd.Series(combined), y_dir)
    r_alone = ic(df["global_pbull"], y_dir)
    # Only print if meaningful difference
    if abs(r_combined) > abs(r_alone)*1.02:
        print(f"  {code:<12}: state={r_alone:+.4f} → +D2 explícito={r_combined:+.4f} (+{abs(r_combined/r_alone)-1:+.1%})")

print("\n═══ PREGUNTA E: INCERTIDUMBRE ═══")
# Dispersión entre estaciones como medida de confianza
df["pbull_std"] = df[all_pbull_cols].std(axis=1, skipna=True)
pbull_lo_conf = df["pbull_std"] > df["pbull_std"].median()  # high dispersion = low confidence
pbull_hi_conf = df["pbull_std"] <= df["pbull_std"].median()
r_lo = ic(df.loc[pbull_lo_conf, "global_pbull"], y_dir[pbull_lo_conf])
r_hi = ic(df.loc[pbull_hi_conf, "global_pbull"], y_dir[pbull_hi_conf])
print(f"  Alta dispersión (baja confianza): IC={r_lo:+.4f} (N={pbull_lo_conf.sum()})")
print(f"  Baja dispersión (alta confianza): IC={r_hi:+.4f} (N={pbull_hi_conf.sum()})")
print(f"  → La señal es {'MÁS' if abs(r_hi)>abs(r_lo) else 'MENOS'} confiable con acuerdo entre estaciones")