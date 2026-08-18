import json, numpy as np, pandas as pd
from datetime import timedelta

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.scripts._lib.decay_check_cascade_conviction import STATION_CONFIG

ALL = list(STATION_CONFIG.keys())

store = TimescaleDataStore(); repo = ZigzagLegRepository(store)

legs25 = repo.get_confirmed_legs("SPY","zz25"); legs50 = repo.get_confirmed_legs("SPY","zz50"); legs75 = repo.get_confirmed_legs("SPY","zz75")
s50 = {pd.to_datetime(l.start_timestamp).date() for l in legs50}
s75 = {pd.to_datetime(l.start_timestamp).date() for l in legs75}

df25 = pd.DataFrame([{"start_timestamp":l.start_timestamp,"start_type":l.start_type,"prev_leg_return":l.prev_leg_return} for l in legs25])
df25 = df25.dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["c50"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in s50 for i in range(-3,4))))
df25["c75"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in s75 for i in range(-3,4))))
df25["next_type"] = df25["start_type"].shift(-1)
df25["next_bear"] = (df25["next_type"]=="MIN").astype(float)

# Load D3 (volatility) for ALL stations
all_d3 = {}
for code, cfg in STATION_CONFIG.items():
    s = store.load_bars(cfg["ticker"],"1d")["close"].copy()
    s.index = [d.date() if hasattr(d,'date') else d for d in pd.to_datetime(s.index)]
    std2 = s.rolling(2).std(); std10 = s.rolling(10).std()
    d3 = (std2/std10).fillna(1.0)
    all_d3[code] = d3

store.close()

# Lookup D3 at each pivot for every station
obs = []
for _, row in df25.iterrows():
    pd_ = row["pivot_date"]
    rec = {"c50":row["c50"],"c75":row["c75"],"bear":row["next_bear"]}
    for code, d3_series in all_d3.items():
        idx = d3_series.index[d3_series.index <= pd_]
        if len(idx) > 0:
            rec[f"{code}_d3"] = float(d3_series.iloc[len(idx)-1])
    # Drop if too many NaN
    if sum(1 for v in rec.values() if pd.isna(v)) < 5:
        obs.append(rec)

df = pd.DataFrame(obs)

print("═"*80)
print("  D3 (VOLATILIDAD) — ¿Qué significa en cada indicador?")
print("  Impacto en cascade_50, cascade_75, dirección")
print("═"*80)

for code in ALL:
    col = f"{code}_d3"
    if col not in df.columns: continue
    d3 = df[col].dropna()
    if len(d3) < 30: continue
    lo = d3 < d3.quantile(0.33)
    hi = d3 >= d3.quantile(0.67)
    
    lo_mask = pd.Series(False, index=df.index)
    hi_mask = pd.Series(False, index=df.index)
    lo_mask[d3.index[lo]] = True
    hi_mask[d3.index[hi]] = True
    
    c50_lo = df.loc[lo_mask,"c50"].mean() if lo_mask.sum()>10 else np.nan
    c50_hi = df.loc[hi_mask,"c50"].mean() if hi_mask.sum()>10 else np.nan
    c75_lo = df.loc[lo_mask,"c75"].mean() if lo_mask.sum()>10 else np.nan
    c75_hi = df.loc[hi_mask,"c75"].mean() if hi_mask.sum()>10 else np.nan
    b_lo = df.loc[lo_mask,"bear"].mean() if lo_mask.sum()>10 else np.nan
    b_hi = df.loc[hi_mask,"bear"].mean() if hi_mask.sum()>10 else np.nan
    
    gap_c50 = (c50_hi - c50_lo)*100 if not (np.isnan(c50_lo) or np.isnan(c50_hi)) else 0
    gap_dir = (b_hi - b_lo)*100 if not (np.isnan(b_lo) or np.isnan(b_hi)) else 0
    
    # Show only if meaningful gap
    marker = "★" if abs(gap_c50) > 5 or abs(gap_dir) > 5 else " "
    print(f"{marker} {code:<18}: D3↓(calma) c50={c50_lo:.0%} c75={c75_lo:.0%} bear={b_lo:.0%} | D3↑(caos) c50={c50_hi:.0%} c75={c75_hi:.0%} bear={b_hi:.0%} | Δc50={gap_c50:+.0f}pp Δdir={gap_dir:+.0f}pp")

print("\n═"*80)
print("  INTERPRETACIÓN: ★ = D3 discrimina significativamente")
print("═"*80)
print("  D3↓ = volatilidad BAJA (indicador estable)")
print("  D3↑ = volatilidad ALTA (indicador caótico)")
print("  Δ positivo: caos → MÁS cascade / MÁS bear")
print("  Δ negativo: caos → MENOS cascade / MENOS bear")