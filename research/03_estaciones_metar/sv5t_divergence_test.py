import numpy as np
import pandas as pd
from datetime import timedelta
from scipy.stats import spearmanr

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

def load_series(ticker):
    s = store.load_bars(ticker, "1d")["close"].copy()
    s.index = [d.date() if hasattr(d, 'date') else d for d in pd.to_datetime(s.index)]
    return s.sort_index()

vix = load_series("VIX")
sv5t = load_series("SV5_TURBULENCE")

def lookup_at(series, pivot_date):
    idx = series.index[series.index <= pivot_date]
    return float(series.loc[idx[-1]]) if len(idx) > 0 else np.nan

vix_vals = [lookup_at(vix, d) for d in df25["pivot_date"]]
sv5_vals = [lookup_at(sv5t, d) for d in df25["pivot_date"]]
df25["vix"] = vix_vals
df25["sv5t"] = sv5_vals

store.close()

y = df25["cascade_50"].values

# z-scores for divergence
z_vix = (df25["vix"] - df25["vix"].mean()) / df25["vix"].std()
z_sv5 = (df25["sv5t"] - df25["sv5t"].mean()) / df25["sv5t"].std()
df25["z_vix"] = z_vix
df25["z_sv5"] = z_sv5

# Divergence: VIX high, SV5T low → positive; VIX low, SV5T high → negative
df25["divergence"] = z_vix - z_sv5

def ic(a, b):
    m = ~np.isnan(a) & ~np.isnan(b)
    if m.sum() < 30: return np.nan
    return spearmanr(a[m], b[m])[0]

print("═══ DIVERGENCIA VIX vs SV5T ═══")
print(f"IC(VIX solo, cascade)          = {ic(df25['z_vix'], y):+.4f}")
print(f"IC(SV5T solo, cascade)         = {ic(df25['z_sv5'], y):+.4f}")
print(f"IC(DIVERGENCIA vix-sv5, casc)  = {ic(df25['divergence'], y):+.4f}")

print("\n═══ DIVERGENCIA como MODULADOR ═══")
# Does divergence condition the VIX signal?
vix_high = df25["z_vix"] > df25["z_vix"].median()
sv5_high = df25["z_sv5"] > df25["z_sv5"].median()

quadrants = {
    "VIX↑ SV5↑ (miedo+batalla)": vix_high & sv5_high,
    "VIX↑ SV5↓ (miedo sin batalla)": vix_high & ~sv5_high,
    "VIX↓ SV5↑ (batalla sin miedo)": ~vix_high & sv5_high,
    "VIX↓ SV5↓ (calma total)": ~vix_high & ~sv5_high,
}
print(f"{'Cuadrante':<32} {'N':>5} {'cascade_rate':>13}")
for name, mask in quadrants.items():
    if mask.sum() > 0:
        print(f"{name:<32} {mask.sum():>5} {y[mask].mean():>13.3f}")

# MIN vs MAX for divergence
print("\n═══ DIVERGENCIA por tipo de pivote ═══")
for t in ["MIN", "MAX"]:
    mask = df25["start_type"] == t
    r = ic(df25.loc[mask, "divergence"], y[mask])
    print(f"  {t}: IC(divergencia, cascade) = {r:+.4f} (N={mask.sum()})")
