import json, numpy as np, pandas as pd
from datetime import timedelta
from scipy.stats import spearmanr

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import STATION_CONFIG

RULES = "/root/botero-trade/backend/modules/entry_decision/domain/rules"

# Load VIX fact store (representative station)
with open(f"{RULES}/vix_fact_store.json") as f:
    vix_fs = json.load(f)["states"]

# N distribution per state
all_n_zz25 = []; all_n_zz50 = []; all_n_zz75 = []
for sk, st in vix_fs.items():
    zz25 = st.get("zz25", {}); zz50 = st.get("zz50", {}); zz75 = st.get("zz75", {})
    n25 = zz25.get("n_raw", 0); n50 = zz50.get("n_raw", 0); n75 = zz75.get("n_raw", 0)
    all_n_zz25.append(n25); all_n_zz50.append(n50); all_n_zz75.append(n75)

print("═══ Distribución de N por escala (VIX) ═══\n")
for scale, data in [("zz25", all_n_zz25), ("zz50", all_n_zz50), ("zz75", all_n_zz75)]:
    d = np.array(data)
    print(f"{scale}: total={len(d)} estados, N medio={d.mean():.0f}, mediana={np.median(d):.0f}")
    print(f"  N<3:  {np.sum(d<3):>4} ({np.mean(d<3)*100:.0f}%)  N<10: {np.sum(d<10):>4} ({np.mean(d<10)*100:.0f}%)  N>=30: {np.sum(d>=30):>4} ({np.mean(d>=30)*100:.0f}%)")
    print()

# EXTREME STATES: cascade behavior
store = TimescaleDataStore()
repo = ZigzagLegRepository(store)
legs25 = repo.get_confirmed_legs("SPY","zz25")
legs50 = repo.get_confirmed_legs("SPY","zz50")
legs75 = repo.get_confirmed_legs("SPY","zz75")
starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)
starts75 = set(pd.to_datetime(l.start_timestamp).date() for l in legs75)

df25 = pd.DataFrame([{"start_timestamp":l.start_timestamp,"start_type":l.start_type,"prev_leg_return":l.prev_leg_return} for l in legs25])
df25 = df25.dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["cascade_50"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in starts50 for i in range(-3,4))))
df25["cascade_75"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in starts75 for i in range(-3,4))))

# VIX data
s = store.load_bars("VIX","1d")["close"].copy()
s.index = [d.date() if hasattr(d,'date') else d for d in pd.to_datetime(s.index)]
vel = s.diff(3); std2=s.rolling(2).std(); std10=s.rolling(10).std()
vol=(std2/std10).fillna(1.0)

from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter

adapter = VIXLookupAdapter()

store.close()

# Classify each pivot's VIX state + N
state_ns = []
for _, row in df25.iterrows():
    pd_ = row["pivot_date"]
    idx_v = s.index[s.index <= pd_]; idx_vel = vel.index[vel.index <= pd_]; idx_vol = vol.index[vol.index <= pd_]
    v_val = float(s.iloc[len(idx_v)-1]) if len(idx_v)>0 else np.nan
    v_vel = float(vel.iloc[len(idx_vel)-1]) if len(idx_vel)>0 else 0.0
    v_vol = float(vol.iloc[len(idx_vol)-1]) if len(idx_vol)>0 else 1.0
    try:
        res = adapter.lookup_vix_guidance(val=v_val, d3_speed=v_vel, vol_norm=v_vol, vol_d3=0.0)
        sk = res.state_key
        n = vix_fs.get(sk, {}).get("zz25", {}).get("n_raw", 0)
        state_ns.append(n)
    except: state_ns.append(np.nan)

df25["n_zz25"] = state_ns

print("═══ EXTREMOS: cascade rate por N ═══\n")
for label, mask in [("N<3 (muy extremo)", df25["n_zz25"]<3), ("3≤N<10 (extremo)", (df25["n_zz25"]>=3)&(df25["n_zz25"]<10)), ("10≤N<30 (normal)", (df25["n_zz25"]>=10)&(df25["n_zz25"]<30)), ("N≥30 (robusto)", df25["n_zz25"]>=30)]:
    if mask.sum()<3: continue
    c50 = df25.loc[mask,"cascade_50"].mean()
    c75 = df25.loc[mask,"cascade_75"].mean()
    print(f"  {label:<25}: cascade_50={c50:.1%}  cascade_75={c75:.1%}  N pivotes={mask.sum()}")

# EXTREME → MORE EXTREME transition
print(f"\n═══ P(extremo → más extremo): ¿el estado extremo cascada o revierte? ═══")
extreme = df25["n_zz25"] < 10
normal = df25["n_zz25"] >= 10
print(f"  Estados N<10 → cascade_50: {df25.loc[extreme,'cascade_50'].mean():.1%}")
print(f"  Estados N≥10 → cascade_50: {df25.loc[normal,'cascade_50'].mean():.1%}")
if extreme.sum()>30 and normal.sum()>30:
    _, pval = spearmanr(extreme.astype(float).values, df25["cascade_50"].values)
    print(f"  ¿Diferencia significativa? p={pval:.4f}")