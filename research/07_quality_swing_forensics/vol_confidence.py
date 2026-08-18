import json, numpy as np, pandas as pd
from datetime import timedelta
from scipy.stats import spearmanr

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import STATION_CONFIG

RULES = "/root/botero-trade/backend/modules/entry_decision/domain/rules"
ALL = list(STATION_CONFIG.keys())

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
df25["next_type"] = df25["start_type"].shift(-1)
df25["next_bear"] = (df25["next_type"]=="MIN").astype(float)

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
    rec = {"next_bear":row["next_bear"]}
    for code in ALL:
        val=feats.get(f"{code}_val"); vel=feats.get(f"{code}_vel",0.0); vol=feats.get(f"{code}_vol",1.0)
        if pd.isna(val): continue
        if pd.isna(vel): vel=0.0
        if pd.isna(vol): vol=1.0
        try:
            method = STATION_CONFIG[code]["method"]
            res = getattr(adapters[code], method)(val=float(val), d3_speed=float(vel), vol_norm=float(vol), vol_d3=float(vol))
            if res and res.state_key:
                zk = fact_stores[code].get(res.state_key, {}).get("zigzag_kinematic", {}).get("zz25", {})
                rec[f"{code}_pbull"] = zk.get("p_bull")
                rec[f"{code}_vol"] = float(vol)
        except: continue
    obs.append(rec)

df = pd.DataFrame(obs)
y_dir = df["next_bear"].values

def ic(a,b):
    a=np.asarray(a,dtype=float); b=np.asarray(b,dtype=float)
    m=~np.isnan(a)&~np.isnan(b)
    return spearmanr(a[m],b[m])[0] if m.sum()>=30 else np.nan

pbull_cols = [f"{c}_pbull" for c in ALL if f"{c}_pbull" in df.columns]
vol_cols = [f"{c}_vol" for c in ALL if f"{c}_vol" in df.columns]
df["global_pbull"] = df[pbull_cols].mean(axis=1, skipna=True)
df["global_vol"] = df[vol_cols].mean(axis=1, skipna=True)

print("═══ D3 (volatilidad) como MODULADOR DE CONFIANZA ═══\n")
print(f"Baseline p_bull → dirección: IC={ic(df['global_pbull'], y_dir):+.4f}\n")

# Split by D3 terciles: low vol (stable) vs high vol (chaotic)
vol_lo = df["global_vol"] < df["global_vol"].quantile(0.33)
vol_md = (df["global_vol"] >= df["global_vol"].quantile(0.33)) & (df["global_vol"] < df["global_vol"].quantile(0.67))
vol_hi = df["global_vol"] >= df["global_vol"].quantile(0.67)

for label, mask in [("D3 BAJA (estable)", vol_lo), ("D3 MEDIA", vol_md), ("D3 ALTA (caótica)", vol_hi)]:
    r = ic(df.loc[mask, "global_pbull"], y_dir[mask])
    print(f"  {label:<20}: IC={r:+.4f}  N={mask.sum()}")

# Bootstrap the difference
rng = np.random.default_rng(42)
diffs = []
for _ in range(2000):
    idx_lo = rng.choice(vol_lo[vol_lo].index, size=vol_lo.sum(), replace=True)
    idx_hi = rng.choice(vol_hi[vol_hi].index, size=vol_hi.sum(), replace=True)
    r_lo = ic(df.loc[idx_lo,"global_pbull"], y_dir[idx_lo])
    r_hi = ic(df.loc[idx_hi,"global_pbull"], y_dir[idx_hi])
    if not np.isnan(r_lo) and not np.isnan(r_hi):
        diffs.append(abs(r_lo) - abs(r_hi))  # positive = low vol better

diffs = np.array(diffs)
ci = np.percentile(diffs, [2.5, 97.5])
print(f"\nBootstrap Δ|IC| (baja vol - alta vol): CI95 [{ci[0]:+.4f}, {ci[1]:+.4f}]")
print(f"Prob(|IC_baja_vol| > |IC_alta_vol|): {(diffs>0).mean():.0%}")
print("→ Señal MÁS confiable con volatilidad BAJA (estable)" if np.mean(diffs)>0 else "→ Señal MÁS confiable con volatilidad ALTA (caótica)")