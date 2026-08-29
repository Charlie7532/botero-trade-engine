#!/usr/bin/env python3
"""P2.8 — SEMIVIDA VIX POR RÉGIMEN (corrección Opus C.1/C.2)
=============================================================
La "semivida 8.2d" esconde una distribución bimodal: shocks ordinarios
(3-16d) vs crisis sistémicas (GFC 112d, pandemia 15.7d). Reportar por régimen:

  SHOCK NORMAL:   peak_z < 5σ  → decaimiento rápido
  CRISIS SISTÉMICA: peak_z >= 5σ → decaimiento estructural

Clasificación observable: el peak_z SE CONOCE en tiempo real cuando ocurre
(el VIX marca el pico), no requiere saber el futuro. El peak_z del episodio
se mide al inicio (cuando z cruza +3), escalando hacia el pico observado.
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
s.index = pd.to_datetime(s.index)

mu, sig = STATION_MU_SIGMA["vix"]["d1"]
z = (s - mu) / sig

# ── Episodios ──
ep = []; in_ep = False; start = None
for dt, zv in z.items():
    if not in_ep and zv > 3.0:
        in_ep = True; start = dt
    elif in_ep and zv < 2.0:
        ep.append((start, dt)); in_ep = False
if in_ep:
    ep.append((start, z.index[-1]))

rows = []
for (t0, t1) in ep:
    seg = s.loc[t0:t1]
    if len(seg) < 4:
        continue
    peak = seg.max()
    peak_z = (peak - mu) / sig
    dur = (t1 - t0).days
    regime = "CRISIS_SISTEMICA" if peak_z >= 5.0 else "SHOCK_NORMAL"
    rows.append({"inicio": str(t0.date()), "fin": str(t1.date()),
                 "peak_vix": round(peak, 1), "peak_z": round(peak_z, 2),
                 "duracion_dias": dur, "regimen": regime})

R = pd.DataFrame(rows)
print(f"EPISODIOS DE CRISIS DEL VIX: {len(R)}")
print(f"{'='*95}")
print(R.to_string(index=False))

print(f"\n{'='*95}")
print("SEMIVIDA POR RÉGIMEN")
print(f"{'='*95}")
for reg, sub in R.groupby("regimen"):
    d = sub["duracion_dias"]
    print(f"\n{reg} (n={len(sub)}):")
    print(f"  duración: media={d.mean():.1f}d  mediana={d.median():.1f}d  "
          f"P25={d.quantile(.25):.1f}d  P75={d.quantile(.75):.1f}d  máx={d.max():.0f}d")
    print(f"  episodios: {', '.join(sub['inicio'].str[:7])}")

# ── ¿El peak_z predice la duración? (observable en tiempo real) ──
from scipy.stats import spearmanr
valid = R.dropna(subset=["peak_z", "duracion_dias"])
rho, p = spearmanr(valid["peak_z"], valid["duracion_dias"])
print(f"\n{'='*95}")
print(f"¿PEAK_Z PREDICE DURACIÓN? (observable en tiempo real)")
print(f"Spearman: rho={rho:.2f}  p={p:.4f}  (n={len(valid)})")
print(f"{'='*95}")
if rho > 0.5 and p < 0.05:
    print("→ El peak_z SÍ predice duración: se puede clasificar shock vs sistémico")
    print("  OBSERVANDO el nivel del VIX en el pico (sin saber el futuro).")
else:
    print("→ Correlación débil o no significativa.")

# ── Regla operativa propuesta ──
print(f"\n{'='*95}")
print("REGLA OPERATIVA PROPUESTA")
print(f"{'='*95}")
thr = R.groupby("regimen")["peak_z"].agg(["min", "max"])
print(thr.to_string())
print(f"\nSi peak_z >= 5σ → CRISIS SISTÉMICA → no esperar reversión rápida")
print(f"Si peak_z < 5σ  → SHOCK NORMAL → semivida ~{R[R['regimen']=='SHOCK_NORMAL']['duracion_dias'].median():.0f}d")
