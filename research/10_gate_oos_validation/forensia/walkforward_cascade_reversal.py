#!/usr/bin/env python3
"""
WALK-FORWARD cascade_reversal (23-Ago-2026)
============================================
El umbral fijo −0.957 (calibrado full-sample) tiene inestabilidad temporal
(fire rate 29.9% fold-1 vs 6.3% fold-3/4 según auditoría Opus). Test de
viabilidad OOS con umbral ROLLING: en cada pivote, el umbral es el cuantil
p15 de c50 calculado SOLO con los 5 años anteriores (sin futuro).

Pregunta: ¿el edge medido por el evaluador se preserva bajo disciplina
walk-forward? Se compara contra el umbral fijo −0.957.
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))

import arnes.datos as datos_mod  # noqa: E402
# SIN override: ahora corre contra el pickle OFICIAL (sustituido 23-Ago)
import arnes  # noqa: E402
import evaluador_vela_a_vela as evv  # noqa: E402
evv._CACHE["df"] = None
evv._CACHE["signals"] = None
from arnes import SEÑALES  # noqa: E402

df, spy = datos_mod.cargar_datos()
dates = pd.to_datetime(df["pivot_date"])
c50 = df["cascade_conviction_50"]

VENTANA_AÑOS = 5
MIN_HIST = 252  # mínimo de observaciones para calcular el cuantil

# ── Umbral rolling: p15 de c50 en los 5 años previos a cada pivote ──
umbrales = []
for i in range(len(df)):
    cutoff = dates.iloc[i] - pd.Timedelta(days=VENTANA_AÑOS * 365)
    hist = c50[(dates >= cutoff) & (dates < dates.iloc[i])]
    if len(hist) >= MIN_HIST:
        umbrales.append(float(hist.quantile(0.15)))
    else:
        umbrales.append(np.nan)
df["_umbral_wf"] = umbrales

valid = df["_umbral_wf"].notna()
print(f"Pivotes con umbral WF calculable: {valid.sum()}/{len(df)} "
      f"(primeros {len(df)-valid.sum()} sin 5 años de historia)")

# Inyectar el df (con la columna _umbral_wf) en el cache del evaluador
evv._CACHE["df"] = df
evv._CACHE["spy"] = spy

mask_wf = valid & (c50 < df["_umbral_wf"])
mask_fijo = c50 < -0.957
print(f"Umbral WF: fire rate = {mask_wf[valid].mean():.1%} ({mask_wf.sum()} disparos)")
print(f"Umbral fijo (−0.957): fire rate = {mask_fijo.mean():.1%} ({mask_fijo.sum()} disparos)")
print(f"Umbral WF — media de umbrales: {df['_umbral_wf'].mean():.3f} "
      f"std: {df['_umbral_wf'].std():.3f}")

# ── Evaluador con la señal WF (override dinámico) ──
def señal_wf(d):
    if "_umbral_wf" not in d.columns:
        return pd.Series(False, index=d.index)
    return (d["cascade_conviction_50"] < d["_umbral_wf"]).fillna(False)

SEÑALES["cascade_reversal"] = señal_wf
evv._CACHE["signals"] = None
evv._CACHE["pool"] = None
r_wf = evv.evaluar("cascade_reversal")

print(f"\n{'='*100}\nWALK-FORWARD (umbral rolling p15, 5 años)")
print(f"{'='*100}")
print(f"status={r_wf.get('status')} N={r_wf.get('n_disparos')}")
for celda, p in r_wf.get("perfil_3d_régimen", {}).items():
    print(f"  {celda}: n={p['n']} fav_neto={p['fav_neto']*100:+.2f}% "
          f"hit={p['hit_rate']:.1%} p={p['p_value']} PF={p['profit_factor']}")

# ── Comparación con el fijo ──
def señal_fija(d):
    return (d["cascade_conviction_50"] < -0.957).fillna(False)

SEÑALES["cascade_reversal"] = señal_fija
evv._CACHE["signals"] = None
evv._CACHE["pool"] = None
r_fijo = evv.evaluar("cascade_reversal")

print(f"\n{'='*100}\nCOMPARACIÓN (mejor celda de cada uno)")
print(f"{'='*100}")

def mejor(r):
    best, best_n = None, None
    for c, p in r.get("perfil_3d_régimen", {}).items():
        if p["n"] >= 5 and (best is None or p["fav_neto"] > best["fav_neto"]):
            best, best_n = p, c
    return best_n, best

c_fijo, p_fijo = mejor(r_fijo)
c_wf, p_wf = mejor(r_wf)
print(f"FIJO  (−0.957): {c_fijo} n={p_fijo['n']} edge={p_fijo['fav_neto']*100:+.2f}% p={p_fijo['p_value']}")
print(f"W-FWD (rolling): {c_wf} n={p_wf['n']} edge={p_wf['fav_neto']*100:+.2f}% p={p_wf['p_value']}")

# ── Estabilidad del umbral rolling por era ──
df["_era"] = pd.cut(dates.dt.year, bins=[1993, 2000, 2005, 2011, 2019, 2027],
                    labels=["93-00", "00-05", "05-11", "11-19", "19-27"])
print(f"\nUmbral WF por era:")
print(df[valid].groupby("_era", observed=True)["_umbral_wf"].agg(
    ["mean", "std", "count"]).round(3).to_string())

out = ROOT / "data/research/signals/walkforward_cascade_reversal.json"
out.write_text(json.dumps({"fecha": "2026-08-23",
                           "ventana_años": VENTANA_AÑOS,
                           "n_disparos_wf": int(mask_wf.sum()),
                           "n_disparos_fijo": int(mask_fijo.sum()),
                           "evaluacion_wf": r_wf,
                           "evaluacion_fijo": r_fijo},
                          indent=1, ensure_ascii=False, default=str))
print(f"\n[✓] Guardado: {out}")
