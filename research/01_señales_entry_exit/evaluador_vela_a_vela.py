#!/usr/bin/env python3
"""
EVALUADOR VELA A VELA v3 — Calificador forense de señales
===========================================================
v3 (30-Ago): Import migrado a arnes/, BLANCOS completos 31/31, --dry-run/--senal.
Correcciones aplicadas tras auditoría Gemini 22-Ago (RECHAZADO v1):
  P0: Usa los pivotes de quants_obs (oficiales) — elimina zigzag incompatible.
  P1: Rechaza señales que filtran pivot_type (sesgo de posición embebido).
  P2: Resultado por PRIMER PASO (first-passage) por escala: ¿el precio cruza
      antes el umbral favorable o el adverso? Elimina el artefacto de
      alternancia MIN/MAX (el hit ya no está garantizado por geometría).
  P5: El baseline excluye los pivotes donde la propia señal disparó.

Resultado por disparo (observable en tiempo real, sin saber el pivote):
  - favorable: movimiento real en la dirección del blanco hasta el evento
  - hit: ¿cruzó antes el umbral favorable que el adverso?
  - mae/mfe: dolor y ganancia máxima intra-tramo
  - bars: velas hasta resolverse
Régimen: última pierna CONFIRMADA de quants_obs (sello temporal).
"""
import sys
import inspect
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))
from arnes.registro import SEÑALES, _CERTEZA  # noqa: E402
from arnes.datos import cargar_datos  # noqa: E402
from arnes.timing import calc_timing_distribution  # noqa: E402

ESCALAS = {"zz25": 0.025, "zz50": 0.05, "zz75": 0.075}
BACKGROUND_THRESHOLD = 0.20  # PC1: señales con fire rate mayor saturan F3
_CACHE: dict = {"df": None, "spy": None, "pool": None, "signals": None}


def _body_uses_pivot_type(fn) -> bool:
    """True si la función filtra por pivot_type en su CUERPO (no en decorador/docstring).
    Las señales del arnés declaran pivot_type= como metadata en @_registrar,
    pero solo unas pocas realmente filtran df['pivot_type'] en la lógica."""
    src = inspect.getsource(fn)
    in_body = False
    in_docstring = False
    docstring_delim = None
    for line in src.split("\n"):
        stripped = line.strip()
        if stripped.startswith("def "):
            in_body = True
            continue
        if not in_body:
            continue
        # Track multi-line docstrings
        if in_docstring:
            if docstring_delim in stripped:
                in_docstring = False
            continue
        # Detect docstring start
        for delim in ('"""', "'''"):
            if delim in stripped:
                count = stripped.count(delim)
                if count == 1:
                    # Opening of multi-line docstring
                    in_docstring = True
                    docstring_delim = delim
                    break
                # count >= 2: single-line docstring or inline string — skip line
                break
        else:
            # No triple-quote found — check for pivot_type
            if stripped.startswith("#"):
                continue
            if "pivot_type" in line:
                return True
    return False


def _get_data():
    """Cache global de cargar_datos() — evita recargar 28 veces."""
    if _CACHE["df"] is None:
        _CACHE["df"], _CACHE["spy"] = cargar_datos()
    return _CACHE["df"], _CACHE["spy"]


def _get_signals(df):
    """Cache global de las señales evaluables (sin pivot_type en el cuerpo)."""
    if _CACHE["signals"] is None:
        _CACHE["signals"] = {
            n: SEÑALES[n](df).astype(bool) for n in SEÑALES
            if not _body_uses_pivot_type(SEÑALES[n])
        }
    return _CACHE["signals"]


def _pool_hermanas(df):
    """Cache global: pool de señales hermanas (sin pivot_type, fire rate ≤ 20%,
    y sin RETIRADA/DEGRADADA — excluye duplicados exactos del pool F3)."""
    if _CACHE["pool"] is None:
        sigs = _get_signals(df)
        _CACHE["pool"] = {}
        for n, s in sigs.items():
            if s.mean() > BACKGROUND_THRESHOLD:
                continue
            cert = str(_CERTEZA.get(n, {}).get("validacion", ""))
            if "RETIRADA" in cert or "DEGRADADA" in cert:
                continue
            _CACHE["pool"][n] = s.values
    return _CACHE["pool"]


BLANCOS = {
    # Auditados 20-Ago
    "euforia": "MAX", "bsi_recovery": "MAX", "pcr_put_panic": "MIN",
    "fg_extreme_greed": "MAX", "credit_equity_divergence": "MAX",
    "credit_easing_k1": "MIN", "fg_extreme_fear": "MIN", "panico_total": "MIN",
    "vvix_entry": "MIN", "capitulacion": "MIN",
    # Asignados 22-Ago (semántica + distribución de disparos):
    "bsi_washed_out": "MIN",        # ENTRY: breadth lavado = piso (100 MIN vs 61 MAX)
    "credit_stress": "MIN",         # ENTRY: estrés crediticio = piso (116 MIN)
    "dxy_bearish": "MIN",           # ENTRY: dólar débil = risk-on = piso
    "sub_reaccion": "MIN",          # ENTRY: edge positivo (338 MIN)
    "vix_crisis_spike": "MIN",      # RECLASIFICADA ENTRY 20-Ago (edge +0.75%)
    "sorpresa_total": "MIN",        # ENTRY contextual (287 MIN, edge +0.83%)
    "skew_paranoia_exit": "MAX",    # EXIT: paranoia de colas en techo
    "stealth_tail_hedging": "MAX",  # EXIT: cobertura OTM en techo (20 MAX)
    "cascade_reversal": "MAX",      # EXIT propuesta (N=0, diamante anecdótico)
    # Re-evaluación 22-Ago (semántica EXIT verificada en definición):
    "breadth_contraction_exit": "MAX",  # EXIT: BSI sale de EXPANSIVE → fin de expansión
    "credit_ease_exit": "MAX",          # EXIT: CREDIT sale de EASE → fin de easing
    "regime_change_exit": "MAX",        # EXIT: cambio de régimen VERANO→INVIERNO
    # v3 (30-Ago) — señales V2 vectoriales + turbulencia silenciosa
    "capitulacion_v2": "MIN",              # ENTRY: V2 vectorial de capitulación (D1+D2)
    "euforia_v2": "MAX",                   # EXIT: V2 vectorial de euforia (D1+D2)
    "vix_crisis_spike_v2": "MIN",          # ENTRY: V2 vectorial de VIX crisis spike (D1+D2)
    "sv5t_silent_distribution": "MAX",     # EXIT: turbulencia silenciosa en techos
    # prompt_cierre_v3 (31-Ago) — Ejercicios Probatorios
    "neutral_crush_entry": "MIN",          # E7 ENTRY: D1 neutral + CRUSH mean-reversion
    "neutral_spike_exit": "MAX",           # E7 EXIT: D1 neutral + SPIKE
    # Señales RETIRADAS/DEGRADADAS (targets asignados para re-evaluación)
    "credit_stress_exit": "MAX",           # EXIT: salida de estrés crediticio en techo
    "dxy_spike_exit": "MAX",               # EXIT: spike de dólar en techo
    "pcr_panic_exit": "MAX",               # EXIT: salida de pánico PCR
    "vix_complacency_exit": "MAX",         # EXIT: complacencia de VIX en techo
    "defensive_rotation_divergence": "MAX", # EXIT: divergencia defensiva en techo
}


def first_passage(prices, t0, scale, blanco):
    """Resultado por primer paso desde t0.
    favorable = movimiento en la dirección del blanco hasta el evento.
    hit = True si el umbral favorable se cruzó ANTES que el adverso."""
    p0 = prices[t0]
    path = prices[t0 + 1:]
    if len(path) == 0 or p0 <= 0:
        return None
    up_i = np.where(path >= p0 * (1 + scale))[0]
    dn_i = np.where(path <= p0 * (1 - scale))[0]
    up_i = up_i[0] if len(up_i) else np.inf
    dn_i = dn_i[0] if len(dn_i) else np.inf
    if np.isinf(up_i) and np.isinf(dn_i):
        return {"resuelto": False}
    down_first = dn_i < up_i
    event_i = int(min(up_i, dn_i))
    seg = prices[t0:t0 + 1 + event_i + 1]
    if blanco == "MAX":          # EXIT: favorable = caída
        captured = (p0 - prices[t0 + 1 + event_i]) / p0
        mae = float((seg.max() - p0) / p0)    # dolor: subida previa
        mfe = float((p0 - seg.min()) / p0)    # ganancia: caída alcanzada
        hit = down_first
    else:                        # ENTRY: favorable = subida
        captured = (prices[t0 + 1 + event_i] - p0) / p0
        mae = float((seg.min() - p0) / p0)    # dolor: caída previa
        mfe = float((seg.max() - p0) / p0)    # ganancia: subida alcanzada
        hit = not down_first
    return {"resuelto": True, "hit": bool(hit), "favorable": float(captured),
            "mae": mae, "mfe": mfe, "bars": event_i + 1}


def evaluar(señal_nombre: str, reevaluar: bool = False, ventana_f3: int = 5):
    """Evalúa una señal. reevaluar=True permite evaluar señales RETIRADAS/DEGRADADAS
    con el método nuevo (para decidir si merecen rescate).
    ventana_f3: ventana de la forensia F3/INDEP en días calendario (default 5)."""
    # ── P1: detectar señales con sesgo de posición embebido ──
    src = inspect.getsource(SEÑALES[señal_nombre])
    if _body_uses_pivot_type(SEÑALES[señal_nombre]):
        return {"señal": señal_nombre,
                "status": "EXCLUIDA",
                "razon": "La definición filtra pivot_type — sesgo de posición "
                         "embebido. No evaluable sin sesgo en este framework (P1)."}

    df, spy = _get_data()
    prices = spy["close"].astype(float).values
    spy_idx = spy.close.index

    # Excluir señales RETIRADAS / DEGRADADAS (salvo re-evaluación explícita)
    cert = _CERTEZA.get(señal_nombre, {})
    v = str(cert.get("validacion", ""))
    if ("RETIRADA" in v or "DEGRADADA" in v) and not reevaluar:
        return {"señal": señal_nombre, "status": "EXCLUIDA",
                "razon": f"Señal {v.split('(')[0].strip()}. No se evalúa (usar reevaluar=True)."}

    blanco = BLANCOS.get(señal_nombre, "AMBOS")
    if blanco == "AMBOS":
        return {"señal": señal_nombre, "status": "PENDIENTE",
                "razon": "Blanco AMBOS: requiere definición de blanco por el arquitecto."}

    sig = SEÑALES[señal_nombre](df).astype(bool)
    disparos = df[sig]

    # ── Filtrar datos pre-inception (ej. SKEW/FG pre-2011 sintético, CREDIT pre-2007) ──
    fecha_inicio = cert.get("fecha_inicio_valida")
    if fecha_inicio:
        n_antes = len(disparos)
        disparos = disparos[disparos["pivot_date"] >= pd.Timestamp(fecha_inicio)]
        n_filtrado = n_antes - len(disparos)
        if n_filtrado > 0:
            print(f"  [{señal_nombre}] Filtrados {n_filtrado} disparos pre-{fecha_inicio} (datos sintéticos/inválidos)")

    # ── Régimen desde pivotes de quants_obs (P0) ──
    piv_dates = df["pivot_date"].values
    piv_types = df["pivot_type"].values
    piv_pos = np.array([spy_idx.searchsorted(pd.Timestamp(d)) for d in piv_dates])
    n_piv = len(piv_dates)

    def régimen_en(t_pos):
        """Dirección de la pierna tras el último pivote CONFIRMADO.
        El pivote i se confirma cuando aparece el pivote i+1."""
        idx = np.arange(n_piv - 1)
        conf = piv_pos[1:]                      # confirmación del pivote i = pos del i+1
        valid = idx[conf <= t_pos]
        if len(valid) == 0:
            return "NA"
        last = valid[-1]
        return "ALZA" if piv_types[last] == "MIN" else "BAJA"

    def outcome_en(t_pos):
        """Perfil por escala para un momento dado (P2: first-passage)."""
        reg = régimen_en(t_pos)
        out = {"régimen": reg}
        for esc, thr in ESCALAS.items():
            r = first_passage(prices, t_pos, thr, blanco)
            out[esc] = r
        return out

    # ── Disparos de la señal ──
    fichas = []
    for piv_i, row in disparos.iterrows():
        t_pos = spy_idx.searchsorted(pd.Timestamp(row["pivot_date"]))
        if t_pos >= len(prices) - 1:
            continue
        o = outcome_en(t_pos)
        for esc in ESCALAS:
            r = o[esc]
            if r and r["resuelto"]:
                fichas.append({"fecha": row["pivot_date"], "escala": esc,
                               "régimen": o["régimen"], **r})
    F = pd.DataFrame(fichas)
    if F.empty:
        return {"señal": señal_nombre, "status": "SIN_DISPAROS_RESUELTOS",
                "razon": "Ningún disparo produjo un tramo resoluble (N=0 o sin primer paso)."}

    # ── Baseline: todos los pivotes del mismo tipo EXCLUIDOS los de la señal (P5) ──
    # Si la señal tiene fecha de inicio válida, el baseline se restringe a la misma era temporal
    tipo = "MAX" if blanco == "MAX" else "MIN"
    señal_fechas = set(pd.DatetimeIndex(disparos["pivot_date"]))
    base_rows = []
    for i in range(n_piv):
        if piv_types[i] != tipo:
            continue
        if fecha_inicio and pd.Timestamp(piv_dates[i]) < pd.Timestamp(fecha_inicio):
            continue
        if pd.Timestamp(piv_dates[i]) in señal_fechas:
            continue
        t_pos = piv_pos[i]
        if t_pos >= len(prices) - 1:
            continue
        o = outcome_en(t_pos)
        for esc in ESCALAS:
            r = o[esc]
            if r and r["resuelto"]:
                base_rows.append({"escala": esc, "régimen": o["régimen"], **r})
    B = pd.DataFrame(base_rows)

    # ── Perfil por celda: señal vs baseline ──
    UM_DIAMANTE = 21  # PC2: §3.3 — N≥21 es ROBUST (inferencia completa), ya no diamante

    def confidence_tier(n: int) -> str:
        """PC3: tiers §3.3 del fact store con semántica operacional."""
        if n <= 2:
            return "ANECDOTAL"   # solo existencia del evento
        if n <= 5:
            return "LOW"         # solo dirección
        if n <= 10:
            return "MODERATE"    # probabilidad con alta incertidumbre
        if n <= 20:
            return "HIGH"        # probabilidad y EV con incertidumbre moderada
        return "ROBUST"          # todo

    perfil = {}
    for esc in ESCALAS:
        for reg in ("ALZA", "BAJA"):
            s = F[(F["escala"] == esc) & (F["régimen"] == reg)]
            b = B[(B["escala"] == esc) & (B["régimen"] == reg)]
            if s.empty:
                continue
            n = len(s)
            fav = s["favorable"]
            b_fav = float(b["favorable"].mean()) if not b.empty else 0.0
            b_hit = float(b["hit"].mean()) if not b.empty else np.nan
            fav_neto = fav - b_fav
            mae_m = -abs(float(s["mae"].mean()))     # PC3: MAE siempre negativo (dolor)
            mfe_m = abs(float(s["mfe"].mean()))
            hits_s = s["hit"]
            # p-value binomial vs baseline hit de la celda (si hay baseline)
            pval = None
            if not b.empty and not np.isnan(b_hit):
                from scipy.stats import binomtest
                pval = float(binomtest(int(hits_s.sum()), n, b_hit,
                                       alternative="greater").pvalue)
            # Profit Factor (PF)
            wins = float(fav[hits_s].sum())
            losses = abs(float(fav[~hits_s].sum()))
            pf = wins / losses if losses > 0 else None
            # EV por barra (eficiencia temporal)
            bars_m = float(s["bars"].mean())
            ev_bar = float(fav_neto.mean()) / bars_m if bars_m > 0 else None
            # ── PROTOCOLO DIAMANTE (§3.3): N<21 = evento raro valioso ──
            # No se degrada por N bajo: se reporta con tasa CRUDA y tier §3.3
            diamante = n < UM_DIAMANTE
            perfil[f"{esc}|{reg}"] = {
                "n": n,
                "diamante": diamante,
                "confidence_tier": confidence_tier(n),
                "fav_media": round(float(fav.mean()), 4),
                "baseline_fav": round(b_fav, 4),
                "fav_neto": round(float(fav_neto.mean()), 4),
                "fav_neto_p5": round(float(fav_neto.quantile(0.05)), 4),
                "fav_neto_p95": round(float(fav_neto.quantile(0.95)), 4),
                "hit_rate": round(float(hits_s.mean()), 3),
                "baseline_hit": round(b_hit, 3) if not np.isnan(b_hit) else None,
                "hit_neto": round(float(hits_s.mean()) - b_hit, 3) if not np.isnan(b_hit) else None,
                "p_value": round(pval, 4) if pval is not None else None,
                "profit_factor": round(pf, 2) if pf is not None else None,
                "rr": round(mfe_m / abs(mae_m), 2) if mae_m != 0 else None,
                "ev_por_barra": round(ev_bar, 5) if ev_bar is not None else None,
                "mae_medio": round(mae_m, 4),
                "mae_p10": round(float(s["mae"].quantile(0.10)), 4) if n >= 10 else None,
                "mfe_medio": round(mfe_m, 4),
                "bars_medio": round(bars_m, 1),
            }

    # ── Forensia F3 ──
    # PC1: excluir señales "background" (fire rate >20%) del pool de hermanas.
    # H4: ventana en días CALENDARIO (±5d), no en índice (gap máx entre pivotes = 219d).
    # H2: clasifica fallos en las 3 escalas, no solo zz25.
    # P2.9 (22-Ago): ventana parametrizada para calibración 3d/5d/7d.
    VENTANA_DIAS = ventana_f3
    fechas_piv = pd.DatetimeIndex(df["pivot_date"])
    pool = {n: v for n, v in _pool_hermanas(df).items() if n != señal_nombre}
    pool_matrix = np.column_stack(list(pool.values())) if pool else None

    def hermana_en_ventana(fecha):
        """¿Alguna señal hermana (no-background) disparó en ±VENTANA_DIAS calendario?"""
        if pool_matrix is None or len(pool_matrix) == 0:
            return False
        mask = (fechas_piv >= fecha - pd.Timedelta(days=VENTANA_DIAS)) & \
               (fechas_piv <= fecha + pd.Timedelta(days=VENTANA_DIAS))
        if not mask.any():
            return False
        return bool(pool_matrix[mask].any())

    fallas = impredecibles = 0
    f3_esc: dict = {esc: {"fallas": 0, "impredecibles": 0} for esc in ESCALAS}
    for piv_i, row in disparos.iterrows():
        sub = F[F["fecha"] == row["pivot_date"]]
        if sub.empty:
            continue
        has_hermana = None  # lazy: una consulta de ventana por disparo
        for esc in ESCALAS:
            r = sub[sub["escala"] == esc]
            if r.empty or float(r["favorable"].iloc[0]) >= 0:
                continue  # no falló en esta escala
            if has_hermana is None:
                has_hermana = hermana_en_ventana(pd.Timestamp(row["pivot_date"]))
            if has_hermana:
                f3_esc[esc]["fallas"] += 1
            else:
                f3_esc[esc]["impredecibles"] += 1
        if has_hermana is not None:  # falló en al menos una escala
            if has_hermana:
                fallas += 1
            else:
                impredecibles += 1
    tot = fallas + impredecibles
    for esc in ESCALAS:
        t = f3_esc[esc]["fallas"] + f3_esc[esc]["impredecibles"]
        f3_esc[esc]["techo"] = round(f3_esc[esc]["fallas"] / t, 2) if t else None

    # Calificación canónica de timing (6 slots: t-2, t-1, t=0, t+1, t+2, ENTRE)
    timing_slots = calc_timing_distribution(
        signal_dates=disparos["pivot_date"].values,
        pivot_dates=df["pivot_date"].values,
        pivot_types=df["pivot_type"].values,
        target_pivot_type=blanco,
    )

    return {
        "señal": señal_nombre, "blanco": blanco, "status": "OK",
        "n_disparos": int(len(disparos)),
        "perfil_3d_régimen": perfil,
        "timing_slots": timing_slots,
        "forensia_F3": {"fallidos": tot, "falla_lectura": fallas,
                        "impredecible": impredecibles,
                        "techo_mejora": round(fallas / tot, 2) if tot else None,
                        "independencia": round(impredecibles / tot, 2) if tot else None,
                        "por_escala": f3_esc},
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Evaluador vela-a-vela v3")
    parser.add_argument("--dry-run", action="store_true", help="Verificar config sin ejecutar")
    parser.add_argument("--senal", type=str, default=None, help="Evaluar solo una señal")
    args = parser.parse_args()

    if args.dry_run:
        print("✅ Dry-run: configuración correcta")
        print(f"  Señales registradas: {len(SEÑALES)}")
        print(f"  Blancos definidos: {len(BLANCOS)}")
        sin_blanco = [s for s in SEÑALES if s not in BLANCOS]
        print(f"  Señales sin blanco: {sin_blanco}")
        sys.exit(0)

    TODAS = [args.senal] if args.senal else sorted(SEÑALES.keys())
    reporte = {}
    filas_ranking = []
    # Rescatadas: retiradas/degradadas por el método antiguo que el arquitecto
    # incluye en el set activo tras la re-evaluación v6 (22-Ago).
    RESCATADAS = {"skew_paranoia_exit"}
    for s in TODAS:
        r = evaluar(s, reevaluar=(s in RESCATADAS))
        reporte[s] = r
        st = r.get("status")
        marca = " [RESCATADA]" if s in RESCATADAS and st == "OK" else ""
        print(f"{s:32s} → {st}{marca}", flush=True)
        if st != "OK":
            continue
        # fila de ranking: mejor celda de la señal (fav_neto, n>=10 para robustez)
        mejor = None
        for celda, p in r["perfil_3d_régimen"].items():
            if p["n"] < 10:
                continue
            if mejor is None or p["fav_neto"] > r["perfil_3d_régimen"][mejor]["fav_neto"]:
                mejor = celda
        if mejor:
            p = r["perfil_3d_régimen"][mejor]
            filas_ranking.append({
                "señal": s, "celda": mejor, "n": p["n"], "diamante": p["diamante"],
                "tier": p["confidence_tier"],
                "hit": p["hit_rate"], "hit_neto": p["hit_neto"],
                "fav_neto": p["fav_neto"], "p": p["p_value"], "pf": p["profit_factor"],
                "ev_bar": p["ev_por_barra"], "bars": p["bars_medio"],
                "indep": r["forensia_F3"].get("independencia"),
            })

    # ── RE-EVALUACIÓN de señales retiradas/degradadas con el método nuevo ──
    # Solo las retiradas por fire-rate o lift (no duplicados ni pivot_type).
    REEVALUAR = ["breadth_contraction_exit", "credit_ease_exit",
                 "regime_change_exit", "skew_paranoia_exit"]
    filas_reeval = []
    print(f"\n{'='*110}\nRE-EVALUACIÓN de señales retiradas (juzgadas con método antiguo)")
    print(f"{'='*110}")
    for s in REEVALUAR:
        r = evaluar(s, reevaluar=True)
        reporte[f"REEVAL_{s}"] = r
        st = r.get("status")
        print(f"{s:32s} → {st}")
        if st != "OK":
            continue
        mejor = None
        for celda, p in r["perfil_3d_régimen"].items():
            if p["n"] < 10:
                continue
            if mejor is None or p["fav_neto"] > r["perfil_3d_régimen"][mejor]["fav_neto"]:
                mejor = celda
        if mejor:
            p = r["perfil_3d_régimen"][mejor]
            filas_reeval.append({
                "señal": s, "celda": mejor, "n": p["n"], "tier": p["confidence_tier"],
                "hit": p["hit_rate"], "hit_neto": p["hit_neto"],
                "fav_neto": p["fav_neto"], "p": p["p_value"], "pf": p["profit_factor"],
                "ev_bar": p["ev_por_barra"], "bars": p["bars_medio"],
                "indep": r["forensia_F3"].get("independencia"),
            })

    out = ROOT / "data/research/signals/evaluacion_vela_a_vela_v7_final.json"
    out.write_text(json.dumps(reporte, indent=2, ensure_ascii=False, default=str))

    print(f"\n{'='*118}\nRANKING FINAL v7 — mejor celda por señal (favorable neto vs baseline, first-passage)")
    print(f"{'='*118}")
    print(f"{'señal':>24s} {'celda':>13s} | {'n':>3s} {'tier':>9s} | {'hit':>5s} {'Δhit':>6s} | "
          f"{'neto':>7s} {'p-val':>7s} {'PF':>5s} {'EV/b':>8s} {'bars':>5s} {'INDEP':>6s}")
    filas_ranking.sort(key=lambda x: -x["fav_neto"])
    for f in filas_ranking:
        d = "💎" if f["diamante"] else ""
        p = f["p"] if f["p"] is not None else float("nan")
        pf = f["pf"] if f["pf"] is not None else float("nan")
        hn = f["hit_neto"] if f["hit_neto"] is not None else float("nan")
        ev = f["ev_bar"] if f["ev_bar"] is not None else float("nan")
        indep = f["indep"] if f["indep"] is not None else float("nan")
        sig = "✓" if not np.isnan(p) and p < 0.05 else ("m" if not np.isnan(p) and p < 0.10 else "")
        print(f"{f['señal']:>24s} {f['celda']:>13s} | {f['n']:>3d} {f['tier']+d:>10s} | "
              f"{f['hit']:>4.0%} {hn:>+5.1%} | {f['fav_neto']:>+6.2%} {p:>7.4f} "
              f"{pf:>5.2f} {ev:>+7.4f} {f['bars']:>5.1f} {indep:>5.0%} {sig}")
    print(f"\n✓ = p<0.05 | m = p<0.10 | 💎 = DIAMANTE (N<21, §3.3)")
    print(f"INDEP = Independencia Informacional (Opción C): % de fallos únicos de la señal.")
    print(f"        Alto = aporta información nueva al ensemble. Bajo = redundante (familia).")

    if filas_reeval:
        print(f"\n{'='*118}\nRESULTADO RE-EVALUACIÓN (retiradas con método antiguo)")
        print(f"{'='*118}")
        print(f"{'señal':>24s} {'celda':>13s} | {'n':>3s} {'tier':>9s} | {'hit':>5s} {'Δhit':>6s} | "
              f"{'neto':>7s} {'p-val':>7s} {'PF':>5s} {'EV/b':>8s} {'bars':>5s} {'INDEP':>6s}")
        for f in sorted(filas_reeval, key=lambda x: -x["fav_neto"]):
            p = f["p"] if f["p"] is not None else float("nan")
            pf = f["pf"] if f["pf"] is not None else float("nan")
            hn = f["hit_neto"] if f["hit_neto"] is not None else float("nan")
            ev = f["ev_bar"] if f["ev_bar"] is not None else float("nan")
            indep = f["indep"] if f["indep"] is not None else float("nan")
            sig = "✓" if not np.isnan(p) and p < 0.05 else ("m" if not np.isnan(p) and p < 0.10 else "")
            print(f"{f['señal']:>24s} {f['celda']:>13s} | {f['n']:>3d} {f['tier']:>9s} | "
                  f"{f['hit']:>4.0%} {hn:>+5.1%} | {f['fav_neto']:>+6.2%} {p:>7.4f} "
                  f"{pf:>5.2f} {ev:>+7.4f} {f['bars']:>5.1f} {indep:>5.0%} {sig}")
    print(f"\n✅ Guardado: {out}")
