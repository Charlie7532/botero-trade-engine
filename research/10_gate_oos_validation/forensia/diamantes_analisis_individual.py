#!/usr/bin/env python3
"""
PROTOCOLO DIAMANTE §3.3 — Paso 4: análisis individual de ocurrencias
=====================================================================
panico_total (N=11) y skew_paranoia_exit (N=10) sobre la tabla nueva.
Para cada disparo: fecha, tipo de pivote, tríada dimensional, y cruce con:
  - episodios del régimen de crisis ±3σ (detector_regimen_crisis)
  - retorno de la pierna que arranca en el pivote (edge realizado)
"""
import sys
import json
from pathlib import Path

import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))

import arnes.datos as datos_mod  # noqa: E402
datos_mod.OBS_PKL = ROOT / "data/research/pivots/quants_obs_new.pkl"
from arnes import SEÑALES  # noqa: E402

df, spy = datos_mod.cargar_datos()

# Episodios de crisis del detector ±3σ
crisis_file = ROOT / "data/research/signals/regimen_crisis_diamantes.json"
episodios = []
if crisis_file.exists():
    cj = json.loads(crisis_file.read_text())
    episodios = cj.get("regimen", {}).get("episodios", [])
print(f"Episodios de crisis cargados: {len(episodios)}")

def en_crisis(fecha, ventana_dias=5):
    """¿La fecha cae dentro (±ventana) de algún episodio de crisis ±3σ?"""
    f = pd.Timestamp(fecha)
    for ep in episodios:
        try:
            ini = pd.Timestamp(ep.get("inicio"))
            fin = pd.Timestamp(ep.get("fin_real", ep.get("inicio")))
        except Exception:
            continue
        if ini - pd.Timedelta(days=ventana_dias) <= f <= fin + pd.Timedelta(days=ventana_dias):
            return True
    return False

# Retorno realizado de la pierna que arranca en cada pivote (SPY, duración propia)
prices = spy["close"].astype(float)
spy_idx = spy.close.index.normalize()

def retorno_realizado(fecha, dur_dias):
    pos = spy_idx.searchsorted(pd.Timestamp(fecha))
    if pos + 1 >= len(prices):
        return None
    # barra a ~dur_dias calendario adelante
    target = pd.Timestamp(fecha) + pd.Timedelta(days=max(dur_dias, 1))
    pos_end = spy_idx.searchsorted(target)
    pos_end = min(pos_end, len(prices) - 1)
    if pos_end <= pos:
        return None
    return float((prices.iloc[pos_end] / prices.iloc[pos] - 1) * 100)

resultados = {}
for señal in ["panico_total", "skew_paranoia_exit"]:
    mask = SEÑALES[señal](df).astype(bool)
    filas = df[mask]
    print(f"\n{'='*100}\nDIAMANTE: {señal} — {len(filas)} ocurrencias")
    print(f"{'='*100}")
    ocurrencias = []
    for _, row in filas.iterrows():
        fecha = row["pivot_date"]
        ptype = row["pivot_type"]
        vix_sk = str(row.get("vix_sk", ""))
        skew_sk = str(row.get("skew_sk", ""))
        dur = int(row.get("duration_bars", 1))
        ret = retorno_realizado(fecha, dur)
        crisis = en_crisis(fecha)
        o = {
            "fecha": str(pd.Timestamp(fecha).date()),
            "pivot_type": ptype,
            "vix_d1": vix_sk.split("__")[0] if vix_sk else None,
            "skew_d1": skew_sk.split("__")[0] if skew_sk else None,
            "skew_d3": skew_sk.split("__")[2] if skew_sk and len(skew_sk.split("__")) > 2 else None,
            "duracion_dias": dur,
            "retorno_pierna_pct": round(ret, 2) if ret is not None else None,
            "en_crisis_3sigma": crisis,
        }
        ocurrencias.append(o)
        print(f"  {o['fecha']} {ptype:>3} | VIX={str(o['vix_d1']):<20} "
              f"SKEW_D1={str(o['skew_d1']):<18} D3={str(o['skew_d3']):<28} "
              f"dur={dur:>3}d ret={str(o['retorno_pierna_pct']):>7}% crisis={crisis}")
    n_crisis = sum(1 for o in ocurrencias if o["en_crisis_3sigma"])
    print(f"\n  Resumen: {n_crisis}/{len(ocurrencias)} disparos dentro de régimen de crisis ±3σ")
    rets = [o["retorno_pierna_pct"] for o in ocurrencias if o["retorno_pierna_pct"] is not None]
    if rets:
        import numpy as np
        print(f"  Retorno de la pierna: media={np.mean(rets):+.2f}% "
              f"(positivo = el pivote fue piso/entrada alcista)")
    resultados[señal] = ocurrencias

out = ROOT / "data/research/signals/diamantes_analisis_individual.json"
out.write_text(json.dumps({"fecha": "2026-08-23",
                           "protocolo": "fact_store_v3 §3.3 paso 4",
                           "diamantes": resultados},
                          indent=1, ensure_ascii=False, default=str))
print(f"\n[✓] Guardado: {out}")
