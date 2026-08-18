import json, numpy as np, pandas as pd
from datetime import timedelta

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter

RULES_D = "/root/botero-trade/backend/modules/entry_decision/domain/rules"
with open(f"{RULES_D}/vix_fact_store.json") as f: vix_fs = json.load(f)["states"]

store = TimescaleDataStore(); repo = ZigzagLegRepository(store)
legs25 = repo.get_confirmed_legs("SPY","zz25"); legs50 = repo.get_confirmed_legs("SPY","zz50"); legs75 = repo.get_confirmed_legs("SPY","zz75")
s50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50); s75 = set(pd.to_datetime(l.start_timestamp).date() for l in legs75)

df25 = pd.DataFrame([{"start_timestamp":l.start_timestamp,"start_type":l.start_type,"prev_leg_return":l.prev_leg_return} for l in legs25])
df25 = df25.dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["B"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in s50 for i in range(-3,4))))
df25["C"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in s75 for i in range(-3,4))))

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
        sk = res.state_key; d1 = sk.split("__")[0]
        n = vix_fs.get(sk,{}).get("zz25",{}).get("n_raw",0)
        rows.append({"N":n,"vel":ve,"d1":d1,"B":row["B"],"C":row["C"]})
    except: pass

df = pd.DataFrame(rows)

# A_extreme = N<10
# Split by D1: HIGH extreme (crisis) vs LOW extreme (complacency)
HIGH_BINS = ["CRISIS_SPIKE","ELEVATED_PANIC"]
LOW_BINS  = ["DEEP_COMPLACENCY","LOW_VOL"]
A_high = (df["N"]<10) & df["d1"].isin(HIGH_BINS)
A_low  = (df["N"]<10) & df["d1"].isin(LOW_BINS)

# Velocity direction
vel_up = df["vel"] > 0; vel_down = df["vel"] < 0

def prob(mask, target):
    m = mask & target.notna()
    return target[m].mean(), m.sum()

print("═"*65)
print("  ESTADÍSTICA CONDICIONAL — DOS EXTREMOS × DOS VELOCIDADES")
print("═"*65)

# HIGH EXTREME (crisis)
print(f"\n── EXTREMO ALTO (CRISIS: CRISIS_SPIKE, ELEVATED_PANIC) ──")
for label, mask in [("cualquier velocidad", A_high), ("VIX SUBIENDO (pánico acelerando)", A_high & vel_up), ("VIX BAJANDO (pánico resolviéndose)", A_high & vel_down)]:
    pb, nb = prob(mask, df["B"]); pc, nc = prob(mask, df["C"])
    print(f"  {label:<40}: P(B)={pb:.0%} (N={nb})  P(C)={pc:.0%} (N={nc})")

# Cascade chain for high extreme
print(f"\n  Cadena HIGH extremo:")
AB_high = A_high & (df["B"]==1)
pc_ab_high, _ = prob(AB_high, df["C"])
print(f"    P(B)={prob(A_high,df['B'])[0]:.0%} × P(C|B)={pc_ab_high:.0%} = {prob(A_high,df['B'])[0]*pc_ab_high:.0%}")

# LOW EXTREME (complacency)
print(f"\n── EXTREMO BAJO (COMPLACENCIA: DEEP_COMPLACENCY, LOW_VOL) ──")
for label, mask in [("cualquier velocidad", A_low), ("VIX SUBIENDO (miedo volviendo)", A_low & vel_up), ("VIX BAJANDO (complacencia profundizando)", A_low & vel_down)]:
    pb, nb = prob(mask, df["B"]); pc, nc = prob(mask, df["C"])
    print(f"  {label:<40}: P(B)={pb:.0%} (N={nb})  P(C)={pc:.0%} (N={nc})")

AB_low = A_low & (df["B"]==1); pc_ab_low, _ = prob(AB_low, df["C"])
print(f"\n  Cadena LOW extremo:")
print(f"    P(B)={prob(A_low,df['B'])[0]:.0%} × P(C|B)={pc_ab_low:.0%} = {prob(A_low,df['B'])[0]*pc_ab_low:.0%}")

# BASELINE
print(f"\n── LÍNEA BASE ──")
print(f"  P(B) = cascade_50: {prob(pd.Series(True,index=df.index), df['B'])[0]:.0%}")
print(f"  P(C) = cascade_75: {prob(pd.Series(True,index=df.index), df['C'])[0]:.0%}")

# DECISIONS
print(f"\n═"*65)
print(f"  ¿QUÉ HACER? — Tablero de decisión")
print(f"═"*65)
print(f"  EXTREMO ALTO + VIX↑ (pánico acelerando)  → P(B)={prob(A_high&vel_up,df['B'])[0]:.0%}  → MANTENER/AGREGAR")
print(f"  EXTREMO ALTO + VIX↓ (pánico resolviendo) → P(B)={prob(A_high&vel_down,df['B'])[0]:.0%}  → MANTENER (reversión posible)")
print(f"  EXTREMO BAJO + VIX↑ (miedo volviendo)    → P(B)={prob(A_low&vel_up,df['B'])[0]:.0%}  → {'MANTENER' if prob(A_low&vel_up,df['B'])[0]>0.55 else 'REDUCIR'}")
print(f"  EXTREMO BAJO + VIX↓ (complacencia deep)  → P(B)={prob(A_low&vel_down,df['B'])[0]:.0%}  → {'MANTENER' if prob(A_low&vel_down,df['B'])[0]>0.55 else 'REDUCIR'}")