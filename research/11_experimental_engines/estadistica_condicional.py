import json, numpy as np, pandas as pd
from datetime import timedelta

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter

RULES = "/root/botero-trade/backend/modules/entry_decision/domain/rules"
with open(f"{RULES}/vix_fact_store.json") as f:
    vix_fs = json.load(f)["states"]

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

# CASCADE labels
df25["B"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in starts50 for i in range(-3,4))))  # cascade_50
df25["C"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in starts75 for i in range(-3,4))))  # cascade_75

s = store.load_bars("VIX","1d")["close"].copy()
s.index = [d.date() if hasattr(d,'date') else d for d in pd.to_datetime(s.index)]
vel = s.diff(3); std2=s.rolling(2).std(); std10=s.rolling(10).std()
vol=(std2/std10).fillna(1.0)
store.close()

adapter = VIXLookupAdapter()

ns = []; vels = []
for _, row in df25.iterrows():
    pd_ = row["pivot_date"]
    iv = s.index[s.index <= pd_]; iv2 = vel.index[vel.index <= pd_]; iv3 = vol.index[vol.index <= pd_]
    v_val = float(s.iloc[len(iv)-1]) if len(iv)>0 else np.nan
    v_vel = float(vel.iloc[len(iv2)-1]) if len(iv2)>0 else 0.0
    v_vol = float(vol.iloc[len(iv3)-1]) if len(iv3)>0 else 1.0
    try:
        res = adapter.lookup_vix_guidance(val=v_val, d3_speed=v_vel, vol_norm=v_vol, vol_d3=0.0)
        n = vix_fs.get(res.state_key, {}).get("zz25", {}).get("n_raw", 0)
        ns.append(n); vels.append(v_vel)
    except: ns.append(np.nan); vels.append(np.nan)

df25["N"] = ns; df25["vel"] = vels

# A: EXTREME STATE (N<10)
A = df25["N"] < 10
A_plus = A & (df25["vel"] > 0)  # velocity UP (VIX accelerating up = fear building)
A_minus = A & (df25["vel"] < 0)  # velocity DOWN (VIX dropping = fear resolving)

B = df25["B"]  # cascade_50
C = df25["C"]  # cascade_75

def prob(condition, target):
    m = condition & target.notna()
    return target[m].mean(), m.sum()

print("╔══════════════════════════════════════════════════════════════╗")
print("║  ESTADÍSTICA CONDICIONAL — Extremo → Cascade → Escala Mayor  ║")
print("╚══════════════════════════════════════════════════════════════╝\n")

# P(B|A): Dado extremo, ¿cascade_50?
p_ba, n_ba = prob(A, B)
p_ba_plus, n_ba_plus = prob(A_plus, B)
p_ba_minus, n_ba_minus = prob(A_minus, B)
print("── P(B | A): Dado estado EXTREMO, ¿cascade_50? ──")
print(f"  P(B|A)     = {p_ba:.1%}  (N={n_ba})  [extremo, cualquier velocidad]")
print(f"  P(B|A+)    = {p_ba_plus:.1%}  (N={n_ba_plus})  [extremo + VIX SUBIENDO]")
print(f"  P(B|A-)    = {p_ba_minus:.1%}  (N={n_ba_minus})  [extremo + VIX BAJANDO]")

# P(C|A,B): Dado extremo y cascade_50, ¿cascade_75?
AB = A & (B == 1); AnotB = A & (B == 0)
p_c_ab, n_c_ab = prob(AB, C)
p_c_anotb, n_c_anotb = prob(AnotB, C)
print(f"\n── P(C | A, B): Dado extremo Y cascade_50 → ¿cascade_75? ──")
print(f"  P(C|A,B=1) = {p_c_ab:.1%}  (N={n_c_ab})  [cascadeó a zz50, ¿llega a zz75?]")
print(f"  P(C|A,B=0) = {p_c_anotb:.1%}  (N={n_c_anotb})  [NO cascadeó, ¿llega a zz75?]")

# P(C|A+): Dado extremo + vel UP, ¿cascade_75?
p_c_aplus, n_c_aplus = prob(A_plus, C)
p_c_aminus, n_c_aminus = prob(A_minus, C)
print(f"\n── P(C | A): Dado estado EXTREMO → ¿cascade_75? ──")
print(f"  P(C|A+)    = {p_c_aplus:.1%}  (N={n_c_aplus})  [extremo + VIX SUBIENDO]")
print(f"  P(C|A-)    = {p_c_aminus:.1%}  (N={n_c_aminus})  [extremo + VIX BAJANDO]")

# FULL CHAIN
print(f"\n── CADENA COMPLETA: P(B|A) × P(C|A,B) ──")
p_chain_plus = p_ba_plus * p_c_aplus
p_chain_minus = p_ba_minus * p_c_aminus
print(f"  A+ → B+ → C+: {p_ba_plus:.1%} × {p_c_aplus:.1%} = {p_chain_plus:.1%}  [extremo vel UP → cascade → zz75]")
print(f"  A- → B+ → C+: {p_ba_minus:.1%} × {p_c_aminus:.1%} = {p_chain_minus:.1%}  [extremo vel DOWN → cascade → zz75]")

# BASELINE
p_b, n_b = prob(pd.Series(True, index=df25.index), B)
p_c, n_c = prob(pd.Series(True, index=df25.index), C)
print(f"\n── LÍNEA BASE (todos los pivotes) ──")
print(f"  P(B) = cascade_50: {p_b:.1%}")
print(f"  P(C) = cascade_75: {p_c:.1%}")

# DECISIONES
print(f"\n╔══════════════════════════════════════════════════════════════╗")
print(f"║  ¿QUÉ HACER? — Reglas de decisión basadas en probabilidad    ║")
print(f"╚══════════════════════════════════════════════════════════════╝")
print(f"  A+ (extremo + VIX SUBIENDO):")
print(f"    P(cascade_50|A+) = {p_ba_plus:.0%}  → {'MANTENER / AGREGAR posición' if p_ba_plus>0.65 else 'REDUCIR'}")
print(f"    P(cascade_75|A+) = {p_c_aplus:.0%}  → {'tendencia de fondo ALCISTA' if p_c_aplus>0.5 else 'tendencia débil'}")
print(f"  A- (extremo + VIX BAJANDO):")
print(f"    P(cascade_50|A-) = {p_ba_minus:.0%}  → {'MANTENER / AGREGAR posición' if p_ba_minus>0.65 else 'REDUCIR'}")
print(f"    P(cascade_75|A-) = {p_c_aminus:.0%}  → {'tendencia de fondo ALCISTA' if p_c_aminus>0.5 else 'tendencia débil'}")