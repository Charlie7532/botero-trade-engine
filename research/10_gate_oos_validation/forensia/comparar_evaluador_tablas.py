#!/usr/bin/env python3
"""
COMPARADOR EVALUADOR: tabla original vs tabla nueva (quants_obs)
==================================================================
Corre el evaluador vela-a-vela completo sobre ambas tablas y compara
edge neto, hit rate y p-value por celda escala×régimen.

Uso (una tabla por proceso, por el cache global del evaluador):
  PYTHONPATH=/root/botero-trade backend/.venv/bin/python \
    scratch/comparar_evaluador_tablas.py <ruta_pickle> <out_json>
"""
import sys
import json
from pathlib import Path

import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))


def main():
    pickle_path = Path(sys.argv[1]).resolve()
    out_path = Path(sys.argv[2]).resolve()
    print(f"[i] Tabla: {pickle_path.name}")

    # Inyectar la tabla antes de importar el evaluador (cache global)
    import arnes.datos as datos_mod
    datos_mod.OBS_PKL = pickle_path

    import importlib
    import evaluador_vela_a_vela as evv
    importlib.reload(evv)  # asegurar que toma el OBS_PKL nuevo
    evv._CACHE["df"] = None  # reset cache

    from arnes import SEÑALES

    # Mismo protocolo que el __main__ del evaluador (rescatadas + re-evaluación)
    RESCATADAS = {"skew_paranoia_exit"}
    REEVALUAR = ["breadth_contraction_exit", "credit_ease_exit",
                 "regime_change_exit", "skew_paranoia_exit"]

    reporte = {}
    filas_ranking = []

    def mejor_celda(r):
        mejor = None
        for celda, p in r["perfil_3d_régimen"].items():
            if p["n"] < 5:
                continue
            if mejor is None or p["fav_neto"] > r["perfil_3d_régimen"][mejor]["fav_neto"]:
                mejor = celda
        return mejor

    for nombre in sorted(SEÑALES.keys()):
        try:
            r = evv.evaluar(nombre, reevaluar=(nombre in RESCATADAS))
        except Exception as e:
            reporte[nombre] = {"status": "ERROR", "razon": str(e)[:120]}
            print(f"  {nombre:>28s}: ERROR {str(e)[:60]}", flush=True)
            continue
        reporte[nombre] = r
        st = r.get("status")
        print(f"  {nombre:>28s}: {st}", flush=True)
        if st != "OK":
            continue
        mc = mejor_celda(r)
        if mc:
            p = r["perfil_3d_régimen"][mc]
            filas_ranking.append({
                "señal": nombre, "celda": mc, "n": p["n"], "diamante": p["diamante"],
                "tier": p["confidence_tier"], "hit": p["hit_rate"],
                "hit_neto": p["hit_neto"], "fav_neto": p["fav_neto"],
                "p": p["p_value"], "pf": p["profit_factor"],
                "ev_bar": p["ev_por_barra"], "bars": p["bars_medio"],
                "indep": r["forensia_F3"].get("independencia"),
            })

    print(f"\n{'='*100}\nRE-EVALUACIÓN de señales retiradas", flush=True)
    for nombre in REEVALUAR:
        try:
            r = evv.evaluar(nombre, reevaluar=True)
        except Exception as e:
            reporte[f"REEVAL_{nombre}"] = {"status": "ERROR", "razon": str(e)[:120]}
            continue
        reporte[f"REEVAL_{nombre}"] = r
        st = r.get("status")
        print(f"  {nombre:>28s}: {st}", flush=True)
        if st != "OK":
            continue
        mc = mejor_celda(r)
        if mc:
            p = r["perfil_3d_régimen"][mc]
            filas_ranking.append({
                "señal": f"REEVAL_{nombre}", "celda": mc, "n": p["n"],
                "diamante": p["diamante"], "tier": p["confidence_tier"],
                "hit": p["hit_rate"], "hit_neto": p["hit_neto"],
                "fav_neto": p["fav_neto"], "p": p["p_value"],
                "pf": p["profit_factor"], "ev_bar": p["ev_por_barra"],
                "bars": p["bars_medio"],
                "indep": r["forensia_F3"].get("independencia"),
            })

    out_path.write_text(json.dumps({"ranking": filas_ranking, "reporte": reporte},
                                   indent=1, ensure_ascii=False, default=str))
    print(f"\n[✓] Guardado: {out_path}")


if __name__ == "__main__":
    main()
