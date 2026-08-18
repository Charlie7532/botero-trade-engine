import json, numpy as np, pandas as pd
from datetime import timedelta

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter

RULES = "/root/botero-trade/backend/modules/entry_decision/domain/rules"
with open(f"{RULES}/vix_fact_store.json") as f: vix_fs = json.load(f)["states"]

store = TimescaleDataStore(); repo = ZigzagLegRepository(store)
legs25 = repo.get_confirmed_legs("SPY","zz25"); legs50 = repo.get_confirmed_legs("SPY","zz50"); legs75 = repo.get_confirmed_legs("SPY","zz75")
s50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50); s75 = set(pd.to_datetime(l.start_timestamp).date() for l in legs75)

df25 = pd.DataFrame([{"start_timestamp":l.start_timestamp,"start_type":l.start_type,"prev_leg_return":l.prev_leg_return} for l in legs25])
df25 = df25.dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["c50"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in s50 for i in range(-3,4))))
df25["c75"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in s75 for i in range(-3,4))))
df25["next_type"] = df25["start_type"].shift(-1)
df25["next_bear"] = (df25["next_type"]=="MIN").astype(float)

vix = store.load_bars("VIX","1d")["close"].copy()
vix.index = [d.date() if hasattr(d,'date') else d for d in pd.to_datetime(vix.index)]
vel = vix.diff(3); std2=vix.rolling(2).std(); std10=vix.rolling(10).std(); vol=(std2/std10).fillna(1.0)
store.close()

adapter = VIXLookupAdapter()

rows = []
for _, row in df25.iterrows():
    pd_ = row["pivot_date"]
    iv=vix.index[vix.index<=pd_]; i2=vel.index[vel.index<=pd_]; i3=vol.index[vol.index<=pd_]
    vv=float(vix.iloc[len(iv)-1]) if len(iv)>0 else np.nan
    ve=float(vel.iloc[len(i2)-1]) if len(i2)>0 else 0.0
    vo=float(vol.iloc[len(i3)-1]) if len(i3)>0 else 1.0
    try:
        res = adapter.lookup_vix_guidance(val=vv, d3_speed=ve, vol_norm=vo, vol_d3=0.0)
        sk = res.state_key; parts = sk.split("__")
        d1, d2, d3 = parts[0], parts[1], parts[2]
        n = vix_fs.get(sk,{}).get("zz25",{}).get("n_raw",0)
        rows.append({"d1":d1,"d2":d2,"d3":d3,"N":n,"c50":row["c50"],"c75":row["c75"],"bear":row["next_bear"]})
    except: pass

df = pd.DataFrame(rows)

# D2 direction groups
def d2_dir(x):
    if "SPIKE" in x or "ACCELERATING" in x: return "UP (acelerando)"
    if "CRUSH" in x or "DECELERATING" in x: return "DOWN (desacelerando)"
    return "STABLE"
df["d2dir"] = df["d2"].apply(d2_dir)

# D3 phase groups
def d3_phase(x):
    if "SQUEEZE" in x or "COMPRESSION" in x: return "CONTRACCIÓN (calma)"
    if "PEAK_DECELERATION" in x: return "PICÓ_Y_CEDE"
    if "EXPANSION" in x: return "EXPANSIÓN (caos)"
    return "NEUTRAL"
df["d3phase"] = df["d3"].apply(d3_phase)

print("═"*70)
print("  ¿D3 agrega poder predictivo sobre D1+D2? (estados huérfanos N<10)")
print("═"*70)

# Focus on extreme HIGH (crisis) orphan states
crisis = df["d1"].isin(["CRISIS_SPIKE","ELEVATED_PANIC"])
orphan = crisis & (df["N"] < 10)

print(f"\n  Huérfanos en CRISIS (N<10): {orphan.sum()} episodios\n")

# D1+D2 only (velocity direction)
print("── SOLO D1+D2 (dirección de velocidad) ──")
for d2g in ["UP (acelerando)", "DOWN (desacelerando)"]:
    m = orphan & (df["d2dir"]==d2g)
    if m.sum() < 3: continue
    print(f"  {d2g:<20}: %bear={df.loc[m,'bear'].mean():.0%}  cascade_50={df.loc[m,'c50'].mean():.0%}  cascade_75={df.loc[m,'c75'].mean():.0%}  N={m.sum()}")

# D1+D2+D3 (full vector)
print("\n── VECTOR COMPLETO (D1+D2+D3) ──")
for d2g in ["UP (acelerando)", "DOWN (desacelerando)"]:
    for d3g in ["EXPANSIÓN (caos)", "PICÓ_Y_CEDE", "CONTRACCIÓN (calma)"]:
        m = orphan & (df["d2dir"]==d2g) & (df["d3phase"]==d3g)
        if m.sum() < 3: continue
        print(f"  {d2g:<20} + {d3g:<22}: %bear={df.loc[m,'bear'].mean():.0%}  c50={df.loc[m,'c50'].mean():.0%}  c75={df.loc[m,'c75'].mean():.0%}  N={m.sum()}")

# Does D3 differentiate within the same D2?
print("\n── ¿D3 diferencia dentro del MISMO D2? ──")
for d2g in ["UP (acelerando)", "DOWN (desacelerando)"]:
    base = orphan & (df["d2dir"]==d2g)
    if base.sum() < 6: continue
    base_bear = df.loc[base,"bear"].mean()
    print(f"\n  D2 = {d2g} (base %bear={base_bear:.0%}, N={base.sum()})")
    for d3g in ["EXPANSIÓN (caos)", "PICÓ_Y_CEDE", "CONTRACCIÓN (calma)"]:
        m = base & (df["d3phase"]==d3g)
        if m.sum() < 3: continue
        b = df.loc[m,"bear"].mean()
        delta = (b - base_bear)*100
        print(f"    D3={d3g:<22}: %bear={b:.0%} (Δ={delta:+.0f}pp, N={m.sum()})")