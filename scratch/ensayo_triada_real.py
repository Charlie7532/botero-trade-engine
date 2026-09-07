#!/usr/bin/env python3
import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))
from evaluador_general import cargar_entorno_evaluacion, evaluar_condicion_booleana, build_episodes, SLOT_ORDER

def calcular_esquema_triada(estacion: str, state_key: str):
    lake, quants = cargar_entorno_evaluacion()
    col = f"{estacion}_sk"
    if col not in lake.columns:
        raise ValueError(f"Columna {col} no existe en el lake")

    mask = (lake[col] == state_key).values.astype(bool)
    n_barras = int(mask.sum())
    if n_barras == 0:
        raise ValueError(f"No hay barras activas para {state_key}")

    # Población básica
    lake_idx = pd.DatetimeIndex(lake.index).normalize()
    episodes = build_episodes(mask, lake_idx)
    n_episodes = len(episodes)
    durations = [ep["duration_bars"] for ep in episodes]

    poblacion = {
        "barras": n_barras,
        "fire_rate_pct": round(float(n_barras / len(lake) * 100), 2),
        "n_episodios": n_episodes,
        "duracion_media": round(float(np.mean(durations)), 2) if durations else 0.0,
        "duracion_max": int(np.max(durations)) if durations else 0
    }

    # Evaluar como MIN (suelos)
    res_min = evaluar_condicion_booleana(mask, nombre=f"{estacion}_{state_key}", blanco="MIN")
    tc_min = res_min["timing_canonico"]
    rs_min = res_min["rendimiento_por_slot"]
    fp_min = res_min["escalas_zigzag"]

    slots_min = {}
    for s in SLOT_ORDER:
        cnt = tc_min["counts"].get(s, 0)
        pct = tc_min["pcts"].get(s, 0.0)
        perf = rs_min.get(s, {})
        slots_min[s] = {
            "n": cnt,
            "pct": pct,
            "hit_rate": perf.get("hit_rate"),
            "ev": perf.get("ev"),
            "bars": perf.get("bars_medio")
        }

    first_passage_min = {}
    for esc in ["zz25", "zz50", "zz75"]:
        e_data = fp_min.get(esc, {})
        first_passage_min[esc] = {
            "hit_rate": e_data.get("hit_rate"),
            "p_value": e_data.get("p_value_binom"),
            "ev": e_data.get("ev"),
            "profit_factor": e_data.get("profit_factor"),
            "mae_medio": e_data.get("mae_medio"),
            "mae_p90": e_data.get("mae_p90"),
            "mfe_medio": e_data.get("mfe_medio"),
            "mfe_p90": e_data.get("mfe_p90"),
            "bars_medio": e_data.get("bars_medio")
        }

    medicion_min = {
        "resumen_rango": {
            "n_en_rango": tc_min["n_en_rango"],
            "pct_en_rango": tc_min["pct_en_rango"],
            "delta_medio": tc_min["delta_medio"],
            "delta_mediana": tc_min["delta_mediana"]
        },
        "slots": slots_min,
        "first_passage": first_passage_min
    }

    # Evaluar como MAX (techos)
    res_max = evaluar_condicion_booleana(mask, nombre=f"{estacion}_{state_key}", blanco="MAX")
    tc_max = res_max["timing_canonico"]
    rs_max = res_max["rendimiento_por_slot"]
    fp_max = res_max["escalas_zigzag"]

    slots_max = {}
    for s in SLOT_ORDER:
        cnt = tc_max["counts"].get(s, 0)
        pct = tc_max["pcts"].get(s, 0.0)
        perf = rs_max.get(s, {})
        slots_max[s] = {
            "n": cnt,
            "pct": pct,
            "hit_rate": perf.get("hit_rate"),
            "ev": perf.get("ev"),
            "bars": perf.get("bars_medio")
        }

    first_passage_max = {}
    for esc in ["zz25", "zz50", "zz75"]:
        e_data = fp_max.get(esc, {})
        first_passage_max[esc] = {
            "hit_rate": e_data.get("hit_rate"),
            "p_value": e_data.get("p_value_binom"),
            "ev": e_data.get("ev"),
            "profit_factor": e_data.get("profit_factor"),
            "mae_medio": e_data.get("mae_medio"),
            "mae_p90": e_data.get("mae_p90"),
            "mfe_medio": e_data.get("mfe_medio"),
            "mfe_p90": e_data.get("mfe_p90"),
            "bars_medio": e_data.get("bars_medio")
        }

    medicion_max = {
        "resumen_rango": {
            "n_en_rango": tc_max["n_en_rango"],
            "pct_en_rango": tc_max["pct_en_rango"],
            "delta_medio": tc_max["delta_medio"],
            "delta_mediana": tc_max["delta_mediana"]
        },
        "slots": slots_max,
        "first_passage": first_passage_max
    }

    return {
        state_key: {
            "poblacion": poblacion,
            "medicion_min": medicion_min,
            "medicion_max": medicion_max
        }
    }

if __name__ == "__main__":
    estacion = sys.argv[1] if len(sys.argv) > 1 else "vix"
    sk = sys.argv[2] if len(sys.argv) > 2 else "4__3__2"
    resultado = calcular_esquema_triada(estacion, sk)
    print(json.dumps(resultado, indent=2))
