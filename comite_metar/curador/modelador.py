# -*- coding: utf-8 -*-
"""
modelador.py — Fase 4. Modelador OOS walk-forward del Comité METAR.

Recorre los episodios en orden cronológico y, para CADA uno, registra si la
dirección que el comité (y cada estación individual) anticipó coincide con la
dirección del PIVOTE REAL siguiente del lake. El pivote es la verdad realizada
post-t que se usa ÚNICAMENTE para scoring; jamás retroalimenta la decisión de
los agentes en t (sin lookahead — ver estado_en / Agente.leer).

Rigor OOS:
  - Cada episodio se evalúa con el estado observable SOLO en t.
  - Partición temporal: train < 2020, test >= 2023. El único parámetro libre
    (umbral `min_net` de la señal confluente) se TUNEA en train y se CONGELA
    antes de evaluar test. Reporte deflated (test) y raw (todo el walk-fwd).
  - De-clustering = credibilidad: se procesan todos los episodios.
  - Significancia vs nulo 50% (binomial, scipy).
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from comite_metar.scripts import common
from comite_metar.curador.curador import _norm_dir

HORIZONTE_DEFAULT = 80            # ventana del pivote próximo (barras)
CORTE_TRAIN = "2020-01-01"        # episodios < corte forman el train (tune)
CORTE_TEST = "2023-01-01"         # partición temporal OOS reportada


# ---------------------------------------------------------------------------
# Pivote real (solo scoring, NUNCA al estado de decisión)
# ---------------------------------------------------------------------------
def pivote_pred(df: pd.DataFrame, t: int, horizon: int = HORIZONTE_DEFAULT
                ) -> Optional[Dict]:
    """Dirección del pivote próximo del SPY tras t (primer extremo alcanzado).

    Barre (t, t+horizon] sobre spy_close y decide qué extremo (máx o mín) se
    alcanza PRIMERO. Dirección = dirección del movimiento que lo produce:
    máximo primero -> 'ALZA'; mínimo primero -> 'BAJA'. None si la ventana es
    vacía o el pivote es plano (max==min).
    """
    seg = df.iloc[t + 1: t + 1 + horizon]
    if len(seg) < 1:
        return None
    c = seg["spy_close"].to_numpy(dtype=float)
    imax = int(np.argmax(c))
    imin = int(np.argmin(c))
    if imax == imin:
        return None
    if imax < imin:
        direc, pos, extremo = "ALZA", imax, float(c[imax])
    else:
        direc, pos, extremo = "BAJA", imin, float(c[imin])
    base = float(df.iloc[t]["spy_close"])
    return {
        "pivote_direccion": direc,
        "posicion_pivote": t + 1 + pos,
        "fecha_pivote": str(seg.index[pos]),
        "retorno": round(float(extremo - base), 6),
        "horizonte": int(len(seg)),
    }


# ---------------------------------------------------------------------------
# Estadística binomial vs nulo 50%
# ---------------------------------------------------------------------------
def p_binario(aciertos: int, total: int) -> Dict:
    if total <= 0:
        return {"n": 0, "hit_rate": 0.0, "p_two_sided": None,
                "p_greater": None, "deflated": False}
    hr = aciertos / total
    bt = binomtest(int(aciertos), int(total), 0.5)
    return {
        "n": int(total),
        "hit_rate": round(hr, 4),
        "p_two_sided": round(float(bt.pvalue), 6),
        "p_greater": round(float(binomtest(int(aciertos), int(total), 0.5,
                                           alternative="greater").pvalue), 6),
        "deflated": bool(hr <= 0.5),
    }


def metricas(hits: int, total: int, baseline: Optional[float] = None
             ) -> Dict:
    """Accuracy, lift y p-value binomial vs nulo 50% para un conjunto."""
    if total <= 0:
        return {"n_episodios_con_senal": 0, "hits": 0, "accuracy": 0.0,
                "baseline": baseline, "lift": None, "p_value_two_sided": None,
                "p_value_greater": None, "deflated": False}
    p = p_binario(hits, total)
    acc = p["hit_rate"]
    baseline = baseline if baseline is not None else 0.5
    lift = (acc - baseline) / baseline if baseline > 0 else None
    return {
        "n_episodios_con_senal": int(total),
        "hits": int(hits),
        "accuracy": acc,
        "baseline": round(baseline, 4),
        "lift": round(lift, 4) if lift is not None else None,
        "p_value_two_sided": p["p_two_sided"],
        "p_value_greater": p["p_greater"],
        "deflated": p["deflated"],
    }


# ---------------------------------------------------------------------------
# Walk-forward completo: agentes + curador + pivote real + registro.
# ---------------------------------------------------------------------------
def walk_forward(df: pd.DataFrame, anticuerpos: List,
                 episodios: List[Dict], *,
                 punto: str = "t0",
                 horizon: int = HORIZONTE_DEFAULT,
                 max_episodios: Optional[int] = None) -> Dict:
    """Ejecuta el comité end-to-end sobre los episodios y devuelve el registro.

    Returns
    -------
    dict:
        episodios     : list[Dict] — registro forense por episodio
        tally_estacion: {estacion: {hits, n, contra, dirs:{ALZA,BAJA}}}
        n_procesados  : int
    """
    from comite_metar.curador import curador as cu

    if max_episodios:
        episodios = episodios[:max_episodios]

    frames: List[Dict] = []
    tally_est: Dict[str, Dict] = {}

    for ep in episodios:
        pos = ep.get(punto)
        if pos is None:
            continue
        lecturas = [ag.leer(pos, episodio=ep) for ag in anticuerpos]
        fusion = cu.fuse(lecturas, ep)
        pr = pivote_pred(df, pos, horizon)

        confdir = fusion["confluencia"]["direccion_confluente"]
        conf_hit = None
        if pr and confdir in ("ALZA", "BAJA"):
            conf_hit = bool(confdir == pr["pivote_direccion"])

        # scoring por estación
        hits_est: Dict[str, Dict] = {}
        for r in lecturas:
            est = r.get("estacion") or ""
            lec = r.get("lectura")
            if not lec or not isinstance(lec, dict):
                continue
            sd = lec.get("direccion_anticipada_spy")
            sd = _norm_dir(sd)
            if sd not in ("ALZA", "BAJA"):
                continue
            hit = None if pr is None else bool(sd == pr["pivote_direccion"])
            hits_est[est] = {"pred": sd, "conv": lec.get("conviccion"),
                             "rol": lec.get("rol_precognitivo"), "hit": hit}
            if pr is not None:
                taccum = tally_est.setdefault(
                    est, {"hits": 0, "n": 0, "contra": 0,
                          "dirs": {"ALZA": 0, "BAJA": 0}})
                taccum["n"] += 1
                taccum["dirs"][sd] += 1
                if hit:
                    taccum["hits"] += 1
                else:
                    taccum["contra"] += 1

        frames.append({
            "episodio_id": ep.get("episodio_id"),
            "t0": pos,
            "fecha": str(ep.get("fecha_inicio")),
            "punto_decision": punto,
            "lecturas": fusion.get("lecturas_utilizadas") or [],
            "confluencia": fusion.get("confluencia"),
            "señal_contradictoria": fusion.get("señal_contradictoria"),
            "flujo_neto": fusion.get("flujo_neto"),
            "alerta": fusion.get("alerta"),
            "pivote_real": pr,
            "hit_confluente": conf_hit,
            "hits_por_estacion": hits_est,
        })

    return {"episodios": frames, "tally_estacion": tally_est,
            "n_procesados": len(frames)}


# ---------------------------------------------------------------------------
# Validación temporal OOS (train tune / test report). Sin fuga de datos.
# ---------------------------------------------------------------------------
def validar_oos(registro: List[Dict], *,
                corte_train: str = CORTE_TRAIN,
                corte_test: str = CORTE_TEST) -> Dict:
    """Tune `min_net` en train (< corte_train), congela y evalúa test.

    `flujo_neto` de la fusión es un score con signo. El comité "opera" si
    |flujo_neto| >= T, prediciendo el signo del flujo (ALZA si >0, BAJA si <0).
    En train se barre T ∈ {0.0..4.0 step 0.1} maximizando accuracy con una
    cobertura mínima del 25% (para que no sea todo-nada). El T óptimo se
    congela y se aplica tal cual a test (>= corte_test): es el reporte
    deflated (tradeable OOS). También se reporta el hit rate RAW de la
    confluencia (sin umbral) sobre test para transparencia.

    Episodios sin señal direccional (flujo_neto==0) -> 'neutro' (no apuesta):
    alimentan cobertura, no accuracy.
    """
    stats: Dict = {
        "corte_train": corte_train,
        "corte_test": corte_test,
        "baseline": 0.5,
        "n_pivotes_test": 0,
        "umbral_T_optimo": 0.0,
        "raw_confluencia_test": {},
        "train": {},
        "test_tunado": {},
        "ejemplos_test": [],
        "contable_nota": ("Report test_tunado = deflated (T congelado en train); "
                          "raw_confluencia_test = accuracy direccional bruta de "
                          "la confluencia (sin umbral) sobre test."),
    }
    fechas = [pd.Timestamp(e["fecha"]) for e in registro]
    t_train = pd.Timestamp(corte_train)
    t_test = pd.Timestamp(corte_test)
    train_rows = [e for e, f in zip(registro, fechas) if f < t_train]
    test_rows = [e for e, f in zip(registro, fechas) if f >= t_test]

    # baseline mayoritaria de pivotes en test (naive)
    pvs = [e["pivote_real"]["pivote_direccion"] for e in test_rows
           if e.get("pivote_real")]
    if pvs:
        baseline = max(pvs.count("ALZA") / len(pvs), 1 - pvs.count("ALZA") / len(pvs))
        stats["baseline"] = round(baseline, 4)
    stats["n_pivotes_test"] = len(pvs)

    # tuple de predicción desde el flujo
    def _pred(f):
        if not f:
            return None
        return "ALZA" if f > 0 else "BAJA"

    # --- tune T en train ---------------------------------------------------
    best_T, best_score = None, None
    T_vals = [round(i * 0.1, 2) for i in range(0, 41)]      # 0.0..4.0
    for T in T_vals:
        hits = tot = 0
        for e in train_rows:
            f = e.get("flujo_neto")
            pr = e.get("pivote_real")
            if f is None or pr is None or abs(f) < T:
                continue
            pred = _pred(f)
            if pred is None:
                continue
            tot += 1
            hits += int(pred == pr["pivote_direccion"])
        if tot == 0:
            continue
        acc = hits / tot
        cov = tot / max(len(train_rows), 1)
        if cov < 0.25:                    # cobertura mínima
            continue
        score = acc + cov
        if best_score is None or score > best_score:
            best_score, best_T = score, T

    T = best_T if best_T is not None else 0.0
    stats["umbral_T_optimo"] = T

    # evaluación con T congelado
    def _eval(rows):
        hits = tot = 0
        corpus = []
        for r in rows:
            f = r.get("flujo_neto")
            pr = r.get("pivote_real")
            if f is None or pr is None or abs(f) < T:
                continue
            pred = _pred(f)
            if pred is None:
                continue
            tot += 1
            hit = int(pred == pr["pivote_direccion"])
            hits += hit
            corpus.append((r.get("episodio_id"), r.get("fecha"), round(f, 2),
                           pred, pr["pivote_direccion"], bool(hit)))
        return {"hits": hits, "total": tot, "corpus": corpus}

    tr = _eval(train_rows)
    te = _eval(test_rows)
    stats["train"] = metricas(tr["hits"], tr["total"], stats["baseline"])
    stats["train"]["n_episodios"] = len(train_rows)
    stats["test_tunado"] = metricas(te["hits"], te["total"], stats["baseline"])
    stats["test_tunado"]["n_episodios"] = len(test_rows)
    stats["test_tunado"]["porcentaje_con_importancia"] = {  # cobertura en test
        "episodios_con_senal_net": te["total"],
        "total_test": len(test_rows),
        "cobertura_pct": round(te["total"] / max(len(test_rows), 1), 4),
    }
    stats["ejemplos_test"] = te["corpus"][:25]

    # raw confluencia (sin umbral) sobre test — transparencia
    raw_hits = raw_tot = 0
    for r in test_rows:
        cf = r.get("confluencia") or {}
        pr = r.get("pivote_real")
        if cf.get("direccion_confluente") not in ("ALZA", "BAJA") or not pr:
            continue
        pred = cf["direccion_confluente"]
        raw_tot += 1
        raw_hits += int(pred == pr["pivote_direccion"])
    stats["raw_obra"] = "confluencia_sin_umbral"
    stats["raw_confluencia_test"] = metricas(raw_hits, raw_tot, stats["baseline"])
    stats["raw_confluencia_test"]["cobertura"] = round(
        raw_tot / max(len(test_rows), 1), 4)
    return stats