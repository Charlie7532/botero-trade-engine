#!/usr/bin/env python3
"""SEÑALES D3 CANDIDATAS (P2.7) — el punto ciego de inestabilidad
==================================================================
Los 110 overflows D3 no contenidos son el inventario de diamantes. Definimos
señales candidatas sobre la dimensión D3 (vol-of-vol = std2/std10) y las
evaluamos con el MISMO método validado del evaluador vela a vela (inyección
en su registry, sin tocar el catálogo oficial todavía).

Diseño (hipótesis de la semivida): D3 alto = la volatilidad de la volatilidad
se está rompiendo = transición de régimen en curso. La incertidumbre se resuelve
midiendo, no suponiendo: cada candidata se prueba como MIN (ENTRY) y MAX (EXIT)
y la significancia decide la dirección.

Candidatas (todas observables en tiempo real, sin pivot_type):
  d3_turb    — turbulencia inestable (sv5_turbulence z>3)
  d3_bsi     — breadth inestable (bsi z>3)
  d3_skew    — colas inestables (skew z>3)
  d3_yield   — curva inestable (yield_curve z>3)
  d3_multi   — inestabilidad sistémica (≥2 estaciones con z>3 el mismo día)
  d3_extremo — overflow extremo (cualquier estación z>4)
"""
import sys
import numpy as np, pandas as pd
from pathlib import Path

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))
sys.path.insert(0, str(ROOT / "backend/modules/entry_decision/domain/rules"))

import evaluador_vela_a_vela as evv
from medir_senal import cargar_datos, SEÑALES
from sigma_overflow import validate_overflow

df, spy = cargar_datos()

# ── Construcción de las máscaras D3 (observables, sin futuro) ──
EST_D3 = {"vix": "vix_vol", "vvix": "vvix_vol", "pcr": "pcr_vol", "fg": "fg_vol",
          "sv5_turbulence": "sv5_turbulence_vol", "skew": "skew_vol",
          "credit": "credit_vol", "bsi": "bsi_vol", "dxy": "dxy_vol",
          "rotation": "rotation_vol", "yield_curve": "yield_curve_vol"}

depths = {}
for est, col in EST_D3.items():
    vals = df[col].astype(float)
    d = pd.Series(np.nan, index=df.index)
    for i, v in vals.items():
        if pd.isna(v):
            continue
        depth, flag = validate_overflow(est, "d3", float(v))
        if depth is not None:
            d.iloc[i] = float(depth)
    depths[est] = d

dep = pd.DataFrame(depths)
mask_multi = (dep > 3.0).sum(axis=1) >= 2
mask_extremo = (dep > 4.0).any(axis=1)

candidatas = {
    "d3_turb":  dep["sv5_turbulence"] > 3.0,
    "d3_bsi":   dep["bsi"] > 3.0,
    "d3_skew":  dep["skew"] > 3.0,
    "d3_yield": dep["yield_curve"] > 3.0,
    "d3_multi": mask_multi,
    "d3_extremo": mask_extremo,
}

print(f"Candidatas D3 (fire rates):")
for n, m in candidatas.items():
    print(f"  {n:>11s}: {m.sum():>4d} disparos ({m.mean():.1%})")

# ── Inyectar en el evaluador: cada candidata × {MIN, MAX} ──
resultados = []
for n, mask in candidatas.items():
    if mask.mean() > 0.20:
        print(f"  {n}: EXCLUIDA por background (fire rate >20%)")
        continue
    for blanco in ["MIN", "MAX"]:
        nombre = f"{n}_{blanco.lower()}"
        fn = (lambda m: lambda df_: m.reindex(df_.index, fill_value=False))(mask)
        fn.__name__ = nombre
        evv.SEÑALES[nombre] = fn
        evv.BLANCOS[nombre] = blanco
        r = evv.evaluar(nombre)
        r["nombre"] = nombre
        resultados.append(r)

# ── Tabla resumen: mejor celda por candidata ──
print(f"\n{'='*108}")
print(f"RESULTADOS — señales D3 candidatas (first-passage, baseline por celda, p binomial)")
print(f"{'='*108}")
print(f"{'señal':>16s} {'celda':>11s} | {'N':>4s} {'neto':>7s} {'hit%':>6s} {'p-val':>8s} {'PF':>5s} {'INDEP':>6s} {'tier':>9s}")
filas = []
for r in resultados:
    if r.get("status") != "OK":
        print(f"{r.get('nombre','?'):>16s} — {r.get('status')}: {str(r.get('razon',''))[:60]}")
        continue
    indep = r.get("forensia_F3", {}).get("independencia")
    for celda, c in r.get("perfil_3d_régimen", {}).items():
        if c.get("n", 0) < 3:
            continue
        filas.append((r["nombre"], celda, c.get("n", 0), c.get("fav_neto", 0),
                      c.get("hit_rate", 0), c.get("p_value", 1),
                      c.get("profit_factor", 0),
                      indep if indep is not None else 0,
                      c.get("confidence_tier", "")))

filas.sort(key=lambda x: (x[5] is None, x[5] if x[5] is not None else 1.0))
for nombre, celda, n, neto, hit, p, pf, indep, tier in filas[:25]:
    pv = p if p is not None else 1.0
    sig = "✓" if pv < 0.05 else ("~" if pv < 0.10 else "")
    pfs = f"{pf:>5.2f}" if pf is not None else "  inf"
    ps = f"{pv:>8.4f}" if p is not None else "     n/a"
    print(f"{nombre:>16s} {celda:>11s} | {n:>4d} {neto*100:>+6.2f}% {hit:>5.0%} {ps} {pfs} {indep:>5.0%} {tier:>9s} {sig}")

n_sig = sum(1 for f in filas if f[5] is not None and f[5] < 0.05)
n_marg = sum(1 for f in filas if f[5] is not None and 0.05 <= f[5] < 0.10)
print(f"\nSignificativas (p<0.05): {n_sig} | Marginales (p<0.10): {n_marg} | Celdas evaluadas: {len(filas)}")

import json
out = ROOT / "data/research/signals/senales_d3_candidatas.json"
out.write_text(json.dumps({"fecha": str(pd.Timestamp.now()),
                           "resultados": resultados}, indent=2, ensure_ascii=False, default=str))
print(f"Guardado: {out}")
