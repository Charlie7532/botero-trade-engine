#!/usr/bin/env python3
"""
CALIBRACIÓN DE cascade_reversal (23-Ago-2026)
==============================================
El umbral original (c50 < 0.30) quedó descalibrado con la normalización de
producción (fire rate 75.8% = background puro). Barrido de umbrales para
encontrar el corte donde la señal recupera valor informativo.

Semántica: EXIT de posiciones largas — "la convicción cascade colapsó".
Candidatos naturales: tercil bajo del cal-file, cambio de signo, cuantiles.
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))

import arnes.datos as datos_mod
datos_mod.OBS_PKL = ROOT / "data/research/pivots/quants_obs_new.pkl"

import arnes  # noqa: E402
import evaluador_vela_a_vela as evv  # noqa: E402
evv._CACHE["df"] = None
evv._CACHE["signals"] = None

from arnes import SEÑALES  # noqa: E402

df, spy = datos_mod.cargar_datos()
c50 = df["cascade_conviction_50"]
cal = json.loads((ROOT / "backend/modules/entry_decision/domain/rules"
                  / "cascade_calibration.json").read_text())
t_low, t_high = cal["tercile_edges"]
print(f"tercile_edges cal-file: [{t_low}, {t_high}]")
print(f"c50: media={c50.mean():.3f} std={c50.std():.3f} "
      f"P33={c50.quantile(1/3):.3f} P50={c50.quantile(0.5):.3f}\n")

# ── Barrido de umbrales ──
CANDIDATOS = {
    "tercil_bajo": t_low,           # corte natural del compositor (t1_low)
    "cero": 0.0,                    # cambio de signo
    "p25": float(c50.quantile(0.25)),
    "p20": float(c50.quantile(0.20)),
    "p15": float(c50.quantile(0.15)),
    "p10": float(c50.quantile(0.10)),
    "original_0.30": 0.30,          # referencia (descalibrado)
}

resultados = {}
print(f"{'umbral':<14} {'corte':>8} {'fire_rate':>10} {'N':>6}")
print("-" * 44)
for nombre, corte in CANDIDATOS.items():
    mask = (c50 < corte)
    resultados[nombre] = {"corte": round(float(corte), 4),
                          "fire_rate": round(float(mask.mean()), 4),
                          "n": int(mask.sum())}
    print(f"{nombre:<14} {corte:>8.3f} {mask.mean():>10.1%} {mask.sum():>6}")

# ── Evaluador para cada candidato con fire rate ≤ 25% ──
print(f"\n{'='*100}\nEVALUADOR por candidato (fire rate ≤ 25%)")
print(f"{'='*100}")
evaluaciones = {}
for nombre, corte in CANDIDATOS.items():
    if (c50 < corte).mean() > 0.25:
        print(f"\n{nombre}: SKIPPED (fire rate > 25% = background)")
        continue
    # override temporal de la definición de la señal
    def make_sig(thr):
        def _sig(d):
            if "cascade_conviction_50" not in d.columns:
                return pd.Series(False, index=d.index)
            return (d["cascade_conviction_50"] < thr).fillna(False)
        return _sig

    SEÑALES["cascade_reversal"] = make_sig(corte)
    evv._CACHE["signals"] = None  # reset pool cache
    evv._CACHE["pool"] = None
    try:
        r = evv.evaluar("cascade_reversal")
    except Exception as e:
        print(f"\n{nombre}: ERROR {e}")
        continue
    evaluaciones[nombre] = r
    print(f"\n{nombre} (corte={corte:.3f}): status={r.get('status')}, "
          f"N={r.get('n_disparos')}")
    for celda, p in r.get("perfil_3d_régimen", {}).items():
        print(f"  {celda}: n={p['n']} fav_neto={p['fav_neto']*100:+.2f}% "
              f"hit={p['hit_rate']:.1%} p={p['p_value']} PF={p['profit_factor']}")
    f3 = r.get("forensia_F3", {})
    print(f"  INDEP={f3.get('independencia')}")

out = ROOT / "data/research/signals/calibracion_cascade_reversal.json"
out.write_text(json.dumps({"fecha": "2026-08-23",
                           "tercile_edges": cal["tercile_edges"],
                           "candidatos": resultados,
                           "evaluaciones": evaluaciones},
                          indent=1, ensure_ascii=False, default=str))
print(f"\n[✓] Guardado: {out}")
