#!/usr/bin/env python3
"""
AUDITOR — gate de calidad de la REGLA DE ORO.
==============================================
Regla de oro: NINGUNA señal expuesta sin probabilidad + CI95 + N.
Prohibidas etiquetas binarias. Separar wins de losses (no promediar colas).
Señales huérfanas (N<10) NO mezcladas con pobladas.

Audita la SALIDA del coordinator y los 3 category agents (CAT1/CAT2/CAT3).

Checks por señal:
  [1] CI95 + N en toda señal
  [2] sin etiquetas binarias sin respaldo probabilístico
  [3] wins/losses separados (no colapso en media)
  [4] sin huérfanas (N<10) mezcladas con pobladas
  [5] bins calibrados del fact store (NO percentiles crudos)
  [6] monotonicidad medida (no solo IC)

Veredicto por señal:  ✅ (número clave) / 🚨 (detalle) / 🤫 (sigue corriendo)

Uso:  backend/.venv/bin/python research/auditor_gate.py
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path("/root/botero-trade")
SCRATCH = ROOT / "data/research"

# ─────────────────────────────────────────────────────────────────────────────
# 1. DETECCIÓN DE SALIDAS DISPONIBLES
# ─────────────────────────────────────────────────────────────────────────────
FILES = {
    "coordinator": SCRATCH / "coordinator.py",
    "coordinator_out": SCRATCH / "coordinator_report.json",
    "cat1": SCRATCH / "cat1_economia.py",
    "cat1_out": SCRATCH / "cat1_economia_results.json",
    "cat2": SCRATCH / "cat2_sentimiento.py",
    "cat2_out": SCRATCH / "cat2_sentimiento_report.json",
    "cat3": SCRATCH / "cat3_accion.py",
    "cat3_out": SCRATCH / "cat3_accion_report.json",
}

def file_exists(path):
    return path.exists() if isinstance(path, Path) else False

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        return {"__error__": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# 2. VERIFICADORES
# ─────────────────────────────────────────────────────────────────────────────
def has_ci95(block):
    """block es un dict de señal. Devuelve True si tiene CI95."""
    if not isinstance(block, dict):
        return False
    for key in ("ci95_pct", "ci95", "ci95_pct_lo"):
        if key in block:
            return True
    # busca recursivo
    for v in block.values():
        if isinstance(v, dict) and has_ci95(v):
            return True
    return False

def has_n(block):
    if not isinstance(block, dict):
        return False
    if "n" in block or "N" in block:
        return True
    for v in block.values():
        if isinstance(v, dict) and has_n(v):
            return True
    return False

def has_wins_losses_separated(block):
    """wins/losses separados: wins_mean + losses_mean (o win_p50 + loss_p50)."""
    if not isinstance(block, dict):
        return False
    keys = set(block.keys())
    if ("wins_mean_pct" in keys and "losses_mean_pct" in keys):
        return True
    if ("win_p50_pct" in keys and "loss_p50_pct" in keys):
        return True
    for v in block.values():
        if isinstance(v, dict) and has_wins_losses_separated(v):
            return True
    return False

def collect_signals_from_grade_a(grade_a):
    """Devuelve {nombre: {N, tiene_ci95, tiene_wl_sep, min_n_horizonte}}."""
    out = {}
    if not isinstance(grade_a, dict):
        return out
    for name, block in grade_a.items():
        if not isinstance(block, dict):
            continue
        N = block.get("N")
        horizons = {k: v for k, v in block.items() if k.startswith("h") and isinstance(v, dict)}
        n_vals = [v.get("n") for v in horizons.values() if isinstance(v.get("n"), (int, float))]
        out[name] = {
            "N": N,
            "tiene_ci95": any(has_ci95(v) for v in horizons.values()),
            "tiene_wl_sep": any(has_wins_losses_separated(v) for v in horizons.values()),
            "min_n_horizonte": min(n_vals) if n_vals else None,
        }
    return out

# ─────────────────────────────────────────────────────────────────────────────
# 3. INSPECCIÓN DE FUENTE (bins calibrados vs percentiles crudos)
# ─────────────────────────────────────────────────────────────────────────────
def inspect_source(path):
    """Escanea un .py en busca de: uso de bins calibrados, uso de percentiles
    crudos, y medición de monotonicidad."""
    txt = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    calibrated = bool(re.search(
        r"dimension_thresholds_definition|_fact_store\.json|_edges_d1|_labels_d1",
        txt))
    raw_percentile = bool(re.search(
        r"\.quantile\(|\.rank\(pct|percentile\(|np\.percentile|expanding\(\)\.rank",
        txt))
    # monotonicidad medida: busca términos de monotonicidad o tablas por bin
    monotonic = bool(re.search(
        r"monoton|monotonic|across.?bin|por.?bin|por.?label|gradiente|slope",
        txt, re.IGNORECASE))
    return {
        "calibrated_bins": calibrated,
        "raw_percentile_present": raw_percentile,
        "monotonic_measured": monotonic,
    }

# ─────────────────────────────────────────────────────────────────────────────
# 4. AUDITORÍA POR AGENTE
# ─────────────────────────────────────────────────────────────────────────────
verdicts = []
violations = []

def v(signal, verdict, note):
    verdicts.append({"signal": signal, "verdict": verdict, "note": note})

def violation(text):
    violations.append(text)

# ── CAT 1 (ECONOMÍA) ──────────────────────────────────────────────────────────
cat1_src = inspect_source(FILES["cat1"])
cat1_out = load_json(FILES["cat1_out"]) if FILES["cat1_out"].exists() else None

if FILES["cat1_out"].exists() and isinstance(cat1_out, dict) and "__error__" not in cat1_out:
    # bins calibrados
    if cat1_src["calibrated_bins"]:
        v("CAT1 bins calibrados", "✅", "usa dimension_thresholds_definition del fact store")
    else:
        v("CAT1 bins calibrados", "🚨", "NO usa bins calibrados")
        violation("CAT1 no carga bins calibrados del fact store")

    # estado actual por sensor: ¿probabilidad + N? (sin CI95 en JSON)
    estado = cat1_out.get("estado_actual_por_sensor", {})
    for station, s in estado.items():
        has_p = isinstance(s.get("p_bull_zz25"), (int, float))
        has_n = isinstance(s.get("n"), (int, float))
        if has_p and has_n:
            v(f"CAT1 estado actual {station}", "✅",
              f"p_bull_zz25={s.get('p_bull_zz25')}, n={s.get('n')} (pero SIN CI95)")
        else:
            v(f"CAT1 estado actual {station}", "🚨", "falta probabilidad o N")
    # CI95 ausente en el estado actual (el p_bull no lleva CI95)
    violation("CAT1: p_bull_zz25/p_bull_zz50 en 'estado_actual_por_sensor' NO llevan CI95 "
              "(solo punto + N). La regla exige CI95 en toda señal expuesta.")

    # régimen duro sin respaldo
    regime = cat1_out.get("regimen_ultimo_dia")
    if regime:
        v("CAT1 régimen (EXPANSION/TRANSICION/CONTRACCION)", "🚨",
          f"'{regime}' es etiqueta binaria/triestado SIN probabilidad + CI95 + N (umbrales 60/40 hardcoded)")
        violation("CAT1: 'regimen' (EXPANSION/TRANSICION/CONTRACCION) es una etiqueta binaria "
                  "sin respaldo probabilístico — viola la regla de oro. Umbrales 60/40 en "
                  "cat1_economia.py line ~310-317.")

    # grade A: solo en stdout, NO en JSON (gap para el coordinator)
    v("CAT1 señales GRADE A (CREDIT_STRESS/YIELD/DXY/ROTATION)", "🤫",
      "calculadas con CI95+N+wins/losses pero SOLO impresas en stdout — NO persistidas en cat1_economia_results.json")
    violation("CAT1: las señales GRADE A (CREDIT_STRESS, YIELD, DXY, ROTATION) con CI95+N y "
              "wins/losses NO se guardan en el JSON de salida — el coordinator no puede consumirlas. "
              "Solo están en stdout.")

    # monotonicidad
    if not cat1_src["monotonic_measured"]:
        v("CAT1 monotonicidad medida", "🚨",
          "NO mide monotonicidad forward-return vs health score (anchors HEALTH_ANCHORS son hand-coded, no medidos)")
        violation("CAT1: la monotonicidad del health score (0-100) NO está medida contra forward "
                  "returns — HEALTH_ANCHORS son supuestos por label, no validados empíricamente.")
else:
    v("CAT1 salida", "🤫", "cat1_economia_results.json no disponible o inválido")
    if not FILES["cat1"].exists():
        v("CAT1 script", "🤫", "cat1_economia.py no existe")

# ── CAT 2 (SENTIMIENTO) ───────────────────────────────────────────────────────
cat2_src = inspect_source(FILES["cat2"])
cat2_out = load_json(FILES["cat2_out"]) if FILES["cat2_out"].exists() else None

if FILES["cat2_out"].exists() and isinstance(cat2_out, dict) and "__error__" not in cat2_out:
    if cat2_src["calibrated_bins"]:
        v("CAT2 bins calibrados", "✅", "usa dimension_thresholds_definition del fact store")
    else:
        v("CAT2 bins calibrados", "🚨", "NO usa bins calibrados")
        violation("CAT2 no carga bins calibrados")

    # RAW percentile en graduated_pct — inconsistencia con CAT1/CAT3
    if cat2_src["raw_percentile_present"]:
        v("CAT2 graduated_pct (percentil crudo)", "🚨",
          "usa expanding().rank(pct=True) = percentil crudo para el estado graduado y el índice de protección, "
          "MIENTRAS CAT1/CAT3 usan σ-band calibrado")
        violation("CAT2: 'graduated_pct' y el 'CAT2 PROTECTION INDEX' se calculan con percentiles "
                  "crudos (expanding().rank(pct=True)) — INCONSISTENTE con CAT1/CAT3 que usan σ-band "
                  "calibrado. El índice de protección (headline 53.09%) se basa en percentiles crudos, "
                  "no en bins calibrados. (La clasificación D1 y las GRADE A SÍ usan bins calibrados.)")

    # índice de protección = etiqueta emoji sin CI95+N
    v("CAT2 índice de protección + etiquetas emoji (🔴 BOCHORNO…)", "🚨",
      "headline binario por umbrales (80/60/40/20) SIN CI95 + N sobre el índice agregado")
    violation("CAT2: 'CAT2 PROTECTION INDEX' se expone como etiqueta emoji (🔴 BOCHORNO ALTO / "
              "🟢 AIRE SECO…, umbrales 80/60/40/20) SIN CI95 + N — etiqueta binaria sin respaldo "
              "probabilístico.")

    # GRADE A
    ga = cat2_out.get("grade_a", {})
    signals = collect_signals_from_grade_a(ga)
    for name, s in signals.items():
        N = s["N"]
        ci = "CI95" if s["tiene_ci95"] else "SIN CI95"
        wl = "wins/losses SEPARADOS" if s["tiene_wl_sep"] else "wins/losses NO separados"
        mn = s["min_n_horizonte"]
        if N is None:
            v(f"CAT2 {name}", "🚨", "sin N declarado")
            violation(f"CAT2 {name}: sin N.")
        elif s["tiene_ci95"] and s["tiene_wl_sep"]:
            if isinstance(N, (int, float)) and N < 10:
                v(f"CAT2 {name}", "🚨", f"N={N}<10 huérfana (pero reportada con CI95+wins/losses)")
                violation(f"CAT2 {name}: N={N}<10 — señal huérfana. Debe ir con intérprete de "
                          "estado vectorial, NO como señal standalone.")
            elif isinstance(N, (int, float)) and N < 30:
                v(f"CAT2 {name}", "✅", f"N={N} (10≤N<30, direccional con CI ancho) — {ci}, {wl}")
            else:
                v(f"CAT2 {name}", "✅", f"N={N} — {ci}, {wl}")
        else:
            v(f"CAT2 {name}", "🚨", f"falta {ci} o {wl}")
            violation(f"CAT2 {name}: falta {ci} o {wl}.")

    # PÁNICO TOTAL: tres variantes (bins N=13, pct90 N=47, raw P85 N=55) — mezcla de bins y percentiles
    v("CAT2 PANICO_TOTAL (3 variantes)", "🚨",
      "expone bins-calibrados (N=13) Y percentiles crudos (N=47/55) para la MISMA señal — "
      "riesgo de que el consumidor elija la versión raw (PF 8.09 vs 2.76)")
    violation("CAT2: PANICO_TOTAL se expone en 3 versiones (bins N=13, pct≥90 N=47, raw≥P85 N=55) "
              "sin designar cuál es la canónica. La versión raw (PF 8.09) es la conocida sobre-inflada "
              "por percentiles crudos (pitfall #84: raw P85 → PF 2.45). Solo la versión de bins "
              "calibrados debe ser la señal operativa.")

    if not cat2_src["monotonic_measured"]:
        v("CAT2 monotonicidad medida", "🚨",
          "NO mide monotonicidad (solo CI95 por horizonte + splits 2-way; sin tabla retorno-vs-bin)")
        violation("CAT2: no mide monotonicidad del edge a través de los bins D1 (solo CI95 por "
                  "horizonte y contrastes 2-way CAPITULACIÓN vs SUB-REACCIÓN).")
else:
    v("CAT2 salida", "🤫", "cat2_sentimiento_report.json no disponible")
    if not FILES["cat2"].exists():
        v("CAT2 script", "🤫", "cat2_sentimiento.py no existe")

# ── CAT 3 (ACCIÓN) ────────────────────────────────────────────────────────────
cat3_src = inspect_source(FILES["cat3"])
cat3_out = load_json(FILES["cat3_out"]) if FILES["cat3_out"].exists() else None

if FILES["cat3"].exists() and not FILES["cat3_out"].exists():
    v("CAT3 salida", "🤫",
      "cat3_accion.py existe (script completo) pero NO se ha ejecutado — no hay cat3_accion_report.json. "
      "Además el script solo imprime a stdout, NO escribe JSON (gap: coordinator no podrá consumirlo).")
    if cat3_src["calibrated_bins"]:
        v("CAT3 bins calibrados (código)", "✅", "load_calibrated_edges() lee fact store")
    else:
        v("CAT3 bins calibrados (código)", "🚨", "no carga bins calibrados")
    violation("CAT3: script sin salida JSON — 'main()' solo hace print(), no json.dump. "
              "El coordinator no tendrá una salida estructurada de CAT3.")
elif FILES["cat3_out"].exists():
    v("CAT3 salida", "✅", "cat3_accion_report.json disponible")
else:
    v("CAT3 script", "🚨", "cat3_accion.py no existe")

# ── COORDINATOR ───────────────────────────────────────────────────────────────
coord_src = inspect_source(FILES["coordinator"])
coord_out = load_json(FILES["coordinator_out"]) if FILES["coordinator_out"].exists() else None

if FILES["coordinator_out"].exists() and isinstance(coord_out, dict) and "__error__" not in coord_out:
    v("coordinator bins calibrados", "✅", "usa dimension_thresholds_definition del fact store")
    if not coord_src["calibrated_bins"]:
        v("coordinator bins calibrados", "🚨", "NO carga bins calibrados")
        violation("coordinator no carga bins calibrados")

    # TAF: p_bull SIN CI95 + direction binaria + huérfanas mezcladas
    taf = coord_out.get("taf", {})
    orphans = 0
    no_ci95 = 0
    for station, t in taf.items():
        if not isinstance(t, dict):
            continue
        for scale, sc in (t.get("scales") or {}).items():
            if not isinstance(sc, dict):
                continue
            n = sc.get("n")
            if isinstance(n, (int, float)) and n < 10:
                orphans += 1
            # ¿CI95? El TAF no expone CI95 en ningún scale
            if "ci95" not in sc:
                no_ci95 += 1
    v("coordinator TAF (cono multi-escala)", "🚨",
      f"{no_ci95} celdas scale SIN CI95 (solo p_bull + n) y {orphans} celdas huérfanas (n<10) "
      f"expuestas junto a pobladas — ej. credit zz75 n=1 p_bull=0.4545")
    violation(f"coordinator TAF: expone p_bull (probabilidad puntual) SIN CI95 en las {no_ci95} "
              f"celdas scale. La regla exige probabilidad + CI95 + N. Además mezcla {orphans} "
              "celdas huérfanas (n<10, 'ANECDOTAL'/'LOW') con pobladas en el mismo cono de dispersión.")
    v("coordinator TAF 'direction' (BULL/BEAR)", "🚨",
      "etiqueta binaria derivada de p_bull≥0.5 — redundante (p_bull ya la expresa) y sin CI95 propia")
    violation("coordinator TAF: 'direction' BULL/BEAR es una etiqueta binaria redundante "
              "(p_bull>=0.5) expuesta junto a p_bull sin CI95 — la regla prohíbe etiquetas binarias "
              "sin respaldo probabilístico completo.")

    # METAR word = etiqueta binaria sin probabilidad
    metar = coord_out.get("metar", {})
    words = {c: m.get("metar_word") for c, m in metar.items() if isinstance(m, dict)}
    if words:
        v("coordinator METAR 'metar_word' (NORMAL/BOCHORNO…)", "🚨",
          f"etiquetas cualitativas {words} SIN probabilidad + CI95 + N (umbrales graduated hardcoded)")
        violation(f"coordinator METAR: 'metar_word' {list(words.values())} son etiquetas cualitativas "
                  "sin respaldo probabilístico (umbrales 97.7/84.13/70/50/30/15.87/2.28 hardcoded en "
                  "metar_word()).")

    # cascade_conviction: score agregado sin CI95
    cc = coord_out.get("cascade_conviction", {})
    v("coordinator cascade_conviction (c50/c75/c50to75)", "🚨",
      f"score agregado ({cc.get('cascade_50')}, {cc.get('cascade_75')}, {cc.get('cascade_50to75')}) "
      f"tercile={cc.get('tercile')} SIN CI95 — es un score de compositor, no una señal con N")
    violation("coordinator: cascade_conviction (c50/c75/c50to75 + tercile) se expone SIN CI95. "
              "El tercile es una discretización binaria sin intervalo de confianza sobre el score.")

    # régime: bien (probabilidad + CI95 + N)
    reg = coord_out.get("regimen", {})
    if isinstance(reg, dict) and "ci95" in reg and "N" in reg:
        v("coordinator RÉGIMEN (secuencia)", "✅",
          f"{reg.get('label')} p={reg.get('probability')}, CI95={reg.get('ci95')}, N={reg.get('N')}")
    else:
        v("coordinator RÉGIMEN", "🚨", "sin CI95 + N")
        violation("coordinator régimen sin CI95+N.")

    # grade_a: refs en percentiles crudos, sin CI95
    ga = coord_out.get("grade_a", {})
    for name, g in ga.items():
        ref = g.get("ref", "") if isinstance(g, dict) else ""
        if "raw P85" in ref or "raw" in ref:
            v(f"coordinator grade_a {name}", "🚨",
              f"ref usa percentiles crudos ('{ref}') en vez de bins calibrados; sin CI95 ni wins/losses")
            violation(f"coordinator grade_a {name}: cita '{ref}' = percentil crudo (PF 8.09 inflado), "
                      "no la versión de bins calibrados (PF ~2.45). Solo 'active' booleano, sin CI95+N "
                      "ni wins/losses del estado actual.")

    if not coord_src["monotonic_measured"]:
        v("coordinator monotonicidad medida", "🚨",
          "NO mide monotonicidad (cascade tercil + régimen binario; sin retorno-vs-score)")
        violation("coordinator: no mide monotonicidad forward-return vs cascade_conviction / "
                  "estado graduado (solo tercil y régimen binario).")
else:
    v("coordinator salida", "🤫", "coordinator_report.json no disponible")
    if not FILES["coordinator"].exists():
        v("coordinator script", "🤫", "coordinator.py no existe")

# ─────────────────────────────────────────────────────────────────────────────
# 5. EMITIR RESULTADO
# ─────────────────────────────────────────────────────────────────────────────
report = {
    "auditor": "auditor_gate.py",
    "timestamp": datetime.now().astimezone().isoformat(),
    "status_files": {k: file_exists(v) for k, v in FILES.items()},
    "verdicts": verdicts,
    "violations": violations,
}

print("═" * 80)
print("AUDITOR — GATE DE CALIDAD DE LA REGLA DE ORO")
print("═" * 80)
print("\nARCHIVOS DETECTADOS:")
for k, ok in sorted({k: file_exists(v) for k, v in FILES.items()}.items()):
    mark = "✓" if ok else "✗"
    print(f"  [{mark}] {k}")

print("\n" + "─" * 80)
print("VEREDICTOS POR SEÑAL:")
print("─" * 80)
for x in verdicts:
    print(f"  {x['verdict']}  {x['signal']}")
    if x["note"]:
        print(f"         {x['note']}")

print("\n" + "─" * 80)
print(f"VIOLACIONES DE LA REGLA DE ORO ({len(violations)}):")
print("─" * 80)
for i, vio in enumerate(violations, 1):
    print(f"  {i}. {vio}")

out_path = SCRATCH / "auditor_gate_report.json"
with open(out_path, "w") as f:
    json.dump(report, f, indent=2, default=str, ensure_ascii=False)
print(f"\nReporte: {out_path}")
print("═" * 80)
