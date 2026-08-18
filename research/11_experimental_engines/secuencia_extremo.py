import json, numpy as np, pandas as pd
from datetime import timedelta
from scipy.stats import spearmanr, fisher_exact

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
df25["cascade_50"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in starts50 for i in range(-3,4))))
df25["cascade_75"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in starts75 for i in range(-3,4))))
df25["next_type"] = df25["start_type"].shift(-1)
df25["next2_type"] = df25["start_type"].shift(-2)
# "continue" = next2 leg goes SAME direction as current leg (MIN->MIN or MAX->MAX after the breath)
df25["trend_continues_after_breath"] = (df25["next2_type"] == df25["start_type"]).astype(float)

s = store.load_bars("VIX","1d")["close"].copy()
s.index = [d.date() if hasattr(d,'date') else d for d in pd.to_datetime(s.index)]
vel = s.diff(3); std2=s.rolling(2).std(); std10=s.rolling(10).std()
vol=(std2/std10).fillna(1.0)
store.close()

adapter = VIXLookupAdapter()

state_ns = []; state_vels = []
for _, row in df25.iterrows():
    pd_ = row["pivot_date"]
    idx_v = s.index[s.index <= pd_]; idx_vel = vel.index[vel.index <= pd_]; idx_vol = vol.index[vol.index <= pd_]
    v_val = float(s.iloc[len(idx_v)-1]) if len(idx_v)>0 else np.nan
    v_vel = float(vel.iloc[len(idx_vel)-1]) if len(idx_vel)>0 else 0.0
    v_vol = float(vol.iloc[len(idx_vol)-1]) if len(idx_vol)>0 else 1.0
    try:
        res = adapter.lookup_vix_guidance(val=v_val, d3_speed=v_vel, vol_norm=v_vol, vol_d3=0.0)
        n = vix_fs.get(res.state_key, {}).get("zz25", {}).get("n_raw", 0)
        state_ns.append(n)
    except:
        state_ns.append(np.nan)
    state_vels.append(v_vel)

df25["n_zz25"] = state_ns
df25["vix_vel"] = state_vels

# Extreme state (N<10)
extreme = df25["n_zz25"] < 10
# Extreme velocity (|vel| > P90)
vel_p90 = df25["vix_vel"].abs().quantile(0.90)
extreme_vel = df25["vix_vel"].abs() > vel_p90

print("═══ SECUENCIA POST-EXTREMO: ¿continúa o revierte tras el breath? ═══\n")
print(f"Velocidad |vel| P90 = {vel_p90:.2f}\n")

# Overall
print("── Todos los pivotes ──")
print(f"  cascade_50 inmediato:      {df25['cascade_50'].mean():.1%}")
print(f"  continúa tras breath (2 leg): {df25['trend_continues_after_breath'].mean():.1%}")

# Split by extreme state
print(f"\n── Estado EXTREMO (N<10) ──")
m = extreme & df25["trend_continues_after_breath"].notna()
print(f"  N={m.sum()}")
print(f"  cascade_50 inmediato:      {df25.loc[m,'cascade_50'].mean():.1%}")
print(f"  continúa tras breath:      {df25.loc[m,'trend_continues_after_breath'].mean():.1%}")

# The KEY: extreme state + extreme velocity
print(f"\n── Estado EXTREMO + VELOCIDAD EXTREMA ──")
m2 = extreme & extreme_vel & df25["trend_continues_after_breath"].notna()
print(f"  N={m2.sum()}")
print(f"  cascade_50 inmediato:      {df25.loc[m2,'cascade_50'].mean():.1%}")
print(f"  continúa tras breath:      {df25.loc[m2,'trend_continues_after_breath'].mean():.1%}")

# Extreme state + LOW velocity (exhausted?)
print(f"\n── Estado EXTREMO + velocidad BAJA (¿agotado?) ──")
low_vel = df25["vix_vel"].abs() < df25["vix_vel"].abs().quantile(0.33)
m3 = extreme & low_vel & df25["trend_continues_after_breath"].notna()
print(f"  N={m3.sum()}")
print(f"  cascade_50 inmediato:      {df25.loc[m3,'cascade_50'].mean():.1%}")
print(f"  continúa tras breath:      {df25.loc[m3,'trend_continues_after_breath'].mean():.1%}")

# VELOCITY sign (accelerating up vs down)
print(f"\n── VELOCIDAD DIRECCIÓN en estado extremo ──")
vel_up = df25["vix_vel"] > 0
for label, vm in [("velocidad UP (subiendo)", vel_up), ("velocidad DOWN (cayendo)", ~vel_up)]:
    mm = extreme & vm & df25["trend_continues_after_breath"].notna()
    print(f"  {label}: N={mm.sum()}, continúa tras breath={df25.loc[mm,'trend_continues_after_breath'].mean():.1%}")