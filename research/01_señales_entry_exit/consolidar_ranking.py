#!/usr/bin/env python3
"""
Consolidador y Generador de Ranking Maestro Cross-Evaluador
===========================================================
Cruza los resultados de:
  1. Evaluador General Continuo (`evaluacion_generalizada_lake.json` - 8,453 barras)
  2. Evaluador Forense Vela a Vela (`evaluacion_vela_a_vela_v7_final.json` - 1,354 pivotes)

Clasifica cada señal en el cuadrante institucional:
  - TACTICA_RAPIDA: Edge concentrado en escala rápida (zz25 / <= 10 velas)
  - ESTRUCTURAL: Edge de fondo/tendencia en escala macro (zz75 / multi-semana)
  - DIAMANTE_COLA: Eventos raros de alta convexidad (N < 21 episodios / rareza §3.3)
  - FILTRO_FONDO: Señales de alta frecuencia (cadencia < 10v / régimen ambiental)

Correcciones aplicadas (1-Sep-2026):
  C6:  Bonferroni y Benjamini-Hochberg (BH) p-value adjustments
  C19: Score separado por categoría en tabla resumen

Produce el artefacto `data/research/signals/ranking_maestro.json`.
"""

import json
from pathlib import Path
from typing import Dict, Any, List
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
DIR_SIGNALS = ROOT / "data" / "research" / "signals"
FILE_LAKE = DIR_SIGNALS / "evaluacion_generalizada_lake.json"
FILE_VAV = DIR_SIGNALS / "evaluacion_vela_a_vela_v7_final.json"
FILE_OUT = DIR_SIGNALS / "ranking_maestro.json"


def cargar_reportes() -> tuple[Dict[str, Any], Dict[str, Any]]:
    if not FILE_LAKE.exists():
        raise FileNotFoundError(f"Falta archivo de lake: {FILE_LAKE}")
    if not FILE_VAV.exists():
        raise FileNotFoundError(f"Falta archivo de pivotes: {FILE_VAV}")
    
    with open(FILE_LAKE) as f:
        lake_data = json.load(f)
    with open(FILE_VAV) as f:
        vav_data = json.load(f)
    return lake_data, vav_data


def clasificar_rol_operacional(
    lake_sig: Dict[str, Any],
    vav_sig: Dict[str, Any]
) -> tuple[str, str]:
    """Determina la categoría institucional y escala óptima."""
    pob = lake_sig.get("poblacion", {})
    escalas = lake_sig.get("escalas_zigzag", {})
    z25 = escalas.get("zz25", {})
    z75 = escalas.get("zz75", {})

    n_episodes = pob.get("n_episodios", 0)
    cadencia = pob.get("cadencia_1_en_n_barras") or 9999
    is_diamante = pob.get("es_diamante", False)
    is_fondo = pob.get("es_fondo", False) or cadencia < 10

    best_scale = lake_sig.get("escala_optima", "zz25")

    ev25 = z25.get("ev", 0.0) or 0.0
    ev75 = z75.get("ev", 0.0) or 0.0

    if is_diamante or (0 < n_episodes < 21):
        rol = "DIAMANTE_COLA"
    elif is_fondo:
        rol = "FILTRO_FONDO"
    elif best_scale == "zz75" or (ev75 > ev25 and ev75 > 0.015):
        rol = "ESTRUCTURAL"
    else:
        rol = "TACTICA_RAPIDA"

    return rol, best_scale


def _benjamini_hochberg(p_values: List[float], q: float = 0.05) -> List[float]:
    """Benjamini-Hochberg FDR adjustment. Returns adjusted p-values."""
    n = len(p_values)
    if n == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    adjusted = [0.0] * n
    prev_adj = 1.0
    for rank_idx in range(n - 1, -1, -1):
        orig_idx, p = indexed[rank_idx]
        adj = min(p * n / (rank_idx + 1), prev_adj)
        adjusted[orig_idx] = min(adj, 1.0)
        prev_adj = adjusted[orig_idx]
    return adjusted


def construir_ranking_maestro() -> Dict[str, Any]:
    lake_data, vav_data = cargar_reportes()
    
    todas_senales = sorted(set(list(lake_data.keys()) + [k for k in vav_data.keys() if not k.startswith("REEVAL_")]))
    filas = []

    for name in todas_senales:
        l_res = lake_data.get(name, {})
        v_res = vav_data.get(name, {})
        
        if not l_res:
            continue

        pob = l_res.get("poblacion", {})
        tim = l_res.get("timing_canonico", {})
        esc = l_res.get("escalas_zigzag", {})
        
        z25 = esc.get("zz25", {})
        z50 = esc.get("zz50", {})
        z75 = esc.get("zz75", {})

        rol, best_scale = clasificar_rol_operacional(l_res, v_res)

        # Extraer métricas de mejor celda en evaluador vela-a-vela si existe
        vav_best_celda = None
        vav_fav_neto = None
        vav_hit_neto = None
        vav_p_val = None
        vav_indep = None

        if v_res and "perfil_3d_régimen" in v_res:
            perfil = v_res["perfil_3d_régimen"]
            valid_cells = [c for c, p in perfil.items() if p.get("n", 0) >= 10]
            if valid_cells:
                best_c = max(valid_cells, key=lambda c: perfil[c].get("fav_neto", -999))
                vav_best_celda = best_c
                vav_fav_neto = perfil[best_c].get("fav_neto")
                vav_hit_neto = perfil[best_c].get("hit_neto")
                vav_p_val = perfil[best_c].get("p_value")
                vav_indep = v_res.get("forensia_F3", {}).get("independencia")

        # Composite score: combinación de hit neto lake + timing + EV neto
        best_esc_obj = esc.get(best_scale, {})
        ev_neto = best_esc_obj.get("ev_neto", 0.0) or 0.0
        hit_rate = best_esc_obj.get("hit_rate", 0.5) or 0.5
        hit_neto = best_esc_obj.get("hit_neto", 0.0) or 0.0
        en_rango = tim.get("pct_en_rango", 0.0) / 100.0

        score_compuesto = round(float(ev_neto * 100 + hit_neto * 50 + en_rango * 10), 3)

        # Extract p-value from best scale (C6)
        p_value_raw = best_esc_obj.get("p_value_binom")
        if p_value_raw is None:
            p_value_raw = 1.0

        filas.append({
            "senal": name,
            "tipo": l_res.get("tipo", "entry"),
            "blanco": l_res.get("blanco", "MIN"),
            "rol_operacional": rol,
            "escala_optima": best_scale,
            "score_compuesto": score_compuesto,
            "p_value_raw": round(float(p_value_raw), 6),
            "poblacion": {
                "n_episodios": pob.get("n_episodios"),
                "fire_rate_pct": pob.get("fire_rate_pct"),
                "cadencia_barras": pob.get("cadencia_1_en_n_barras"),
                "duracion_mediana_barras": pob.get("duracion_episodio", {}).get("median"),
                "tier_rareza": pob.get("tier_rareza"),
                "es_diamante": pob.get("es_diamante", False),
                "es_fondo": pob.get("es_fondo", False),
            },
            "timing": {
                "en_rango_pct": tim.get("pct_en_rango"),
                "anticipada_pct": tim.get("pct_anticipada"),
                "exacta_pct": tim.get("pct_exacta"),
                "retrasada_pct": tim.get("pct_retrasada"),
                "delta_medio_barras": tim.get("delta_medio"),
            },
            "rendimiento_lake": {
                "hit_rate_optimo": round(hit_rate, 4),
                "hit_neto_optimo": round(hit_neto, 4),
                "ev_optimo": round(best_esc_obj.get("ev", 0.0), 4) if best_esc_obj.get("ev") is not None else None,
                "ev_neto_optimo": round(ev_neto, 4),
                "profit_factor_optimo": best_esc_obj.get("profit_factor"),
                "mae_medio": best_esc_obj.get("mae_medio"),
                "mae_p10": best_esc_obj.get("mae_p10"),
                "mfe_medio": best_esc_obj.get("mfe_medio"),
            },
            "rendimiento_pivotes_vav": {
                "mejor_celda": vav_best_celda,
                "fav_neto": vav_fav_neto,
                "hit_neto": vav_hit_neto,
                "p_value": vav_p_val,
                "independencia_f3": vav_indep,
            }
        })

    # Sort ranking by score_compuesto descending
    filas.sort(key=lambda x: x["score_compuesto"], reverse=True)

    # C6: Bonferroni + Benjamini-Hochberg adjustments
    n_signals = len(filas)
    raw_pvals = [f["p_value_raw"] for f in filas]
    bh_adjusted = _benjamini_hochberg(raw_pvals, q=0.05)

    for i, f in enumerate(filas):
        f["p_bonferroni"] = round(min(f["p_value_raw"] * n_signals, 1.0), 6)
        f["p_BH"] = round(bh_adjusted[i], 6)
        f["significativo_bonferroni"] = bool(f["p_bonferroni"] < 0.05)
        f["significativo_BH"] = bool(f["p_BH"] < 0.05)

    # DSR metadata
    z_scores = []
    for f in filas:
        p = f["p_value_raw"]
        if 0 < p < 1:
            from scipy.stats import norm
            z_scores.append(abs(norm.ppf(p)))
    max_z = max(z_scores) if z_scores else 0.0
    n_tests = len(z_scores)
    expected_max_z = np.sqrt(2 * np.log(n_tests)) - (np.log(np.log(n_tests)) + np.log(4 * np.pi)) / (2 * np.sqrt(2 * np.log(n_tests))) if n_tests > 1 else 0.0
    dsr = max_z - expected_max_z

    n_pass_bonf = sum(1 for f in filas if f["significativo_bonferroni"])
    n_pass_bh = sum(1 for f in filas if f["significativo_BH"])

    ranking_maestro = {
        "metadata": {
            "version": "2.0-corregida",
            "total_senales_evaluadas": len(filas),
            "distribucion_roles": {
                "TACTICA_RAPIDA": len([f for f in filas if f["rol_operacional"] == "TACTICA_RAPIDA"]),
                "ESTRUCTURAL": len([f for f in filas if f["rol_operacional"] == "ESTRUCTURAL"]),
                "DIAMANTE_COLA": len([f for f in filas if f["rol_operacional"] == "DIAMANTE_COLA"]),
                "FILTRO_FONDO": len([f for f in filas if f["rol_operacional"] == "FILTRO_FONDO"]),
            },
            "multiple_testing": {
                "n_tests": n_signals,
                "n_pass_bonferroni_005": n_pass_bonf,
                "n_pass_BH_005": n_pass_bh,
                "dsr_delta": round(dsr, 3),
                "max_z_observed": round(max_z, 3),
                "expected_max_z_H0": round(expected_max_z, 3),
                "dsr_passes": dsr > 0,
            }
        },
        "ranking": filas
    }

    FILE_OUT.parent.mkdir(parents=True, exist_ok=True)
    def _default(o):
        if isinstance(o, (np.bool_, np.integer)):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    FILE_OUT.write_text(json.dumps(ranking_maestro, indent=2, ensure_ascii=False, default=_default))
    return ranking_maestro


def imprimir_tabla_resumen(rm: Dict[str, Any]):
    filas = rm["ranking"]
    meta = rm["metadata"]
    mt = meta.get("multiple_testing", {})

    print("\n" + "=" * 145)
    print("RANKING MAESTRO CROSS-EVALUADOR v2.0 (Lake Continuo 8,453v + Forense Pivotes 1,354p)")
    print("=" * 145)

    print(f"\n  📊 Multiple Testing: {mt.get('n_tests',0)} señales | "
          f"Bonferroni: {mt.get('n_pass_bonferroni_005',0)} pasan | "
          f"BH(q=0.05): {mt.get('n_pass_BH_005',0)} pasan | "
          f"DSR: {'✅ PASA' if mt.get('dsr_passes') else '❌ FALLA'} (Δ={mt.get('dsr_delta',0):+.3f})")

    # C19: Print by category
    for rol in ["TACTICA_RAPIDA", "ESTRUCTURAL", "DIAMANTE_COLA", "FILTRO_FONDO"]:
        grupo = [f for f in filas if f["rol_operacional"] == rol]
        if not grupo:
            continue

        print(f"\n  ─── {rol} ({len(grupo)} señales) ───")
        print(f"  {'#':<3s} | {'Señal':<30s} | {'Tipo':<5s} | {'Best':>4s} | "
              f"{'Score':>6s} | {'N(Ep)':>5s} {'Cad':>5s} | {'Hit%':>5s} {'ΔHit%':>6s} {'EV Neto':>7s} | "
              f"{'p_raw':>7s} {'p_BH':>7s} {'BH?':>3s}")
        print("  " + "-" * 115)

        for i, f in enumerate(grupo, 1):
            pob = f["poblacion"]
            rlk = f["rendimiento_lake"]

            dia = "💎" if pob["es_diamante"] else ""
            cad = f"{pob['cadencia_barras']:.0f}v" if pob["cadencia_barras"] else "-"
            hit = f"{rlk['hit_rate_optimo']:.0%}"
            dhit = f"{rlk['hit_neto_optimo']:+.1%}"
            evn = f"{rlk['ev_neto_optimo']:+.2%}"
            p_raw = f"{f['p_value_raw']:.4f}"
            p_bh = f"{f['p_BH']:.4f}"
            bh_pass = "✅" if f["significativo_BH"] else ""

            print(f"  {i:<3d} | {f['senal']+dia:<30s} | {f['tipo']:<5s} | {f['escala_optima']:>4s} | "
                  f"{f['score_compuesto']:>6.2f} | {pob['n_episodios']:>5d} {cad:>5s} | {hit:>5s} {dhit:>6s} {evn:>7s} | "
                  f"{p_raw:>7s} {p_bh:>7s} {bh_pass:>3s}")

    print("\n" + "=" * 145)
    print(f"✅ Ranking Maestro v2.0 guardado en: {FILE_OUT}\n")


if __name__ == "__main__":
    rm = construir_ranking_maestro()
    imprimir_tabla_resumen(rm)
