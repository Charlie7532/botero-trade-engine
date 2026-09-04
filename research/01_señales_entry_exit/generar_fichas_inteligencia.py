#!/usr/bin/env python3
"""Generar fichas de inteligencia unitarias por señal — datos que YA existen."""
import json, os, sys
import numpy as np
from scipy.stats import beta

sys.path.insert(0, "/root/botero-trade/research/01_señales_entry_exit")
sys.path.insert(0, "/root/botero-trade")

LAKE = json.load(open("/root/botero-trade/data/research/signals/evaluacion_generalizada_lake.json"))
VAV = json.load(open("/root/botero-trade/data/research/signals/evaluacion_vela_a_vela_v7_final.json"))
RANK = json.load(open("/root/botero-trade/data/research/signals/ranking_maestro.json"))

OUTDIR = "/root/botero-trade/data/research/intelligence/senales"
os.makedirs(OUTDIR, exist_ok=True)

ranking_list = RANK.get("ranking", [])
meta_rank = RANK.get("metadata", {})
multiple_testing = meta_rank.get("multiple_testing", {})

def _ci95(hits, n):
    if n <= 0 or hits is None:
        return None, None
    lo = beta.ppf(0.025, hits, n - hits + 1)
    hi = beta.ppf(0.975, hits + 1, n - hits)
    return round(float(lo), 4), round(float(hi), 4)

def _calcular_drawdown(fav_series):
    """Calcula drawdown desde una serie de retornos favorables."""
    favs = np.array(fav_series)
    if len(favs) < 5:
        return {"max_drawdown": None, "max_consecutive_losses": None}
    cum = np.cumprod(1 + favs)
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    max_dd = float(dd.min())
    # Rachas de perdidas
    losses = (favs < 0).astype(int)
    streaks = np.diff(np.concatenate(([0], losses, [0])))
    starts = np.where(streaks == 1)[0]
    ends = np.where(streaks == -1)[0]
    max_streak = int((ends - starts).max()) if len(starts) > 0 and len(ends) > 0 else 0
    avg_win = float(favs[favs > 0].mean()) if (favs > 0).any() else 0
    avg_loss = float(favs[favs < 0].mean()) if (favs < 0).any() else 0
    return {
        "max_drawdown": round(max_dd, 4),
        "max_consecutive_losses": max_streak,
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4)
    }

senal_count = 0
for entry in ranking_list:
    s_name = entry.get("senal", "")
    if not s_name:
        continue
    
    # Datos del evaluador general (lake)
    r_lake = LAKE.get(s_name, {})
    if not isinstance(r_lake, dict):
        continue
    
    poblacion = r_lake.get("poblacion", {})
    tc = r_lake.get("timing_canonico", {})
    rs = r_lake.get("rendimiento_por_slot", {})
    escalas = r_lake.get("escalas_zigzag", {})
    score = entry.get("score_compuesto")
    rol = entry.get("rol_operacional", "")
    
    # Datos del VAV
    r_vav = VAV.get(s_name, {})
    perfil = r_vav.get("perfil_3d_régimen", {}) if isinstance(r_vav, dict) else {}
    ts_vav = r_vav.get("timing_slots", {}) if isinstance(r_vav, dict) else {}
    f3 = r_vav.get("forensia_F3", {}) if isinstance(r_vav, dict) else {}
    
    # Confiabilidad desde ranking
    p_bh = entry.get("p_BH")
    p_bonf = entry.get("p_bonferroni")
    sig_bh = entry.get("significativo_BH", False)
    
    # Clasificar precision temporal
    ant = tc.get("pct_anticipada", 0)
    exa = tc.get("pct_exacta", 0)
    ret = tc.get("pct_retrasada", 0)
    fue = tc.get("pct_fuera", 0)
    
    if ant > exa and ant > ret:
        precision = "ANTICIPADORA"
    elif exa > ant and exa > ret:
        precision = "COINCIDENTE"
    elif ret > ant and ret > exa:
        precision = "CONFIRMADORA"
    elif fue > 50:
        precision = "SIN_ALINEACION"
    else:
        precision = "MIXTA"
    
    # Drawdown (desde favorable de zz25)
    fav_series = []
    for esc_data in escalas.values():
        if isinstance(esc_data, dict) and "ev" in esc_data:
            fav_series.append(esc_data["ev"])
    dd_info = _calcular_drawdown(fav_series) if fav_series else {}

    # CI95 para mejor escala
    best_scale = None
    best_hr = -1
    for esc_name, esc_data in escalas.items():
        if isinstance(esc_data, dict):
            hr_val = esc_data.get("hit_rate", 0) or 0
            if hr_val > best_hr:
                best_hr = hr_val
                best_scale = esc_name
    ci95_lo, ci95_hi = None, None
    if best_scale and best_scale in escalas:
        ed = escalas[best_scale]
        n_val = ed.get("n", 0)
        hr_val = ed.get("hit_rate", 0)
        if n_val > 0 and hr_val is not None:
            ci95_lo, ci95_hi = _ci95(round(hr_val * n_val), n_val)
    
    # Slot detail
    slots_detail = {}
    for slot_label in ["t-2", "t-1", "t=0", "t+1", "t+2", "ENTRE"]:
        sr = rs.get(slot_label, {})
        if sr and sr.get("n", 0) > 0:
            slots_detail[slot_label] = {
                "n": sr["n"],
                "hit_rate": sr.get("hit_rate"),
                "ev": sr.get("ev"),
                "bars_medio": sr.get("bars_medio")
            }
    
    # Perfil regimen detail
    regimen_detail = {}
    for celda, data in perfil.items():
        if isinstance(data, dict) and data.get("n", 0) > 0:
            regimen_detail[celda] = {
                "n": data["n"],
                "hit_rate": data.get("hit_rate"),
                "fav_neto": data.get("fav_neto"),
                "p_value": data.get("p_value"),
                "profit_factor": data.get("profit_factor")
            }
    
    # Escalas detail
    escalas_detail = {}
    for esc_name, esc_data in escalas.items():
        if isinstance(esc_data, dict):
            escalas_detail[esc_name] = {
                "n": esc_data["n"],
                "hit_rate": esc_data.get("hit_rate"),
                "hit_neto": esc_data.get("hit_neto"),
                "ev_neto": esc_data.get("ev_neto"),
                "profit_factor": esc_data.get("profit_factor"),
                "mae_medio": esc_data.get("mae_medio"),
                "mfe_medio": esc_data.get("mfe_medio"),
                "bars_medio": esc_data.get("bars_medio"),
                "p_value_binom": esc_data.get("p_value_binom")
            }
    
    # Ficha
    ficha = {
        "_meta": {
            "fecha": "2026-09-03",
            "version": "2.0-homologada",
            "fuentes": [
                "evaluacion_generalizada_lake.json",
                "evaluacion_vela_a_vela_v7_final.json",
                "ranking_maestro.json"
            ]
        },
        "senal": s_name,
        "tipo": entry.get("tipo", r_lake.get("tipo", "")),
        "blanco": entry.get("blanco", r_lake.get("blanco", "")),
        "version": "2.0-homologada",
        
        "poblacion": {
            "n_episodios": poblacion.get("n_episodios"),
            "n_barras_totales": poblacion.get("total_barras_activas"),
            "fire_rate_pct": poblacion.get("fire_rate_pct"),
            "cadencia_1_en_n_barras": poblacion.get("cadencia_1_en_n_barras"),
            "duracion_episodio_barras": poblacion.get("duracion_episodio", {}),
            "es_diamante": poblacion.get("es_diamante"),
            "tier_rareza": poblacion.get("tier_rareza")
        },
        
        "timing": {
            "precision": precision,
            "pct_en_rango": tc.get("pct_en_rango"),
            "pct_fuera_de_rango": tc.get("pct_fuera"),
            "delta_medio_barras": tc.get("delta_medio"),
            "delta_mediana_barras": tc.get("delta_mediana"),
            "por_slot": slots_detail,
            "perfil_agregado": {
                "anticipadora_t2_t1_pct": ant,
                "coincidente_t0_pct": exa,
                "confirmadora_t1_t2_pct": ret,
                "fuera_rango_pct": fue
            }
        },
        
        "first_passage": {
            "escalas": escalas_detail,
            "escala_optima": r_lake.get("escala_optima", best_scale),
            "ci95_hit_rate_mejor_escala": [ci95_lo, ci95_hi]
        },
        
        "perfil_regimen_pivotes": regimen_detail,
        
        "drawdown_y_riesgo": dd_info,
        
        "confiabilidad": {
            "p_value_binom_mejor_escala": best_scale and escalas.get(best_scale, {}).get("p_value_binom"),
            "p_BH": p_bh,
            "p_bonferroni": p_bonf,
            "significativo_BH": sig_bh,
            "independencia_F3": f3.get("independencia"),
            "techo_mejora_F3": f3.get("techo_mejora"),
            "score_compuesto": score,
            "rol_institucional": rol
        },
        
        "score_compuesto": score,
        "rol": rol
    }
    
    # Guardar
    outpath = os.path.join(OUTDIR, f"{s_name}.json")
    with open(outpath, "w") as f:
        json.dump(ficha, f, indent=2)
    senal_count += 1

# Resumen ejecutivo
resumen = {
    "_meta": {
        "fecha": "2026-09-03",
        "total_senales": senal_count,
        "fuentes": ["evaluacion_generalizada_lake.json", "evaluacion_vela_a_vela_v7_final.json", "ranking_maestro.json"]
    },
    "distribucion_precision": {},
    "distribucion_roles": meta_rank.get("distribucion_roles", {}),
    "multiple_testing": {
        "n_pass_BH": multiple_testing.get("n_pass_BH_005"),
        "n_pass_bonferroni": multiple_testing.get("n_pass_bonferroni_005"),
        "dsr_pasa": multiple_testing.get("dsr_passes", False),
        "dsr_delta": multiple_testing.get("dsr_delta")
    }
}

# Precision counts
precision_counts = {}
for entry in ranking_list:
    s_name = entry.get("senal", "")
    fpath = os.path.join(OUTDIR, f"{s_name}.json")
    if os.path.exists(fpath):
        f = json.load(open(fpath))
        p = f.get("timing", {}).get("precision", "?")
        precision_counts[p] = precision_counts.get(p, 0) + 1
resumen["distribucion_precision"] = precision_counts

# Top 10
resumen["top_10_score"] = []
for entry in ranking_list[:10]:
    resumen["top_10_score"].append({
        "senal": entry["senal"],
        "score": entry.get("score_compuesto"),
        "rol": entry.get("rol_operacional"),
        "p_BH": entry.get("p_BH"),
        "significativo_BH": entry.get("significativo_BH", False)
    })

with open(os.path.join(OUTDIR, "resumen_ejecutivo.json"), "w") as f:
    json.dump(resumen, f, indent=2)

print(f"✅ {senal_count} fichas generadas en {OUTDIR}")
print(f"   Resumen ejecutivo: {os.path.join(OUTDIR, 'resumen_ejecutivo.json')}")
print(f"   Distribucion precision: {precision_counts}")
print(f"   BH significativas: {resumen['multiple_testing']['n_pass_BH']}/{senal_count}")
print(f"   DSR: {'PASA' if resumen['multiple_testing']['dsr_pasa'] else 'FALLA'} (delta={resumen['multiple_testing']['dsr_delta']})")