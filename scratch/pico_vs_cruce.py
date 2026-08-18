import numpy as np, pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore()
vix = store.load_bars("VIX","1d")["close"].copy(); spy = store.load_bars("SPY","1d")["close"].copy()
vix.index = pd.to_datetime(vix.index); spy.index = pd.to_datetime(spy.index)
store.close()

vix_mean = vix.mean(); vix_std = vix.std()
threshold = vix_mean + 2 * vix_std  # ~28-30
print(f"VIX 2σ = {threshold:.1f}\n")

# Align to common dates
common_dates = vix.index.intersection(spy.index)
vix = vix.loc[common_dates]; spy = spy.loc[common_dates]

vals = vix.values; spy_vals = spy.values; n = len(vals)

entro_pico = []   # buy at peak (VIX above 2σ, still there)
entro_cruce = []  # wait for VIX to cross BELOW 2σ, then buy

for i in range(5, n-15):
    if vals[i] >= threshold:
        if i+1 < n and i+10 < n:
            ret_5 = spy_vals[min(i+5,n-1)] / spy_vals[i+1] - 1
            ret_10 = spy_vals[min(i+10,n-1)] / spy_vals[i+1] - 1
            entro_pico.append((ret_5, ret_10))
        
        above = True
        for j in range(i+1, min(i+15, n-10)):
            if above and vals[j] < threshold:
                above = False
                # First bar below 2σ = cruzó → buy next bar
                if j+1 < n:
                    ret_5 = spy_vals[min(j+6,n-1)] / spy_vals[j+1] - 1
                    ret_10 = spy_vals[min(j+11,n-1)] / spy_vals[j+1] - 1
                    entro_cruce.append((ret_5, ret_10))
                break  # solo el primer cruce
        # Also track if it NEVER crossed below (stayed extreme)
        # Skip these for now

pico_5 = np.array([r[0] for r in entro_pico if not np.isnan(r[0])])
pico_10 = np.array([r[1] for r in entro_pico if not np.isnan(r[1])])
cruce_5 = np.array([r[0] for r in entro_cruce if not np.isnan(r[0])])
cruce_10 = np.array([r[1] for r in entro_cruce if not np.isnan(r[1])])

print(f"═══ COMPARACIÓN: ¿comprar en el pico o esperar el cruce? ═══\n")
print(f"  {'Estrategia':<25} {'N':>5} {'SPY 5d':>10} {'SPY 10d':>10} {'%positivo 5d':>12}")
print(f"  {'COMPRAR EN EL PICO':<25} {len(pico_5):>5} {pico_5.mean()*100:>+9.2f}% {pico_10.mean()*100:>+9.2f}% {(pico_5>0).mean()*100:>10.0f}%")
print(f"  {'ESPERAR EL CRUCE ↓2σ':<25} {len(cruce_5):>5} {cruce_5.mean()*100:>+9.2f}% {cruce_10.mean()*100:>+9.2f}% {(cruce_5>0).mean()*100:>10.0f}%")

# Bootstrap difference
rng = np.random.default_rng(42)
diffs = []
for _ in range(2000):
    bs_p = rng.choice(pico_5, size=len(pico_5), replace=True).mean()
    bs_c = rng.choice(cruce_5, size=len(cruce_5), replace=True).mean()
    diffs.append(bs_p - bs_c)
ci = np.percentile(diffs, [2.5, 97.5])
print(f"\n  Bootstrap Δ(pico - cruce) 5d: CI95 [{ci[0]*100:+.2f}%, {ci[1]*100:+.2f}%]")
print(f"  Prob(pico > cruce): {(np.array(diffs)>0).mean():.0%}")

# Days to cross
above_periods = []
for i in range(5, n-5):
    if vals[i] >= threshold:
        for j in range(i+1, min(i+30, n)):
            if vals[j] < threshold:
                above_periods.append(j - i)
                break
print(f"\n  Días sobre 2σ hasta cruzar: media={np.mean(above_periods):.1f}, P50={np.median(above_periods):.0f}")