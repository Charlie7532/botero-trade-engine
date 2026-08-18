import numpy as np, pandas as pd
from datetime import timedelta

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

store = TimescaleDataStore(); repo = ZigzagLegRepository(store)
legs25 = repo.get_confirmed_legs("SPY","zz25"); legs50 = repo.get_confirmed_legs("SPY","zz50"); legs75 = repo.get_confirmed_legs("SPY","zz75")
s50 = {pd.to_datetime(l.start_timestamp).date() for l in legs50}
s75 = {pd.to_datetime(l.start_timestamp).date() for l in legs75}

df25 = pd.DataFrame([{"start_timestamp":l.start_timestamp,"start_type":l.start_type,"prev_leg_return":l.prev_leg_return} for l in legs25])
df25 = df25.dropna(subset=["prev_leg_return"]).reset_index(drop=True)
df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["c50"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in s50 for i in range(-3,4))))
df25["c75"] = df25["pivot_date"].apply(lambda d: int(any(d+timedelta(days=i) in s75 for i in range(-3,4))))
df25["next_bear"] = (df25["start_type"].shift(-1)=="MIN").astype(float)

# Load VIX + FG (fear and euphoria proxies)
vix = store.load_bars("VIX","1d")["close"].copy(); fg = store.load_bars("FG","1d")["close"].copy()
vix.index = [d.date() if hasattr(d,'date') else d for d in pd.to_datetime(vix.index)]
fg.index = [d.date() if hasattr(d,'date') else d for d in pd.to_datetime(fg.index)]
vix_vel = vix.diff(3); fg_vel = fg.diff(3)
vix_std2=vix.rolling(2).std(); vix_std10=vix.rolling(10).std(); vix_vol=(vix_std2/vix_std10).fillna(1.0)
fg_std2=fg.rolling(2).std(); fg_std10=fg.rolling(10).std(); fg_vol=(fg_std2/fg_std10).fillna(1.0)
store.close()

rows = []
for _, row in df25.iterrows():
    pd_ = row["pivot_date"]
    # VIX
    iv=vix.index[vix.index<=pd_]; iv2=vix_vel.index[vix_vel.index<=pd_]; iv3=vix_vol.index[vix_vol.index<=pd_]
    vv=float(vix.iloc[len(iv)-1]) if len(iv)>0 else np.nan
    ve=float(vix_vel.iloc[len(iv2)-1]) if len(iv2)>0 else 0.0
    vo=float(vix_vol.iloc[len(iv3)-1]) if len(iv3)>0 else 1.0
    # VIX D2 previous (3d ago) sign for flip detection
    ve_prev_idx = vix_vel.index[vix_vel.index <= pd_ + timedelta(days=-3)]
    ve_prev = float(vix_vel.iloc[len(ve_prev_idx)-1]) if len(ve_prev_idx)>0 else ve
    
    # FG
    i_fg=fg.index[fg.index<=pd_]; i_fg2=fg_vel.index[fg_vel.index<=pd_]; i_fg3=fg_vol.index[fg_vol.index<=pd_]
    fv=float(fg.iloc[len(i_fg)-1]) if len(i_fg)>0 else np.nan
    fe=float(fg_vel.iloc[len(i_fg2)-1]) if len(i_fg2)>0 else 0.0
    fo=float(fg_vol.iloc[len(i_fg3)-1]) if len(i_fg3)>0 else 1.0
    fe_prev_idx = fg_vel.index[fg_vel.index <= pd_ + timedelta(days=-3)]
    fe_prev = float(fg_vel.iloc[len(fe_prev_idx)-1]) if len(fe_prev_idx)>0 else fe
    
    rows.append({"vix":vv,"vix_vel":ve,"vix_vol":vo,"vix_vel_prev":ve_prev,
                 "fg":fv,"fg_vel":fe,"fg_vol":fo,"fg_vel_prev":fe_prev,
                 "c50":row["c50"],"c75":row["c75"],"bear":row["next_bear"]})

df = pd.DataFrame(rows).dropna(subset=["vix","fg"])

# FLIP detection
df["vix_flip"] = (np.sign(df["vix_vel"]) != np.sign(df["vix_vel_prev"]))
df["fg_flip"] = (np.sign(df["fg_vel"]) != np.sign(df["fg_vel_prev"]))

# Extreme D1
vix_extreme = df["vix"] >= 30
fg_extreme = df["fg"] >= 80  # greed/euphoria

# Velocity direction NOW
vix_vel_up = df["vix_vel"] > 0; vix_vel_down = df["vix_vel"] < 0
fg_vel_up = df["fg_vel"] > 0; fg_vel_down = df["fg_vel"] < 0

# D3
vix_d3_lo = df["vix_vol"] < df["vix_vol"].quantile(0.50)
fg_d3_lo = df["fg_vol"] < df["fg_vol"].quantile(0.50)

def prob(m,t): m2=m&t.notna(); return t[m2].mean(),m2.sum()

print("═"*65)
print("  TIMING: ¿Cuándo COMPRAR miedo y VENDER euforia?")
print("═"*65)

# MIEDO (VIX extreme)
print(f"\n── MIEDO (VIX ≥ 30, N={vix_extreme.sum()}) ──")
print(f"  {'Escenario':<45} {'%bear':>8} {'N':>5}")

# FLIP to DOWN (fear was building, now resolving → BUY signal)
flip_down = vix_extreme & df["vix_flip"] & vix_vel_down
p,n = prob(flip_down, df["bear"])
print(f"  {'FLIP a DOWN (miedo PASÓ)':<45} {p*100:>7.1f}% {n:>5}")

# Still UP (fear still building → WAIT)
still_up = vix_extreme & ~df["vix_flip"] & vix_vel_up
p,n = prob(still_up, df["bear"])
print(f"  {'AÚN SUBIENDO (miedo CRECE)':<45} {p*100:>7.1f}% {n:>5}")

# FLIP + D3 low (calm transition → more reliable)
flip_down_calm = flip_down & vix_d3_lo
p,n = prob(flip_down_calm, df["bear"])
print(f"  {'FLIP a DOWN + vol BAJA (transición calma)':<45} {p*100:>7.1f}% {n:>5}")

# FLIP + cascade
p,n = prob(flip_down, df["c50"])
print(f"  {'FLIP a DOWN → cascade_50':<45} {p*100:>7.1f}% {n:>5}")

# EUFORIA (FG extreme)
print(f"\n── EUFORIA (FG ≥ 80, N={fg_extreme.sum()}) ──")

# FLIP to DOWN (euphoria was building, now fading → SELL signal)
flip_fg_down = fg_extreme & df["fg_flip"] & fg_vel_down
p,n = prob(flip_fg_down, df["bear"])
print(f"  {'FLIP a DOWN (euforia SE AGOTÓ)':<45} {p*100:>7.1f}% {n:>5}")

# Still UP (euphoria still building → HOLD)
still_fg_up = fg_extreme & ~df["fg_flip"] & fg_vel_up
p,n = prob(still_fg_up, df["bear"])
print(f"  {'AÚN SUBIENDO (euforia CRECE)':<45} {p*100:>7.1f}% {n:>5}")

# FLIP + D3 low
flip_fg_down_calm = flip_fg_down & fg_d3_lo
p,n = prob(flip_fg_down_calm, df["bear"])
print(f"  {'FLIP a DOWN + vol BAJA':<45} {p*100:>7.1f}% {n:>5}")

p,n = prob(flip_fg_down, df["c50"])
print(f"  {'FLIP a DOWN → cascade_50':<45} {p*100:>7.1f}% {n:>5}")

# Summary
print(f"\n═══ REGLA DE TIMING ═══")
print(f"  COMPRAR cuando: VIX ≥ 30 + D2 flip ↓ + D3 baja")
print(f"  ESPERAR cuando: VIX ≥ 30 + D2 aún ↑")
print(f"  VENDER cuando:  FG ≥ 80 + D2 flip ↓")
print(f"  MANTENER cuando: FG ≥ 80 + D2 aún ↑")