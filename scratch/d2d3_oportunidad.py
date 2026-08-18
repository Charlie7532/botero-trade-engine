import numpy as np, pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore()
vix = store.load_bars("VIX","1d")["close"].copy(); spy = store.load_bars("SPY","1d")["close"].copy()
vix.index = pd.to_datetime(vix.index); spy.index = pd.to_datetime(spy.index)
common = vix.index.intersection(spy.index)
vix = vix.loc[common]; spy = spy.loc[common]
vix_vel = vix.diff(3); vix_vol = (vix.rolling(2).std()/vix.rolling(10).std()).fillna(1.0)
store.close()

vals=vix.values; vel_vals=vix_vel.values; vol_vals=vix_vol.values; spy_vals=spy.values; n=len(vals)

# Speed buckets: slow, medium, fast (absolute velocity)
vel_p33 = np.nanquantile(np.abs(vel_vals), 0.33); vel_p67 = np.nanquantile(np.abs(vel_vals), 0.67)
vol_p33 = np.nanquantile(vol_vals, 0.33); vol_p67 = np.nanquantile(vol_vals, 0.67)

print(f"|vel| P33={vel_p33:.1f} P67={vel_p67:.1f} | vol P33={vol_p33:.2f} P67={vol_p67:.2f}\n")

results = []
for i in range(10, n-20):
    v = vals[i]; vel = abs(vel_vals[i]); vol = vol_vals[i]
    ret_10 = spy_vals[min(i+10,n-1)]/spy_vals[i] - 1
    results.append({"vix":v, "vel_abs":vel, "vel":vel_vals[i], "vol":vol, "ret10":ret_10})
df = pd.DataFrame(results).dropna()

# VIX elevated (>= 20 for more samples, then focus >= 30)
for elev_label, elev_mask in [("VIX ≥ 20", df["vix"]>=20), ("VIX ≥ 25", df["vix"]>=25), ("VIX ≥ 30", df["vix"]>=30)]:
    sub = df[elev_mask]
    if len(sub) < 30: continue
    print(f"═══ {elev_label} (N={len(sub)}) ═══")
    print(f"  {'Velocidad':<20} {'Volatilidad':<20} {'SPY 10d':>9} {'%pos':>6} {'N':>5}")
    for vlab, vmask in [("LENTA", sub["vel_abs"]<vel_p33), ("MEDIA", (sub["vel_abs"]>=vel_p33)&(sub["vel_abs"]<vel_p67)), ("RÁPIDA", sub["vel_abs"]>=vel_p67)]:
        for dlab, dmask in [("BAJA", sub["vol"]<vol_p33), ("MEDIA", (sub["vol"]>=vol_p33)&(sub["vol"]<vol_p67)), ("ALTA", sub["vol"]>=vol_p67)]:
            m = vmask & dmask
            if m.sum() < 5: continue
            r = sub.loc[m,"ret10"].mean()*100
            pos = (sub.loc[m,"ret10"]>0).mean()*100
            marker = "★" if abs(r) > 1.5 or pos > 65 or pos < 35 else " "
            print(f"{marker} {vlab:<20} {dlab:<20} {r:>+8.2f}% {pos:>5.0f}% {m.sum():>5}")

# Deceleration gradient: VIX >= 25, velocity NEGATIVE (falling) but split by magnitude
print(f"\n═══ GRADIENTE DE VELOCIDAD (VIX ≥ 25, D2 negativo = cayendo) ═══")
sub25 = df[df["vix"]>=25]
neg = sub25[sub25["vel"] < 0]
neg_lo = neg["vel"].abs() < vel_p33; neg_md = (neg["vel"].abs() >= vel_p33) & (neg["vel"].abs() < vel_p67)
neg_hi = neg["vel"].abs() >= vel_p67
for label, mask in [("CAE LENTO", neg_lo), ("CAE MEDIO", neg_md), ("CAE RÁPIDO (crush)", neg_hi)]:
    m = mask
    if m.sum() < 5: continue
    r = neg.loc[m,"ret10"].mean()*100
    pos = (neg.loc[m,"ret10"]>0).mean()*100
    print(f"  {label:<20}: SPY 10d={r:+.2f}%  %pos={pos:.0f}%  N={m.sum()}")

# Sweet spot: VIX >= 25, D3 low, velocity negative
print(f"\n═══ PUNTO DULCE: VIX ≥ 25 + D3 BAJA + velocidad ↓ ═══")
sweet = sub25[(sub25["vol"]<vol_p33) & (sub25["vel"]<0)]
if len(sweet) > 5:
    print(f"  SPY 10d={sweet['ret10'].mean()*100:+.2f}%  %pos={(sweet['ret10']>0).mean()*100:.0f}%  N={len(sweet)}")