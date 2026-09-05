# -*- coding: utf-8 -*-
"""
run_comite.py — Fase 5. Orquestador del Comité METAR Walk-Forward (end-to-end).

Pipeline:
  F1 episodios   : genera episodios (vista completa) sobre el lake.
  F2 agentes     : 11 agentes leen su estación en t (sin lookahead).
  F3 curador     : fusión probabilística (pesos ALTA=3/MEDIA=2/BAJA=1,
                   P(ALZA)/P(BAJA), contradicción, co-ocurrencias catálogo).
  F4 modelador   : walk-forward OOS; accuracy vs pivote real, lift, cobertura,
                   p binomial vs nulo 50%, validación temporal train/test.
  F5 entrega     : registro forense + reglas validadas/invalidadas +
                   modelo_confluencia.json + resumen.json.

Normativa: sin lookahead (el pivote real es SOLO scoring), inception respetada,
de-clustering = credibilidad (se procesan todos los episodios), confluencia
probabilística.

Uso (desde /root/botero-trade):
    backend/.venv/bin/python3 comite_metar/run_comite.py
    backend/.venv/bin/python3 comite_metar/run_comite.py --limit 200 --punto t0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # /root/botero-trade

from comite_metar.scripts import common, episodios as EP, estado_en as EE
from comite_metar.agentes._agente_base import Agente
from comite_metar.curador import modelador as MOD

VALID_MIN_N = 50        # §9.3: mínimo defensivo N>=50 para validar estación (anti-ruido n~30)
PASO_EDGE = 0.03        # hr debe superar baseline al menos +3pp (+0.03 aditivo)
OMEGA = 0.05            # §9.1: umbral estándar p < 0.05 (López de Prado, sin laxitud)


def _verificar_sin_lookahead(lake, episodios, n_muestras: int = 15) -> Dict:
    """Smoke test: comprueba que en una muestra aleatoria de episodios lake[:t0] es estricto."""
    n = min(n_muestras, len(episodios))
    ok = 0
    for ep in episodios[:n]:
        try:
            EE.assert_sin_lookahead(lake, ep["t0"])
            ok += 1
        except Exception:
            pass
    return {"n_verificados": n, "n_ok": ok,
            "sin_lookahead": ok == n}


def baselines_pivote_escala(frames: List[Dict], scale: str = "zz25") -> Dict[str, float]:
    """Calcula baseline_alza, baseline_baja y baseline_mayoritaria para una escala."""
    dirs = [
        f["pivote_real"][scale]["direccion"]
        for f in frames
        if f.get("pivote_real") and f["pivote_real"].get(scale, {}).get("resuelto")
    ]
    if not dirs:
        return {"baseline_alza": 0.5, "baseline_baja": 0.5, "baseline_mayoritaria": 0.5, "n_resueltos": 0}
    n_tot = len(dirs)
    n_a = dirs.count("ALZA")
    n_b = dirs.count("BAJA")
    p_a = n_a / n_tot
    p_b = n_b / n_tot
    return {
        "baseline_alza": round(p_a, 4),
        "baseline_baja": round(p_b, 4),
        "baseline_mayoritaria": round(max(p_a, p_b), 4),
        "n_resueltos": n_tot,
    }


def baseline_pivote(frames: List[Dict], scale: str = "zz25") -> float:
    """Baseline naive de clase mayoritaria en escala dada."""
    return baselines_pivote_escala(frames, scale)["baseline_mayoritaria"]


def benjamini_hochberg(p_values: List[Optional[float]]) -> List[Optional[float]]:
    """Ajuste Benjamini-Hochberg (FDR) sobre lista de p-values."""
    m = len(p_values)
    if m == 0:
        return []
    valid_entries = [(idx, p) for idx, p in enumerate(p_values) if p is not None]
    if not valid_entries:
        return [None] * m
    valid_entries.sort(key=lambda x: x[1])
    m_val = len(valid_entries)
    adj_map = {}
    min_adj = 1.0
    for rank in range(m_val, 0, -1):
        idx, p = valid_entries[rank - 1]
        val = min(1.0, p * m_val / rank)
        min_adj = min(min_adj, val)
        adj_map[idx] = round(min_adj, 6)

    return [adj_map.get(i) for i in range(m)]


def clasificar_estaciones(tally: Dict[str, Dict],
                          baselines_triada: Dict[str, Dict],
                          *,
                          min_n: int = VALID_MIN_N,
                          min_edge: float = PASO_EDGE,
                          alpha_fdr: float = OMEGA) -> Tuple[Dict, Dict, Dict]:
    """Evalúa cada estación por dirección y por cada escala (zz25, zz50, zz75) con FDR y CI95.

    Retorna: (validadas, invalidadas, todas)
    """
    estaciones_eval = {}
    test_entries = []  # lista de (estacion, escala, p_candidato)

    for est, t in tally.items():
        est_obj = {
            "estacion": est,
            "por_escala": {},
            "escala_optima": "zz25",
            "direccion_optima": "ALZA",
            "status": "INVALIDADA",
            "edge_optimo": None,
            "acc_optimo": None,
            "ci95_optimo": [None, None],
            "p_crudo_optimo": None,
            "p_BH_optimo": None,
            "baseline_optimo": None,
            "n_optimo": 0,
            "n_operacional_optimo": 0,
            "tipo_evaluacion_optima": "BRUTO",
            "razon": "",
        }

        mejor_p = 1.0
        mejor_sc = "zz25"
        mejor_dir = "ALZA"
        mejor_edge = -999.0
        mejor_acc = None
        mejor_ci = [None, None]
        mejor_base = 0.5
        mejor_n = 0
        mejor_n_op = 0
        mejor_tipo = "BRUTO"

        for sc in ("zz25", "zz50", "zz75"):
            sc_data = t.get("escalas", {}).get(sc, {})
            n_a = sc_data.get("n_alza", 0)
            h_a = sc_data.get("hits_alza", 0)
            n_b = sc_data.get("n_baja", 0)
            h_b = sc_data.get("hits_baja", 0)

            n_op_a = sc_data.get("n_op_alza", 0)
            h_op_a = sc_data.get("hits_op_alza", 0)
            n_op_b = sc_data.get("n_op_baja", 0)
            h_op_b = sc_data.get("hits_op_baja", 0)

            b_info = baselines_triada.get(sc, {"baseline_alza": 0.5, "baseline_baja": 0.5, "baseline_mayoritaria": 0.5})
            b_a = b_info.get("baseline_alza", 0.5)
            b_b = b_info.get("baseline_baja", 0.5)

            ed_bruto = MOD.edge_direccional(n_a, h_a, n_b, h_b, b_a, b_b)
            ed_op = MOD.edge_direccional(n_op_a, h_op_a, n_op_b, h_op_b, b_a, b_b)

            candidatos_sc = []
            for d_name, ed_dict, t_label in [("OPERACIONAL", ed_op, "OP"), ("BRUTO", ed_bruto, "BRUTO")]:
                if ed_dict["n_alza"] > 0 and ed_dict["edge_alza"] is not None:
                    candidatos_sc.append({
                        "dir": "ALZA", "tipo": d_name, "p": ed_dict["p_greater_alza"],
                        "edge": ed_dict["edge_alza"], "acc": ed_dict["accuracy_alza"],
                        "ci95": ed_dict["ci95_alza"], "base": b_a, "n": ed_dict["n_alza"],
                        "n_op": ed_op["n_alza"],
                    })
                if ed_dict["n_baja"] > 0 and ed_dict["edge_baja"] is not None:
                    candidatos_sc.append({
                        "dir": "BAJA", "tipo": d_name, "p": ed_dict["p_greater_baja"],
                        "edge": ed_dict["edge_baja"], "acc": ed_dict["accuracy_baja"],
                        "ci95": ed_dict["ci95_baja"], "base": b_b, "n": ed_dict["n_baja"],
                        "n_op": ed_op["n_baja"],
                    })

            cands_pos = [c for c in candidatos_sc if c["edge"] is not None and c["edge"] > 0 and c["p"] is not None]
            if cands_pos:
                cand_sc = min(cands_pos, key=lambda c: (c["p"], -c["edge"]))
            elif candidatos_sc:
                cand_sc = max(candidatos_sc, key=lambda c: c["edge"] if c["edge"] is not None else -999)
            else:
                cand_sc = {
                    "dir": "ALZA", "tipo": "BRUTO", "p": 1.0, "edge": 0.0,
                    "acc": 0.0, "ci95": [None, None], "base": b_a, "n": 0, "n_op": 0,
                }

            sc_summary = {
                "acc_alza": ed_bruto["accuracy_alza"],
                "acc_baja": ed_bruto["accuracy_baja"],
                "edge_alza": ed_bruto["edge_alza"],
                "edge_baja": ed_bruto["edge_baja"],
                "p_greater_alza": ed_bruto["p_greater_alza"],
                "p_greater_baja": ed_bruto["p_greater_baja"],
                "ci95_alza": ed_bruto["ci95_alza"],
                "ci95_baja": ed_bruto["ci95_baja"],
                "n_alza": ed_bruto["n_alza"],
                "n_baja": ed_bruto["n_baja"],
                "edge_operacional": ed_op,
                "edge_bruto": ed_bruto,
                "candidato_escala": cand_sc,
                "p_BH": None,
            }
            est_obj["por_escala"][sc] = sc_summary
            test_entries.append((est, sc, cand_sc["p"]))

            p_val = cand_sc["p"] if cand_sc["p"] is not None else 1.0
            if (p_val < mejor_p) or (p_val == mejor_p and cand_sc["edge"] > mejor_edge):
                mejor_p = p_val
                mejor_sc = sc
                mejor_dir = cand_sc["dir"]
                mejor_edge = cand_sc["edge"]
                mejor_acc = cand_sc["acc"]
                mejor_ci = cand_sc["ci95"]
                mejor_base = cand_sc["base"]
                mejor_n = cand_sc["n"]
                mejor_n_op = cand_sc["n_op"]
                mejor_tipo = cand_sc["tipo"]

        est_obj["escala_optima"] = mejor_sc
        est_obj["direccion_optima"] = mejor_dir
        est_obj["edge_optimo"] = mejor_edge
        est_obj["acc_optimo"] = mejor_acc
        est_obj["ci95_optimo"] = mejor_ci
        est_obj["p_crudo_optimo"] = mejor_p
        est_obj["baseline_optimo"] = mejor_base
        est_obj["n_optimo"] = mejor_n
        est_obj["n_operacional_optimo"] = mejor_n_op
        est_obj["tipo_evaluacion_optima"] = mejor_tipo
        estaciones_eval[est] = est_obj

    # §9.2: Benjamini-Hochberg FDR sobre las 33 comparaciones (11 estaciones x 3 escalas)
    p_vals_33 = [entry[2] for entry in test_entries]
    p_adj_33 = benjamini_hochberg(p_vals_33)

    for (est, sc, _), p_adj in zip(test_entries, p_adj_33):
        estaciones_eval[est]["por_escala"][sc]["p_BH"] = p_adj
        if sc == estaciones_eval[est]["escala_optima"]:
            estaciones_eval[est]["p_BH_optimo"] = p_adj

    # Clasificar en VALIDADA vs INVALIDADA
    validadas, invalidadas = {}, {}
    for est, obj in estaciones_eval.items():
        p_bh = obj["p_BH_optimo"]
        edge = obj["edge_optimo"]
        n_eval = obj["n_optimo"]
        ci_low = obj["ci95_optimo"][0]
        base = obj["baseline_optimo"]

        razones_rechazo = []
        if edge is None or edge < min_edge:
            razones_rechazo.append(f"edge {edge} < {min_edge}")
        if p_bh is None or p_bh >= alpha_fdr:
            razones_rechazo.append(f"p_BH {p_bh} >= {alpha_fdr} (p_crudo={obj['p_crudo_optimo']})")
        if n_eval < min_n:
            razones_rechazo.append(f"N insuficiente ({n_eval} < {min_n})")
        if ci_low is not None and ci_low <= base:
            razones_rechazo.append(f"CI95 inferior {ci_low} <= baseline {base}")

        if not razones_rechazo:
            obj["status"] = "VALIDADA"
            obj["razon"] = (f"Supera baseline {base:.2f} en escala {obj['escala_optima']} "
                            f"({obj['direccion_optima']}): acc={obj['acc_optimo']:.2f}, "
                            f"edge={edge:+.2%}, CI95={obj['ci95_optimo']}, "
                            f"p_BH={p_bh:.4f} < {alpha_fdr}, N={n_eval}")
            validadas[est] = obj
        else:
            obj["status"] = "INVALIDADA"
            obj["razon"] = "; ".join(razones_rechazo)
            invalidadas[est] = obj

    return validadas, invalidadas, estaciones_eval


def reglas_por_estacion(tally: Dict[str, Dict], baseline: Any) -> "tuple[Dict, Dict]":
    """Compatibilidad: clasifica estaciones recibiendo baseline float o baselines_triada dict."""
    if isinstance(baseline, dict):
        baselines_triada = baseline
    else:
        b_val = float(baseline) if baseline else 0.5
        baselines_triada = {
            sc: {"baseline_alza": 0.5, "baseline_baja": 0.5, "baseline_mayoritaria": b_val}
            for sc in ("zz25", "zz50", "zz75")
        }
    val, inv, _ = clasificar_estaciones(tally, baselines_triada)
    return val, inv


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Comité METAR walk-forward")
    ap.add_argument("--limit", type=int, default=None,
                    help="procesa solo los primeros N episodios")
    ap.add_argument("--punto", default="t0", choices=["t0", "nucleo_pos"])
    ap.add_argument("--horizon", type=int, default=MOD.HORIZONTE_DEFAULT)
    args = ap.parse_args()

    print("== Comité METAR — Walk-Forward (Fases 1-5 Canónico con Baseline Direccional) ==")
    lake = common.cargar_lake()
    perfiles = common.cargar_perfiles()
    print(f"Lake: {lake.shape} | {lake.index[0]} .. {lake.index[-1]}")

    # F1 episodios
    episodios = EP.generar(escribir=True, solo_vista_completa=True)
    total_ep = len(episodios)
    if args.limit:
        episodios = episodios[: args.limit]
    print(f"F1: episodios vista completa = {total_ep} | a procesar = {len(episodios)}")

    # verificación de salubridad (sin-lookahead)
    chk = _verificar_sin_lookahead(lake, episodios)
    print(f"Ø : sin-lookahead (muestra): {chk['n_ok']}/{chk['n_verificados']} ok "
          f"-> {chk['sin_lookahead']}")

    # F2-F4: correr el comité
    agentes = [Agente(p["estacion"], p, lake=lake) for p in perfiles]
    wf = MOD.walk_forward(lake, agentes, episodios,
                          punto=args.punto, horizon=args.horizon)
    frames = wf["episodios"]
    tally_lake = wf["tally_estacion"]
    print(f"F2-F4: episodios procesados = {len(frames)}")

    # modelado OOS + validación temporal (Opción C Triada + Embargo)
    oos = MOD.validar_oos(frames)
    tt = oos["test_tunado"]
    emb = oos.get("embargo_temporal", {})
    tt_indep = emb.get("metricas_indep_zz25", {})
    rc = oos["raw_confluencia_test"]
    tally_test = oos.get("tally_test", {})

    print(f"\n== F4: CONFLUENCIA COMITÉ (OOS Test >= 2023) ==")
    print(f"T óptimo tunado en train (<2020) = {oos.get('umbral_T_optimo')}")
    print(f"Test zz25 acc={tt['accuracy']} (n={tt['n_episodios_con_senal']}) baseline={tt['baseline']} lift={tt['lift']} p_greater={tt['p_value_greater']}")
    if tt.get("direccional"):
        ed_c = tt["direccional"]
        e_a = f"{ed_c['edge_alza']:+.2%}" if ed_c.get('edge_alza') is not None else "-"
        e_b = f"{ed_c['edge_baja']:+.2%}" if ed_c.get('edge_baja') is not None else "-"
        e_c = f"{ed_c['edge_combinado']:+.2%}" if ed_c.get('edge_combinado') is not None else "-"
        print(f"  -> Direccional zz25: ALZA acc={ed_c['accuracy_alza']} (edge={e_a}, p={ed_c['p_greater_alza']}, n={ed_c['n_alza']}) | "
              f"BAJA acc={ed_c['accuracy_baja']} (edge={e_b}, p={ed_c['p_greater_baja']}, n={ed_c['n_baja']}) | "
              f"edge_comb={e_c}")
    print(f"Test purgado (embargo) acc={tt_indep.get('accuracy')} (n_indep={emb.get('n_indep')}/{emb.get('n_nominal')}) p_greater={tt_indep.get('p_value_greater')}")
    print(f"Raw confluencia zz25 acc={rc['accuracy']} (n={rc['n_episodios_con_senal']})")

    # F5 reglas por estación: OOS vs In-Sample
    # 1. Baselines triada
    baselines_test_triada = {
        sc: {
            "baseline_alza": oos["baselines_alza_test"][sc],
            "baseline_baja": oos["baselines_baja_test"][sc],
            "baseline_mayoritaria": oos["baselines_triada"][sc],
        }
        for sc in ("zz25", "zz50", "zz75")
    }
    baselines_lake_triada = {
        sc: baselines_pivote_escala(frames, scale=sc)
        for sc in ("zz25", "zz50", "zz75")
    }

    # 2. Clasificación OOS (conjunto de test >= 2023)
    val_oos, inv_oos, todas_oos = clasificar_estaciones(tally_test, baselines_test_triada, min_n=50, min_edge=PASO_EDGE, alpha_fdr=OMEGA)

    # 3. Clasificación In-Sample (lake completo 1993-2026)
    val_lake, inv_lake, todas_lake = clasificar_estaciones(tally_lake, baselines_lake_triada, min_n=50, min_edge=PASO_EDGE, alpha_fdr=OMEGA)

    base_lake_zz25 = baselines_lake_triada["zz25"]["baseline_mayoritaria"]

    print(f"\n== F5: TABLA OOS (Test >= 2023, n_pivotes={oos.get('n_pivotes_test')}) ==")
    print(f"{'Estación':<12} | {'Escala':<6} | {'Dir':<5} | {'Acc':<6} | {'Base':<6} | {'Edge':<8} | {'CI95':<16} | {'p_crudo':<8} | {'p_BH':<8} | {'N':<5} | {'Status'}")
    print("-" * 105)
    for est in sorted(todas_oos.keys()):
        o = todas_oos[est]
        ci_str = f"[{o['ci95_optimo'][0]}, {o['ci95_optimo'][1]}]" if o['ci95_optimo'][0] is not None else "[-, -]"
        p_c_str = f"{o['p_crudo_optimo']:.4f}" if o['p_crudo_optimo'] is not None else "-"
        p_bh_str = f"{o['p_BH_optimo']:.4f}" if o['p_BH_optimo'] is not None else "-"
        edge_str = f"{o['edge_optimo']:+.2%}" if o['edge_optimo'] is not None else "-"
        acc_str = f"{o['acc_optimo']:.2f}" if o['acc_optimo'] is not None else "-"
        base_str = f"{o['baseline_optimo']:.2f}" if o['baseline_optimo'] is not None else "-"
        print(f"{est:<12} | {o['escala_optima']:<6} | {o['direccion_optima']:<5} | {acc_str:<6} | {base_str:<6} | {edge_str:<8} | {ci_str:<16} | {p_c_str:<8} | {p_bh_str:<8} | {o['n_optimo']:<5} | {o['status']}")

    print(f"\nResumen OOS: VALIDADAS = {len(val_oos)} | INVALIDADAS = {len(inv_oos)}")

    print(f"\n== F5: TABLA IN-SAMPLE (Lake Completo 1993-2026, N={len(frames)}) ==")
    print(f"{'Estación':<12} | {'Escala':<6} | {'Dir':<5} | {'Acc':<6} | {'Base':<6} | {'Edge':<8} | {'CI95':<16} | {'p_crudo':<8} | {'p_BH':<8} | {'N':<5} | {'Status'}")
    print("-" * 105)
    for est in sorted(todas_lake.keys()):
        o = todas_lake[est]
        ci_str = f"[{o['ci95_optimo'][0]}, {o['ci95_optimo'][1]}]" if o['ci95_optimo'][0] is not None else "[-, -]"
        p_c_str = f"{o['p_crudo_optimo']:.4f}" if o['p_crudo_optimo'] is not None else "-"
        p_bh_str = f"{o['p_BH_optimo']:.4f}" if o['p_BH_optimo'] is not None else "-"
        edge_str = f"{o['edge_optimo']:+.2%}" if o['edge_optimo'] is not None else "-"
        acc_str = f"{o['acc_optimo']:.2f}" if o['acc_optimo'] is not None else "-"
        base_str = f"{o['baseline_optimo']:.2f}" if o['baseline_optimo'] is not None else "-"
        print(f"{est:<12} | {o['escala_optima']:<6} | {o['direccion_optima']:<5} | {acc_str:<6} | {base_str:<6} | {edge_str:<8} | {ci_str:<16} | {p_c_str:<8} | {p_bh_str:<8} | {o['n_optimo']:<5} | {o['status']}")

    print(f"\nResumen In-Sample: VALIDADAS = {len(val_lake)} | INVALIDADAS = {len(inv_lake)}")

    # --- guardar salidas ---------------------------------------------
    common.SALIDAS.mkdir(parents=True, exist_ok=True)
    salv = common.SALIDAS
    (salv / "comite_registro_forense.json").write_text(
        json.dumps(frames, indent=2, ensure_ascii=False), encoding="utf-8")
    oos_out = {
        "baseline_pivote_mayoritaria_lake_zz25": base_lake_zz25,
        "baselines_lake_triada": baselines_lake_triada,
        "baselines_test_triada": baselines_test_triada,
        **oos,
    }
    (salv / "modelo_confluencia.json").write_text(
        json.dumps(oos_out, indent=2, ensure_ascii=False), encoding="utf-8")
    (salv / "reglas_validadas.json").write_text(
        json.dumps(val_oos, indent=2, ensure_ascii=False), encoding="utf-8")
    (salv / "reglas_invalidadas.json").write_text(
        json.dumps(inv_oos, indent=2, ensure_ascii=False), encoding="utf-8")
    (salv / "reglas_estaciones_lake.json").write_text(
        json.dumps(todas_lake, indent=2, ensure_ascii=False), encoding="utf-8")

    res = {
        "episodios_generados": total_ep,
        "episodios_procesados": len(frames),
        "episodios_con_senal": sum(1 for f in frames if f.get("flujo_neto")),
        "n_estaciones_validadas_oos": len(val_oos),
        "n_estaciones_invalidadas_oos": len(inv_oos),
        "estaciones_validadas_oos": ", ".join(sorted(val_oos)),
        "estaciones_invalidadas_oos": ", ".join(sorted(inv_oos)),
        "n_estaciones_validadas_lake": len(val_lake),
        "n_estaciones_invalidadas_lake": len(inv_lake),
        "estaciones_validadas_lake": ", ".join(sorted(val_lake)),
        "estaciones_invalidadas_lake": ", ".join(sorted(inv_lake)),
        "baseline_lake_zz25": base_lake_zz25,
        "baselines_triada_test": oos.get("baselines_triada"),
        "baselines_alza_test": oos.get("baselines_alza_test"),
        "baselines_baja_test": oos.get("baselines_baja_test"),
        "resolution_rates_test": oos.get("resolution_rates_test"),
        "modelo_confluencia_test_deflated_zz25": tt,
        "modelo_confluencia_test_indep_zz25": tt_indep,
        "modelo_confluencia_triada_test": oos.get("test_tunado_triada"),
        "embargo_temporal": emb,
        "modelo_confluencia_raw_test_zz25": rc,
        "sin_lookahead": chk,
    }
    (salv / "resumen.json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n== Salidas guardadas en {salv} ==")
    for name in ("comite_registro_forense.json", "modelo_confluencia.json",
                 "reglas_validadas.json", "reglas_invalidadas.json",
                 "reglas_estaciones_lake.json", "resumen.json"):
        print("  ", salv / name)


if __name__ == "__main__":
    main()