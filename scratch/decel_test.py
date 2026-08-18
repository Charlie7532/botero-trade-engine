import numpy as np, pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore()
vix = store.load_bars("VIX","1d")["close"].copy(); spy = store.load_bars("SPY","1d")["close"].copy()
vix.index = pd.to_datetime(vix.index); spy.index = pd.to_datetime(spy.index)
common = vix.index.intersection(spy.index)
vix = vix.loc[common]; spy = spy.loc[common]
vix_vel = vix.diff(3)  # D2

vals=vix.values; vel_vals=vix_vel.values; spy_vals=spy.values; n=len(vals)

# D2 acceleration: D2(t) - D2(t-3)
vel_accel = vix_vel.diff(3).values

entro_peak = []    # VIX ≥ 30, D2 UP (acelerando — el pico)
entro_decel = []   # VIX ≥ 30, D2 UP pero DECELERANDO (perdiendo velocidad)
entro_flip = []    # VIX ≥ 30, D2 DOWN (ya flipeó)

for i in range(10, n-20):
    if vals[i] < 30 or np.isnan(vals[i]): continue
    ret_10 = spy_vals[min(i+10,n-1)]/spy_vals[i] - 1 if i+10 < n else np.nan
    ret_20 = spy_vals[min(i+20,n-1)]/spy_vals[i] - 1 if i+20 < n else np.nan
    
    if vel_vals[i] > 0:
        if vel_accel[i] > 0:  # acelerando (D2 subiendo más rápido)
            entro_peak.append((ret_10, ret_20))
        else:  # decelerando (D2 positivo pero bajando)
            entro_decel.append((ret_10, ret_20))
    else:  # D2 negativo (ya flipeó)
        entro_flip.append((ret_10, ret_20))

peak_10 = np.array([r[0] for r in entro_peak if not np.isnan(r[0])])
decel_10 = np.array([r[0] for r in entro_decel if not np.isnan(r[0])])
flip_10 = np.array([r[0] for r in entro_flip if not np.isnan(r[0])])

peak_20 = np.array([r[1] for r in entro_peak if not np.isnan(r[1])])
decel_20 = np.array([r[1] for r in entro_decel if not np.isnan(r[1])])
flip_20 = np.array([r[1] for r in entro_flip if not np.isnan(r[1])])

print("═══ VIX ≥ 30 — ¿Cuándo comprar? ═══\n")
print(f"  {'Estrategia':<45} {'N':>5} {'SPY 10d':>10} {'SPY 20d':>10} {'%pos 10d':>9}")
print(f"  {'D2↑ ACELERANDO (pico del miedo)':<45} {len(peak_10):>5} {peak_10.mean()*100:>+9.2f}% {peak_20.mean()*100:>+9.2f}% {(peak_10>0).mean()*100:>8.0f}%")
print(f"  {'D2↑ DECELERANDO (pierde velocidad)':<45} {len(decel_10):>5} {decel_10.mean()*100:>+9.2f}% {decel_20.mean()*100:>+9.2f}% {(decel_10>0).mean()*100:>8.0f}%")
print(f"  {'D2↓ FLIP (ya bajó)':<45} {len(flip_10):>5} {flip_10.mean()*100:>+9.2f}% {flip_20.mean()*100:>+9.2f}% {(flip_10>0).mean()*100:>8.0f}%")

# Bootstrap decel vs others
rng = np.random.default_rng(42)
for comp, label in [(peak_10, "acelerando"), (flip_10, "flip")]:
    if len(decel_10) < 5 or len(comp) < 5: continue
    diffs = []
    for _ in range(2000):
        bs_d = rng.choice(decel_10, size=len(decel_10), replace=True).mean()
        bs_c = rng.choice(comp, size=len(comp), replace=True).mean()
        diffs.append(bs_d - bs_c)
    ci = np.percentile(diffs, [2.5, 97.5])
    print(f"\n  Bootstrap decelerando vs {label}:")
    print(f"    Δ10d: CI95 [{ci[0]*100:+.2f}%, {ci[1]*100:+.2f}%]  Prob(mejor)= {(np.array(diffs)>0).mean():.0%}")