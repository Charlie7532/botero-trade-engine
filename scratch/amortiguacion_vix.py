#!/usr/bin/env python3
"""¿El decaimiento del VIX tras un impulso es un sistema de segundo orden amortiguado?
Test empírico: para cada episodio de crisis (z>3 hasta decaer <2), ajusta el
decaimiento post-pico y mide:
  1) Semivida de reversión a la media (modelo OU / primer orden): t_half = ln2/κ
  2) ¿Oscila (segundo orden subamortiguado)? → cuenta cruces del nivel final
     y autocorrelación de los residuos (oscilación amortiguada deja ACF negativa)
  3) ζ efectivo: si hay oscilación, ζ = -ln(A2/A1) / sqrt(4π² + ln²(A2/A1))
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT / "backend/modules/entry_decision/domain/rules"))
from sigma_overflow import STATION_MU_SIGMA

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore(); conn = store._conn()
df = pd.read_sql("SELECT time::date as date, close FROM market.ohlcv_bars "
                 "WHERE ticker='VIX' AND timeframe='1d' ORDER BY time", conn)
store.close()
s = df.set_index("date")["close"].astype(float)

mu, sig = STATION_MU_SIGMA["vix"]["d1"]
z = (s - mu) / sig

# ── Episodios: z cruza +3, termina al decaer bajo +2 (solo UPPER: el miedo sube) ──
ep = []; in_ep = False; start = None
for d, zv in z.items():
    if not in_ep and zv > 3.0:
        in_ep = True; start = d
    elif in_ep and zv < 2.0:
        ep.append((start, d)); in_ep = False
if in_ep:
    ep.append((start, z.index[-1]))

print(f"VIX: {len(ep)} episodios de crisis (z>3 → decae <2σ)\n")

# ── Para cada episodio: pico → decaimiento. Ajustar reversión a la media. ──
mu_level = mu  # nivel de reposo (media del VIX)
resultados = []
for (t0, t1) in ep:
    seg = s.loc[t0:t1]
    if len(seg) < 5:
        continue
    peak_i = seg.idxmax()
    decay = seg.loc[peak_i:]            # fase de decaimiento post-pico
    if len(decay) < 4:
        continue
    x = decay.values
    t = np.arange(len(x))
    # Modelo 1: exponencial simple x(t) = μ + (x0-μ)·e^{-κ t}  (primer orden / OU)
    # linealizar: ln(x - μ) = ln(x0-μ) - κ t
    y = x - mu_level
    valid = y > 0
    if valid.sum() < 3:
        continue
    slope, intercept = np.polyfit(t[valid], np.log(y[valid]), 1)
    kappa = -slope                       # κ > 0 = reversión
    t_half = np.log(2) / kappa if kappa > 0 else np.inf
    resid1 = np.log(y[valid]) - (intercept + slope * t[valid])

    # Modelo 2: ¿oscila? cruces del nivel de reposo + ACF de residuos
    crossings = int(np.sum(np.diff(np.sign(y[valid] - np.median(y[valid]*0 + 0.0) if False else (x - mu_level))) != 0))
    # autocorrelación lag-1 y lag-2 de los residuos del modelo exponencial
    acf1 = np.corrcoef(resid1[:-1], resid1[1:])[0,1] if len(resid1) > 2 else np.nan
    acf2 = np.corrcoef(resid1[:-2], resid1[2:])[0,1] if len(resid1) > 3 else np.nan

    resultados.append({
        "inicio": str(t0), "pico": str(peak_i), "fin": str(t1),
        "peak_z": round(float((seg.max()-mu)/sig), 1),
        "n_decay": len(decay), "kappa": round(float(kappa), 3),
        "t_half_dias": round(float(t_half), 1) if np.isfinite(t_half) else None,
        "cruces": crossings, "acf1": round(float(acf1), 3) if not np.isnan(acf1) else None,
        "acf2": round(float(acf2), 3) if not np.isnan(acf2) else None,
    })

R = pd.DataFrame(resultados)
pd.set_option("display.width", 200)
print(R.to_string(index=False))

print("\n" + "="*80)
th = R["t_half_dias"].dropna()
print(f"SEMIVIDA de absorción del impulso VIX (modelo OU / primer orden):")
print(f"  media={th.mean():.1f}d  mediana={th.median():.1f}d  P25={th.quantile(.25):.1f}d  P75={th.quantile(.75):.1f}d")
osc = R["acf1"].dropna()
neg = (osc < -0.2).sum()
print(f"\nOSCILACIÓN (segundo orden subamortiguado):")
print(f"  episodios con ACF1 < -0.2 (residuo oscilante): {neg}/{len(osc)}")
print(f"  → si pocos: el decaimiento es reversión a la media (1er orden), NO oscilación amortiguada")
