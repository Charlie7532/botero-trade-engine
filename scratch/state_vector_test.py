import json, numpy as np, pandas as pd
from datetime import timedelta
from scipy.stats import spearmanr

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import STATION_CONFIG, d1_directional_vote

RULES = "/root/botero-trade/backend/modules/entry_decision/domain/rules"
GRUPO_A = ["vix","bsi","fg","credit","rotation"]

fact_stores = {}
for code in GRUPO_A:
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
# next leg direction
df25["next_type"] = df25["start_type"].shift(-1)
df25["next_bear"] = (df25["next_type"]=="MIN").astype(float)

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

obs = []
for idx, row in df25.iterrows():
    pd_ = row["pivot_date"]
    if pd_ not in date_features.index: continue
    feats = date_features.loc[pd_]
    rec = {"cascade_50":row["cascade_50"], "next_bear":row["next_bear"], "start_type":row["start_type"]}
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
                st = fact_stores[code].get(sk, {})
                zz25 = st.get("zz25", {})
                zk = st.get("zigzag_kinematic", {}).get("zz25", {})
                # FULL STATE probabilities
                rec[f"{code}_p_bull"] = zz25.get("p_bull")
                rec[f"{code}_p_bear"] = zz25.get("p_bear")
                rec[f"{code}_zk_pbull"] = zk.get("p_bull")
                rec[f"{code}_zk_pbear"] = zk.get("p_bear")
                rec[f"{code}_n"] = zz25.get("n_raw")
        except: continue
    mv=[v for v in votes.values()]
    rec["d1_bear"] = sum(1 for v in mv if v<0)/len(mv) if mv else np.nan
    obs.append(rec)

df = pd.DataFrame(obs)

def ic(a,b):
    a=np.asarray(a,dtype=float); b=np.asarray(b,dtype=float)
    m=~np.isnan(a)&~np.isnan(b)
    return spearmanr(a[m],b[m])[0] if m.sum()>=30 else np.nan

y_cascade = df["cascade_50"].values
y_dir = df["next_bear"].values

print("═══ D1-only vs ESTADO COMPLETO (D1×D2×D3) ═══\n")

# D1 vote aggregate
print(f"D1 vote agregado → cascade:  IC={ic(df['d1_bear'], y_cascade):+.4f}")

# Full state: aggregate p_bull (zz25 layer) and zigzag p_bull across stations
for layer in ["p_bull","zk_pbull","p_bear"]:
    cols = [f"{c}_{layer}" for c in GRUPO_A]
    # Mean of p_bull across available stations
    df[f"mean_{layer}"] = df[cols].mean(axis=1, skipna=True)
    print(f"Estado completo mean({layer}) → cascade: IC={ic(df[f'mean_{layer}'], y_cascade):+.4f}")
    print(f"Estado completo mean({layer}) → dirección: IC={ic(df[f'mean_{layer}'], y_dir):+.4f}")

# Direction: does p_bull predict next_bear?
print("\n═══ p_bull del estado → dirección del próximo leg ═══")
for code in GRUPO_A:
    r = ic(df[f"{code}_zk_pbull"], y_dir)
    print(f"  {code:<10}: IC(zk_p_bull → next_bear) = {r:+.4f}")

# KEY: does the full state (150 states) beat D1-only (6 states)?
print("\n═══ ¿El VECTOR completo supera a D1? ═══")
# D1 vote predicts direction
print(f"D1 vote → dirección:  IC={ic(df['d1_bear'], y_dir):+.4f}")
# Full state zk_pbull predicts direction
print(f"Estado completo (zk_pbull) → dirección: IC={ic(df['mean_zk_pbull'], y_dir):+.4f}")