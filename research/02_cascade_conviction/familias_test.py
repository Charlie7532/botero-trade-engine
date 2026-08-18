import json, numpy as np, pandas as pd
from datetime import timedelta
from scipy.stats import spearmanr

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import STATION_CONFIG

RULES = "/root/botero-trade/backend/modules/entry_decision/domain/rules"

# ALL 11 stations
ALL = ["vix","vvix","pcr","fg","sv5_turbulence","skew","credit","yield_curve","rotation","bsi","dxy"]

fact_stores = {}
for code in ALL:
    with open(f"{RULES}/{code}_fact_store.json") as f:
        fact_stores[code] = json.load(f)["states"]

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

# Load all station data
indicator_series = {}
for code, cfg in STATION_CONFIG.items():
    s = store.load_bars(cfg["ticker"],"1d")["close"].copy()
    s.index = [d.date() if hasattr(d,'date') else d for d in pd.to_datetime(s.index)]
    indicator_series[code] = s

all_dates = set()
for s in indicator_series.values(): all_dates.update(s.index)
date_features = pd.DataFrame(index=sorted(all_dates))
for code, s in indicator_series.items():
    vel = s.diff(3)
    std2=s.rolling(2).std(); std10=s.rolling(10).std()
    vol=(std2/std10).fillna(1.0)
    date_features[f"{code}_val"]=s; date_features[f"{code}_vel"]=vel; date_features[f"{code}_vol"]=vol

adapters = {code: cfg["adapter_cls"]() for code, cfg in STATION_CONFIG.items()}
store.close()

# Extract state probabilities for all 11 stations
obs = []
for idx, row in df25.iterrows():
    pd_ = row["pivot_date"]
    if pd_ not in date_features.index: continue
    feats = date_features.loc[pd_]
    rec = {"cascade_50":row["cascade_50"], "next_bear":row["next_bear"], "start_type":row["start_type"]}
    for code in ALL:
        val=feats.get(f"{code}_val"); vel=feats.get(f"{code}_vel",0.0); vol=feats.get(f"{code}_vol",1.0)
        if pd.isna(val): continue
        if pd.isna(vel): vel=0.0
        if pd.isna(vol): vol=1.0
        try:
            method = STATION_CONFIG[code]["method"]
            res = getattr(adapters[code], method)(val=float(val), d3_speed=float(vel), vol_norm=float(vol), vol_d3=float(vol))
            if res and res.state_key:
                sk = res.state_key
                zk = fact_stores[code].get(sk, {}).get("zigzag_kinematic", {}).get("zz25", {})
                rec[f"{code}_pbull"] = zk.get("p_bull")
                rec[f"{code}_pbear"] = zk.get("p_bear")
        except: continue
    obs.append(rec)

df = pd.DataFrame(obs)

def ic(a,b):
    a=np.asarray(a,dtype=float); b=np.asarray(b,dtype=float)
    m=~np.isnan(a)&~np.isnan(b)
    return spearmanr(a[m],b[m])[0] if m.sum()>=30 else np.nan

y_dir = df["next_bear"].values

# FAMILIES
FAMILIAS = {
    "miedo":    ["vix","vvix"],
    "sentimiento": ["fg"],
    "posicion": ["pcr","skew"],
    "batalla":  ["sv5_turbulence"],
    "participacion": ["bsi","rotation"],
    "macro":    ["credit","yield_curve","dxy"],
}

print("═══ FAMILIAS — ¿Agrupar mejora la predicción de dirección? ═══\n")
print(f"{'Modelo':<40} {'IC(dir)':>8}")

# 1. Individual stations (all 11)
for code in ALL:
    r = ic(df.get(f"{code}_pbull"), y_dir)
    if not np.isnan(r): print(f"  Individual: {code:<25} {r:>+8.4f}")

# 2. Family average
for fam_name, members in FAMILIAS.items():
    cols = [f"{m}_pbull" for m in members if f"{m}_pbull" in df.columns]
    if cols:
        df[f"fam_{fam_name}"] = df[cols].mean(axis=1, skipna=True)
        r = ic(df[f"fam_{fam_name}"], y_dir)
        print(f"  Familia: {fam_name:<25} {r:>+8.4f}")

# 3. ALL families averaged (global p_bull)
all_cols = [f"{c}_pbull" for c in ALL if f"{c}_pbull" in df.columns]
df["global_pbull"] = df[all_cols].mean(axis=1, skipna=True)
r = ic(df["global_pbull"], y_dir)
print(f"  GLOBAL (11 estaciones):             {r:>+8.4f}")

# 4. Family weighted by IC
print("\n═══ ¿La familia de mayor IC individual mejora? ═══")
# Pick the strongest family
best_fam = None; best_ic = -1
for fam_name in FAMILIAS:
    r = ic(df.get(f"fam_{fam_name}"), y_dir)
    if not np.isnan(r) and abs(r) > best_ic:
        best_ic = abs(r); best_fam = fam_name
print(f"  Mejor familia: {best_fam} (IC={best_ic:+.4f})")

# 5. Avg of top 3 stations vs avg of all
top3 = ["fg","vix","bsi"]
df["top3_pbull"] = df[[f"{c}_pbull" for c in top3]].mean(axis=1, skipna=True)
r_top3 = ic(df["top3_pbull"], y_dir)
r_all = ic(df["global_pbull"], y_dir)
print(f"\n  Top 3 (FG+VIX+BSI):    IC={r_top3:+.4f}")
print(f"  11 estaciones:         IC={r_all:+.4f}")
print(f"  Diferencia:            {abs(r_top3/r_all):.1f}×")