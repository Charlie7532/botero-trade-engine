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
df25["cascade_50"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in starts50 for i in range(-3,4))))
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
    rec = {"cascade_50":row["cascade_50"], "next_bear":row["next_bear"]}
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
                rec[f"{code}_vel"] = float(vel)
                rec[f"{code}_vol"] = float(vol)
        except: continue
    obs.append(rec)

df = pd.DataFrame(obs)
y_dir = df["next_bear"].values

def ic(a,b):
    a=np.asarray(a,dtype=float); b=np.asarray(b,dtype=float)
    m=~np.isnan(a)&~np.isnan(b)
    return spearmanr(a[m],b[m])[0] if m.sum()>=30 else np.nan

# Global p_bull (static)
pbull_cols = [f"{c}_pbull" for c in ALL if f"{c}_pbull" in df.columns]
df["global_pbull"] = df[pbull_cols].mean(axis=1, skipna=True)

# Global velocity (z-scored per station, then averaged)
vel_cols = [f"{c}_vel" for c in ALL if f"{c}_vel" in df.columns]
vel_df = df[vel_cols]
# z-score each station's velocity
vel_z = (vel_df - vel_df.mean()) / vel_df.std()
df["global_vel_z"] = vel_z.mean(axis=1, skipna=True)

print("═══ AJUSTE DE p_bull POR VELOCIDAD ═══\n")
print(f"Baseline (p_bull estático) → dirección: IC={ic(df['global_pbull'], y_dir):+.4f}")
print(f"Velocidad sola → dirección:         IC={ic(df['global_vel_z'], y_dir):+.4f}")

# Grid search w: p_bull_adj = p_bull + w * vel_z  (signo empírico, el dato decide)
print(f"\n{'w':>6} {'IC ajustado':>12} {'Δ vs baseline':>14}")
results = []
for w in np.arange(-0.4, 0.41, 0.05):
    adj = df["global_pbull"] + w * df["global_vel_z"]
    ic_adj = ic(adj, y_dir)
    ic_base = ic(df["global_pbull"], y_dir)
    results.append((w, ic_adj))
    print(f"{w:>+6.2f} {ic_adj:>+12.4f} {ic_adj-ic_base:>+14.4f}")

# Best w
results.sort(key=lambda x: abs(x[1]), reverse=True)
best_w, best_ic = results[0]
print(f"\nMejor w = {best_w:+.2f} → IC = {best_ic:+.4f}")

# Sign interpretation
print(f"\n── Interpretación del signo de w ──")
print(f"w > 0: velocidad empuja p_bull EN su dirección (velocidad ↑ → más alcista)")
print(f"w < 0: velocidad empuja p_bull EN CONTRA (velocidad ↑ → más bajista)")
print(f"El dato dice w={best_w:+.2f}")