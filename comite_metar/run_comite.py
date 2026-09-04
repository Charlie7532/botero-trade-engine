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
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # /root/botero-trade

from comite_metar.scripts import common, episodios as EP, estado_en as EE
from comite_metar.agentes._agente_base import Agente
from comite_metar.curador import modelador as MOD

VALID_MIN_N = 15        # mínimo de episodios para VALIDAR una estación
PASO_EDGE = 0.03        # hr debe superar baseline al menos +3pp
OMEGA = 0.15            # p_greater umbral de significancia por estación


# ---------------------------------------------------------------------------
def _verificar_sin_lookahead(lake, episodios) -> Dict:
    """Salubridad: sin-lookahead de estado_en en una muestra de episodios."""
    ok = 0
    n = min(len(episodios), 25)
    for ep in episodios[:n]:
        try:
            EE.assert_sin_lookahead(lake, ep["t0"])
            ok += 1
        except Exception:
            pass
    return {"n_verificados": n, "n_ok": ok,
            "sin_lookahead": ok == n}


def baseline_pivote(frames: List[Dict]) -> float:
    """Baseline naive = frecuencia de la dirección de pivote mayoritaria."""
    dirs = [f["pivote_real"]["pivote_direccion"]
            for f in frames if f.get("pivote_real")]
    if not dirs:
        return 0.5
    fa = dirs.count("ALZA") / len(dirs)
    return round(max(fa, 1 - fa), 4)


def reglas_por_estacion(tally: Dict[str, Dict], baseline: float
                        ) -> "tuple[Dict, Dict]":
    """Clasifica cada estación en (validadas, invalidadas) con N y p."""
    val, inv = {}, {}
    for est, t in tally.items():
        n, hits = t["n"], t["hits"]
        dirs = t["dirs"]
        dir_pred = ("ALZA" if dirs["ALZA"] >= dirs["BAJA"] else "BAJA")
        m = MOD.metricas(hits, n, baseline)
        edge = m["accuracy"] - m["baseline"]
        p_g = m["p_value_greater"]
        obj = {
            "estacion": est,
            "direccion_anticipada_predominante": dir_pred,
            "n_episodios": n,
            "hits": hits,
            "hits_alza": dirs["ALZA"],
            "hits_baja": dirs["BAJA"],
            "accuracy": m["accuracy"],
            "baseline": m["baseline"],
            "lift": m["lift"],
            "edge_sobre_baseline": round(edge, 4) if n else None,
            "p_value_greater": p_g,
            "p_value_two_sided": m["p_value_two_sided"],
        }
        if n >= VALID_MIN_N and edge >= PASO_EDGE and p_g is not None and p_g < OMEGA:
            obj["status"] = "VALIDADA"
            val[est] = obj
        elif n < VALID_MIN_N:
            obj["status"] = "INVALIDADA"
            obj["razon"] = f"evidencia insuficiente (n={n}<{VALID_MIN_N})"
            inv[est] = obj
        else:
            obj["status"] = "INVALIDADA"
            obj["razon"] = (f"accuracy {m['accuracy']:.2f} no supera baseline "
                            f"{m['baseline']:.2f} con suficiente significancia "
                            f"(p_greater={p_g})")
            inv[est] = obj
    return val, inv


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Comité METAR walk-forward")
    ap.add_argument("--limit", type=int, default=None,
                    help="procesa solo los primeros N episodios")
    ap.add_argument("--punto", default="t0", choices=["t0", "nucleo_pos"])
    ap.add_argument("--horizon", type=int, default=MOD.HORIZONTE_DEFAULT)
    args = ap.parse_args()

    print("== Comité METAR — Walk-Forward (Fases 1-5) ==")
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
    tally = wf["tally_estacion"]
    print(f"F2-F4: episodios procesados = {len(frames)}")

    # modelado OOS + validación temporal
    oos = MOD.validar_oos(frames)
    tt = oos["test_tunado"]
    rc = oos["raw_confluencia_test"]
    print(f"F4 : test deflated acc={tt['accuracy']} p_greater="
          f"{tt['p_value_greater']} (n={tt['n_episodios_con_senal']}) | "
          f"raw_confluencia acc={rc['accuracy']} (n={rc['n_episodios_con_senal']})")

    # F5 reglas por estación
    base = baseline_pivote(frames)
    val, inv = reglas_por_estacion(tally, base)
    print(f"F5 : baseline mayoritaria = {base} | reglas VALIDADAS = {len(val)} | "
          f"INVALIDADAS = {len(inv)}")

    # --- guardar salidas ---------------------------------------------
    common.SALIDAS.mkdir(parents=True, exist_ok=True)
    salv = common.SALIDAS
    (salv / "comite_registro_forense.json").write_text(
        json.dumps(frames, indent=2, ensure_ascii=False), encoding="utf-8")
    oos_out = {
        "baseline_pivote_mayoritaria": base,
        **oos,
    }
    (salv / "modelo_confluencia.json").write_text(
        json.dumps(oos_out, indent=2, ensure_ascii=False), encoding="utf-8")
    (salv / "reglas_validadas.json").write_text(
        json.dumps(val, indent=2, ensure_ascii=False), encoding="utf-8")
    (salv / "reglas_invalidadas.json").write_text(
        json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
    res = {
        "episodios_generados": total_ep,
        "episodios_procesados": len(frames),
        "episodios_con_senal": sum(1 for f in frames if f.get("flujo_neto")),
        "n_estaciones_validadas": len(val),
        "n_estaciones_invalidadas": len(inv),
        "estaciones_validadas": ", ".join(sorted(val)),
        "estaciones_invalidadas": ", ".join(sorted(inv)),
        "modelo_confluencia_test_deflated": tt,
        "modelo_confluencia_raw_test": rc,
        "sin_lookahead": chk,
    }
    (salv / "resumen.json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n== Salidas guardadas en {salv} ==")
    for name in ("comite_registro_forense.json", "modelo_confluencia.json",
                 "reglas_validadas.json", "reglas_invalidadas.json",
                 "resumen.json"):
        print("  ", salv / name)


if __name__ == "__main__":
    main()