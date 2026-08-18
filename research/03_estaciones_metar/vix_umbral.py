import numpy as np, pandas as pd
from datetime import timedelta

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

store = TimescaleDataStore(); repo = ZigzagLegRepository(store)
legs25 = repo.get_confirmed_legs("SPY","zz25"); legs50 = repo.get_confirmed_legs("SPY","zz50"); legs75 = repo.get_confirmed_legs("SPY","zz75")
s50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50); s75 = set(pd.to_datetime(l.start_timestamp).date() for l in legs75)

df25 = pd.DataFrame([{"start_timestamp":l.start_timestamp,"start_type":l.start_type,"prev_leg_return":l.prev_leg_return} for l in legs25])
df25 = df25.dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["c50"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in s50 for i in range(-3,4))))
df25["c75"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in s75 for i in range(-3,4))))
# Forward return after pivot (for rebound magnitude)
df25["next_type"] = df25["start_type"].shift(-1)

vix = store.load_bars("VIX","1d")["close"].copy()
vix.index = [d.date() if hasattr(d,'date') else d for d in pd.to_datetime(vix.index)]
vel = vix.diff(3)
store.close()

rows = []
for _, row in df25.iterrows():
    pd_ = row["pivot_date"]
    iv=vix.index[vix.index<=pd_]; i2=vel.index[vel.index<=pd_]
    vv=float(vix.iloc[len(iv)-1]) if len(iv)>0 else np.nan
    ve=float(vel.iloc[len(i2)-1]) if len(i2)>0 else 0.0
    rows.append({"vix":vv,"vel":ve,"c50":row["c50"],"c75":row["c75"],"ptype":row["start_type"]})

df = pd.DataFrame(rows).dropna(subset=["vix"])

vel_up = df["vel"] > 0
vel_down = df["vel"] < 0

def prob(mask, t):
    m = mask & t.notna()
    return t[m].mean(), m.sum()

print("="*70)
print("  VIX EXTREMO: ¿cuándo entrar con todo? — Test de hipótesis")
print("="*70)
print(f"  Baseline: P(c50)={prob(pd.Series(True,index=df.index),df['c50'])[0]:.0%}  P(c75)={prob(pd.Series(True,index=df.index),df['c75'])[0]:.0%}\n")

for threshold in [28, 30, 32, 34, 36, 40]:
    extreme = df["vix"] >= threshold
    n_ext = extreme.sum()
    if n_ext < 3: continue
    up = extreme & vel_up
    down = extreme & vel_down
    p_up_c50, n_up = prob(up, df["c50"]); p_up_c75, _ = prob(up, df["c75"])
    p_down_c50, n_down = prob(down, df["c50"]); p_down_c75, _ = prob(down, df["c75"])
    print(f"── VIX >= {threshold} (N={n_ext}) ──")
    print(f"  VIX ↑ (acelerando):  P(c50)={p_up_c50:.0%}  P(c75)={p_up_c75:.0%}  (N={n_up})")
    print(f"  VIX ↓ (revirtiéndose): P(c50)={p_down_c50:.0%}  P(c75)={p_down_c75:.0%}  (N={n_down})")
    print()

# The hypothesis: VIX falling from extreme = rebound reliable
# Also check: does the NEXT leg direction depend on velocity at extreme?
print("="*70)
print("  DIRECCIÓN del próximo leg en extremo (¿rebota o sigue cayendo?)")
print("="*70)
df["next_bear"] = (df["ptype"]=="MIN").astype(float)
for threshold in [30, 32, 34, 36, 40]:
    extreme = df["vix"] >= threshold
    if extreme.sum() < 3: continue
    up = extreme & vel_up; down = extreme & vel_down
    pb_up, nu = prob(up, df["next_bear"]); pb_down, nd = prob(down, df["next_bear"])
    print(f"  VIX>={threshold}:  VIX↑ → %bear={pb_up:.0%} (N={nu}) | VIX↓ → %bear={pb_down:.0%} (N={nd})")