import numpy as np
import pandas as pd
from datetime import timedelta
from scipy.stats import spearmanr, chi2_contingency

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

legs25 = repo.get_confirmed_legs("SPY", "zz25")
legs50 = repo.get_confirmed_legs("SPY", "zz50")
starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)

df25 = pd.DataFrame([
    {"start_timestamp": l.start_timestamp, "start_type": l.start_type, "prev_leg_return": l.prev_leg_return}
    for l in legs25
]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["cascade_50"] = df25["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts50 for i in range(-3, 4)))
)

# Load SV5_TURBULENCE bars
turb = store.load_bars("SV5_TURBULENCE", "1d")
s = turb["close"].copy()
s.index = [d.date() if hasattr(d, 'date') else d for d in pd.to_datetime(s.index)]
s = s.sort_index()

# D1 = level, D2 = 3d delta, D3 = std2/std10
sv5_d1 = s
sv5_d2 = s.diff(3)
sv5_d3 = (s.rolling(2).std() / s.rolling(10).std()).replace([np.inf, -np.inf], np.nan).fillna(1.0)

# Attach to each pivot
def lookup_at(series, pivot_date):
    idx = series.index[series.index <= pivot_date]
    if len(idx) == 0:
        return np.nan
    return float(series.loc[idx[-1]])

d1_vals, d2_vals, d3_vals = [], [], []
for pd_ in df25["pivot_date"]:
    d1_vals.append(lookup_at(sv5_d1, pd_))
    d2_vals.append(lookup_at(sv5_d2, pd_))
    d3_vals.append(lookup_at(sv5_d3, pd_))

df25["sv5_d1"] = d1_vals
df25["sv5_d2"] = d2_vals
df25["sv5_d3"] = d3_vals

store.close()

y = df25["cascade_50"].values

print("═══ HIPÓTESIS 1: SV5T D1 (nivel) modula cascade rate ═══")
print("Turbulencia alta → ¿más cascade?")
# Bin by D1 percentiles
bins = pd.qcut(df25["sv5_d1"], 5, labels=["Q1","Q2","Q3","Q4","Q5"], duplicates="drop")
for q in ["Q1","Q2","Q3","Q4","Q5"]:
    mask = bins == q
    if mask.sum() > 0:
        rate = y[mask].mean()
        mean_turb = df25.loc[mask, "sv5_d1"].mean()
        print(f"  {q}: N={mask.sum():4d}  turb_mean={mean_turb:5.2f}  cascade_rate={rate:.3f}")

# Correlation
r, p = spearmanr(df25["sv5_d1"], y)
print(f"\n  Spearman ρ(SV5T_D1, cascade) = {r:+.4f} (p={p:.4f})")

print("\n═══ HIPÓTESIS 2: SV5T es BIMODAL (U-shaped) ═══")
print("Extremos (calma O pánico) → más cascade; centro → menos")
# Define extremes
p2 = df25["sv5_d1"].quantile(0.0228)
p16 = df25["sv5_d1"].quantile(0.1587)
p84 = df25["sv5_d1"].quantile(0.8413)
p98 = df25["sv5_d1"].quantile(0.9772)
calm = df25["sv5_d1"] < p2
low = (df25["sv5_d1"] >= p2) & (df25["sv5_d1"] < p16)
normal = (df25["sv5_d1"] >= p16) & (df25["sv5_d1"] < p84)
high = (df25["sv5_d1"] >= p84) & (df25["sv5_d1"] < p98)
extreme = df25["sv5_d1"] >= p98

for name, mask in [("CALM(<P2)", calm), ("LOW(P2-P16)", low), ("NORMAL", normal), ("HIGH(P84-P98)", high), ("EXTREME(>P98)", extreme)]:
    if mask.sum() > 0:
        print(f"  {name:14s}: N={mask.sum():4d}  cascade_rate={y[mask].mean():.3f}")

print("\n═══ HIPÓTESIS 3: SV5T D2 (velocidad) predice ═══")
r2, p2_ = spearmanr(df25["sv5_d2"].dropna(), y[df25["sv5_d2"].notna()])
print(f"  Spearman ρ(SV5T_D2, cascade) = {r2:+.4f} (p={p2_:.4f})")
# MIN vs MAX for D2
for t in ["MIN", "MAX"]:
    mask = df25["start_type"] == t
    r_t, p_t = spearmanr(df25.loc[mask, "sv5_d2"].dropna(), y[mask][df25.loc[mask, "sv5_d2"].notna()])
    print(f"  {t}: ρ(SV5T_D2, cascade) = {r_t:+.4f} (p={p_t:.4f})")

print("\n═══ HIPÓTESIS 4: MIN/MAX × turbulencia (interacción) ═══")
for t in ["MIN", "MAX"]:
    mask = df25["start_type"] == t
    r_t, p_t = spearmanr(df25.loc[mask, "sv5_d1"].dropna(), y[mask][df25.loc[mask, "sv5_d1"].notna()])
    print(f"  {t}: ρ(SV5T_D1, cascade) = {r_t:+.4f} (p={p_t:.4f})  N={mask.sum()}")
    # calm vs high within type
    calm_rate = y[mask & calm].mean() if (mask & calm).sum() > 0 else np.nan
    high_rate = y[mask & extreme].mean() if (mask & extreme).sum() > 0 else np.nan
    print(f"      CALM cascade_rate={calm_rate:.3f}  EXTREME cascade_rate={high_rate:.3f}")

print("\n═══ HIPÓTESIS 5: SV5T como modulador del cascade_conviction ═══")
# Does high turbulence amplify the cascade signal?
# Split by turbulence tercile, check cascade_rate of t3_high cascade_conviction
# We use prev_leg_return as proxy for domino (already have it)
z_dom = (df25["prev_leg_return"].abs() - df25["prev_leg_return"].abs().mean()) / df25["prev_leg_return"].abs().std()
high_turb = df25["sv5_d1"] > df25["sv5_d1"].median()
for name, mask in [("BAJA turb", ~high_turb), ("ALTA turb", high_turb)]:
    r_m, p_m = spearmanr(z_dom[mask], y[mask])
    print(f"  {name}: ρ(domino, cascade) = {r_m:+.4f} (p={p_m:.4f}) N={mask.sum()}")
