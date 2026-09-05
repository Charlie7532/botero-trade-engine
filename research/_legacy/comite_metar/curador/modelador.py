# -*- coding: utf-8 -*-
"""
modelador.py — Fase 4. Modelador OOS walk-forward del Comité METAR.

Recorre los episodios en orden cronológico y, para CADA uno, registra si la
dirección que el comité (y cada estación individual) anticipó coincide con la
dirección del PIVOTE REAL siguiente del lake bajo la Metrología Opción C Canónica
(First-Passage intrabar OHLC sobre spy_high y spy_low en la Triada zz25/zz50/zz75,
sin time-stop fijo de velas).

Rigor OOS:
  - Cada episodio se evalúa con el estado observable SOLO en t (sin lookahead).
  - Partición temporal: train < 2020, test >= 2023. El umbral `min_net` (T)
    se TUNEA en train sobre zz25 y se CONGELA antes de evaluar test.
  - Baseline real: la hipótesis nula del test binomial es la frecuencia de la clase
    mayoritaria observada bajo Opción C (nunca un 50% fijo cuando hay asimetría).
  - Embargo temporal (purga): se reportan métricas nominales y métricas sobre
    muestras independientes (sin solapamiento forward en el viaje de resolución).
  - Resolución de frontera: si un evento en el tail no toca barrera antes del fin
    de la serie, se marca resuelto: False y se excluye de accuracy, reportando
    resolution_rate.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from comite_metar.scripts import common
from comite_metar.curador.curador import _norm_dir

SCALES = {"zz25": 0.025, "zz50": 0.050, "zz75": 0.075}
HORIZONTE_DEFAULT = 80            # mantenido por compatibilidad de firma
CORTE_TRAIN = "2020-01-01"        # episodios < corte forman el train (tune)
CORTE_TEST = "2023-01-01"         # partición temporal OOS reportada


# ---------------------------------------------------------------------------
# Pivote real Opción C Canónica (Triada First-Passage OHLC intrabar)
# ---------------------------------------------------------------------------
def pivote_pred(df: pd.DataFrame, t: int, horizon: Optional[int] = None
                ) -> Optional[Dict]:
    """Dirección del pivote del SPY tras t bajo Opción C Canónica (Triada OHLC).

    Evalúa first-passage intrabar sobre spy_high y spy_low para:
      - zz25: ±2.5%
      - zz50: ±5.0%
      - zz75: ±7.5%
    Sin time-stop fijo de velas. Si ninguna barrera se toca antes del final del lake,
    resuelto=False.
    """
    n = len(df)
    if not (0 <= t < n - 1):
        return None

    close = df["spy_close"].values
    highs = df["spy_high"].values
    lows = df["spy_low"].values

    p0 = float(close[t])
    if p0 <= 0:
        return None

    path_h = highs[t + 1:]
    path_l = lows[t + 1:]
    n_forward = len(path_h)
    if n_forward < 1:
        return None

    res_triada: Dict[str, Dict] = {}
    for name, s in SCALES.items():
        fav_barrier = p0 * (1.0 + s)
        adv_barrier = p0 * (1.0 - s)
        h_hits = np.where(path_h >= fav_barrier)[0]
        l_hits = np.where(path_l <= adv_barrier)[0]
        f_h = int(h_hits[0]) if len(h_hits) > 0 else 999999
        f_l = int(l_hits[0]) if len(l_hits) > 0 else 999999

        if f_h == 999999 and f_l == 999999:
            res_triada[name] = {
                "direccion": None,
                "bars": n_forward,
                "resuelto": False,
                "scale": s,
            }
        elif f_h < f_l:
            res_triada[name] = {
                "direccion": "ALZA",
                "bars": f_h + 1,
                "resuelto": True,
                "scale": s,
            }
        else:
            res_triada[name] = {
                "direccion": "BAJA",
                "bars": f_l + 1,
                "resuelto": True,
                "scale": s,
            }

    p_25 = res_triada["zz25"]
    pos_abs = t + 1 + (p_25["bars"] - 1) if p_25["resuelto"] else None
    fecha_piv = str(df.index[min(pos_abs, n - 1)]) if pos_abs is not None else None

    return {
        "zz25": res_triada["zz25"],
        "zz50": res_triada["zz50"],
        "zz75": res_triada["zz75"],
        "pivote_direccion": p_25["direccion"],
        "posicion_pivote": pos_abs,
        "fecha_pivote": fecha_piv,
        "retorno": round(float(p0 * SCALES["zz25"] * (1 if p_25["direccion"] == "ALZA" else -1)), 6) if p_25["resuelto"] else 0.0,
        "horizonte": p_25["bars"],
        "bars": p_25["bars"],
        "resuelto": p_25["resuelto"],
        "sin_time_stop": True,
    }


# ---------------------------------------------------------------------------
# Estadística binomial contra baseline real
# ---------------------------------------------------------------------------
def p_binario(aciertos: int, total: int, baseline: Optional[float] = None) -> Dict:
    """Test binomial unilateral y bilateral contra la hipótesis nula del baseline real."""
    p_null = float(baseline) if baseline is not None and baseline > 0 else 0.5
    if total <= 0:
        return {"n": 0, "hit_rate": 0.0, "baseline": round(p_null, 4),
                "p_two_sided": None, "p_greater": None, "deflated": False}
    hr = aciertos / total
    bt = binomtest(int(aciertos), int(total), p_null)
    bt_g = binomtest(int(aciertos), int(total), p_null, alternative="greater")
    return {
        "n": int(total),
        "hit_rate": round(hr, 4),
        "baseline": round(p_null, 4),
        "p_two_sided": round(float(bt.pvalue), 6),
        "p_greater": round(float(bt_g.pvalue), 6),
        "deflated": bool(hr <= p_null),
    }


def metricas(hits: int, total: int, baseline: Optional[float] = None
             ) -> Dict:
    """Accuracy, lift y p-value binomial vs baseline real para un conjunto."""
    b_val = baseline if baseline is not None and baseline > 0 else 0.5
    if total <= 0:
        return {"n_episodios_con_senal": 0, "hits": 0, "accuracy": 0.0,
                "baseline": round(b_val, 4), "lift": None, "p_value_two_sided": None,
                "p_value_greater": None, "deflated": False}
    p = p_binario(hits, total, baseline=b_val)
    acc = p["hit_rate"]
    lift = (acc - b_val) / b_val if b_val > 0 else None
    return {
        "n_episodios_con_senal": int(total),
        "hits": int(hits),
        "accuracy": acc,
        "baseline": round(b_val, 4),
        "lift": round(lift, 4) if lift is not None else None,
        "p_value_two_sided": p["p_two_sided"],
        "p_value_greater": p["p_greater"],
        "deflated": p["deflated"],
    }


def clopper_pearson_ci(hits: int, total: int, alpha: float = 0.05) -> Tuple[Optional[float], Optional[float]]:
    """Intervalo de confianza Clopper-Pearson exacto al (1 - alpha)%."""
    if total <= 0:
        return None, None
    bt = binomtest(hits, total)
    ci = bt.proportion_ci(confidence_level=1.0 - alpha, method="exact")
    return round(float(ci.low), 4), round(float(ci.high), 4)


def edge_direccional(n_alza: int, hits_alza: int, n_baja: int, hits_baja: int,
                     baseline_alza: float, baseline_baja: float) -> Dict:
    """Calcula métricas direccional-condicionadas con edge aditivo (pp) vs baselines propios.

    Principio de López de Prado: probar contra la clase mayoritaria que la señal predice,
    no contra un baseline global agregado.
    """
    acc_a = round(hits_alza / n_alza, 4) if n_alza > 0 else None
    acc_b = round(hits_baja / n_baja, 4) if n_baja > 0 else None

    # Edge aditivo en puntos porcentuales (no lift relativo, coherente con PASO_EDGE = 0.03)
    edge_a = round(acc_a - baseline_alza, 4) if acc_a is not None else None
    edge_b = round(acc_b - baseline_baja, 4) if acc_b is not None else None

    p_a = None
    if n_alza > 0:
        bt_a = binomtest(hits_alza, n_alza, baseline_alza, alternative="greater")
        p_a = round(float(bt_a.pvalue), 6)

    p_b = None
    if n_baja > 0:
        bt_b = binomtest(hits_baja, n_baja, baseline_baja, alternative="greater")
        p_b = round(float(bt_b.pvalue), 6)

    ci_a_low, ci_a_high = clopper_pearson_ci(hits_alza, n_alza) if n_alza > 0 else (None, None)
    ci_b_low, ci_b_high = clopper_pearson_ci(hits_baja, n_baja) if n_baja > 0 else (None, None)

    n_tot = n_alza + n_baja
    h_tot = hits_alza + hits_baja
    if n_tot > 0:
        base_cond = round((n_alza * baseline_alza + n_baja * baseline_baja) / n_tot, 4)
        acc_tot = round(h_tot / n_tot, 4)
        edge_comb = round(acc_tot - base_cond, 4)
        ci_tot_low, ci_tot_high = clopper_pearson_ci(h_tot, n_tot)
    else:
        base_cond = acc_tot = edge_comb = None
        ci_tot_low = ci_tot_high = None

    return {
        "n_alza": n_alza,
        "hits_alza": hits_alza,
        "accuracy_alza": acc_a,
        "baseline_alza": round(baseline_alza, 4),
        "edge_alza": edge_a,
        "p_greater_alza": p_a,
        "ci95_alza": [ci_a_low, ci_a_high],

        "n_baja": n_baja,
        "hits_baja": hits_baja,
        "accuracy_baja": acc_b,
        "baseline_baja": round(baseline_baja, 4),
        "edge_baja": edge_b,
        "p_greater_baja": p_b,
        "ci95_baja": [ci_b_low, ci_b_high],

        "n_total": n_tot,
        "hits_total": h_tot,
        "accuracy_total": acc_tot,
        "baseline_condicionado": base_cond,
        "edge_combinado": edge_comb,
        "ci95_total": [ci_tot_low, ci_tot_high],
    }


def crear_tally_estacion() -> Dict:
    """Estructura de tally tri-escala, direccional y operacional por estación."""
    return {
        "n": 0, "hits": 0, "contra": 0,
        "dirs": {"ALZA": 0, "BAJA": 0},
        "hits_zz50": 0, "hits_zz75": 0,
        "n_alza": 0, "hits_alza": 0,
        "n_baja": 0, "hits_baja": 0,
        "n_operacional": 0, "hits_operacional": 0,
        "n_bruto": 0, "hits_bruto": 0,
        "escalas": {
            sc: {
                "n_alza": 0, "hits_alza": 0, "n_baja": 0, "hits_baja": 0,
                "n_op_alza": 0, "hits_op_alza": 0, "n_op_baja": 0, "hits_op_baja": 0,
                "n_operacional": 0, "hits_operacional": 0,
                "n_bruto": 0, "hits_bruto": 0,
            }
            for sc in ("zz25", "zz50", "zz75")
        }
    }


def tally_desde_frames(frames: List[Dict]) -> Dict[str, Dict]:
    """Genera el tally direccional, operacional y tri-escala a partir de una lista de frames."""
    tally: Dict[str, Dict] = {}
    for f in frames:
        pr = f.get("pivote_real")
        hits_est = f.get("hits_por_estacion") or {}
        for est, h in hits_est.items():
            sd = h.get("pred")
            if sd not in ("ALZA", "BAJA"):
                continue
            accion = h.get("accion", "OBSERVAR")
            es_op = (accion in ("ENTRADA", "COBERTURA"))
            taccum = tally.setdefault(est, crear_tally_estacion())

            for sc in ("zz25", "zz50", "zz75"):
                sc_info = pr.get(sc) if pr else None
                if not sc_info or not sc_info.get("resuelto"):
                    continue
                gt_dir = sc_info.get("direccion")
                hit_sc = bool(sd == gt_dir)

                sc_data = taccum["escalas"][sc]
                sc_data["n_bruto"] += 1
                if hit_sc:
                    sc_data["hits_bruto"] += 1

                if sd == "ALZA":
                    sc_data["n_alza"] += 1
                    if hit_sc:
                        sc_data["hits_alza"] += 1
                    if es_op:
                        sc_data["n_op_alza"] += 1
                        if hit_sc:
                            sc_data["hits_op_alza"] += 1
                elif sd == "BAJA":
                    sc_data["n_baja"] += 1
                    if hit_sc:
                        sc_data["hits_baja"] += 1
                    if es_op:
                        sc_data["n_op_baja"] += 1
                        if hit_sc:
                            sc_data["hits_op_baja"] += 1

                if es_op:
                    sc_data["n_operacional"] += 1
                    if hit_sc:
                        sc_data["hits_operacional"] += 1

                if sc == "zz25":
                    taccum["n"] += 1
                    taccum["dirs"][sd] += 1
                    taccum["n_bruto"] = sc_data["n_bruto"]
                    taccum["hits_bruto"] = sc_data["hits_bruto"]
                    taccum["n_alza"] = sc_data["n_alza"]
                    taccum["hits_alza"] = sc_data["hits_alza"]
                    taccum["n_baja"] = sc_data["n_baja"]
                    taccum["hits_baja"] = sc_data["hits_baja"]
                    taccum["n_operacional"] = sc_data["n_operacional"]
                    taccum["hits_operacional"] = sc_data["hits_operacional"]
                    if hit_sc:
                        taccum["hits"] += 1
                    else:
                        taccum["contra"] += 1
                elif sc == "zz50" and hit_sc:
                    taccum["hits_zz50"] += 1
                elif sc == "zz75" and hit_sc:
                    taccum["hits_zz75"] += 1

    return tally


# ---------------------------------------------------------------------------
# Walk-forward completo: agentes + curador + pivote real Opción C + registro.
# ---------------------------------------------------------------------------
def walk_forward(df: pd.DataFrame, anticuerpos: List,
                 episodios: List[Dict], *,
                 punto: str = "t0",
                 horizon: Optional[int] = None,
                 max_episodios: Optional[int] = None) -> Dict:
    """Ejecuta el comité end-to-end sobre los episodios con ground truth Opción C Triada."""
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
        pr = pivote_pred(df, pos, horizon=horizon)

        confdir = fusion["confluencia"]["direccion_confluente"]
        conf_hits: Dict[str, Optional[bool]] = {}
        for sc in ("zz25", "zz50", "zz75"):
            sc_info = pr.get(sc) if pr else None
            if sc_info and sc_info.get("resuelto") and confdir in ("ALZA", "BAJA"):
                conf_hits[sc] = bool(confdir == sc_info["direccion"])
            else:
                conf_hits[sc] = None

        conf_hit_25 = conf_hits.get("zz25")

        # scoring por estación (tri-escala)
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

            hit_sc: Dict[str, Optional[bool]] = {}
            for sc in ("zz25", "zz50", "zz75"):
                sc_info = pr.get(sc) if pr else None
                if sc_info and sc_info.get("resuelto"):
                    hit_sc[sc] = bool(sd == sc_info["direccion"])
                else:
                    hit_sc[sc] = None

            hit_primary = hit_sc.get("zz25")
            hits_est[est] = {
                "pred": sd,
                "conv": lec.get("conviccion"),
                "accion": lec.get("accion", "OBSERVAR"),
                "rol": lec.get("rol_precognitivo"),
                "hit": hit_primary,
                "hit_zz25": hit_sc.get("zz25"),
                "hit_zz50": hit_sc.get("zz50"),
                "hit_zz75": hit_sc.get("zz75"),
            }

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
            "hit_confluente": conf_hit_25,
            "hit_confluente_triada": conf_hits,
            "hits_por_estacion": hits_est,
        })

    tally_est = tally_desde_frames(frames)
    return {"episodios": frames, "tally_estacion": tally_est,
            "n_procesados": len(frames)}


# ---------------------------------------------------------------------------
# Validación temporal OOS (train tune / test report con embargo temporal)
# ---------------------------------------------------------------------------
def validar_oos(registro: List[Dict], *,
                corte_train: str = CORTE_TRAIN,
                corte_test: str = CORTE_TEST) -> Dict:
    """Tune `min_net` en train (< corte_train) sobre zz25, congela y evalúa test.

    Incluye:
      - Métricas Triada Canónica (zz25, zz50, zz75).
      - Baselines reales de clase mayoritaria y direccional-condicionados en test por escala.
      - Embargo temporal (purga de solapamiento forward) -> N_nominal vs N_indep.
      - Tasa de resolución de frontera temporal.
      - Tally direccional y tri-escala OOS en test y train.
    """
    stats: Dict = {
        "corte_train": corte_train,
        "corte_test": corte_test,
        "baseline": 0.5,
        "baselines_triada": {},
        "baselines_alza_test": {},
        "baselines_baja_test": {},
        "n_pivotes_test": 0,
        "resolution_rates_test": {},
        "umbral_T_optimo": 0.0,
        "raw_confluencia_test": {},
        "raw_confluencia_triada_test": {},
        "train": {},
        "test_tunado": {},
        "test_tunado_triada": {},
        "embargo_temporal": {},
        "ejemplos_test": [],
        "contable_nota": ("Report test_tunado = deflated (T congelado en train sobre zz25); "
                          "evaluación contra baselines reales bajo Opción C Canónica."),
    }
    fechas = [pd.Timestamp(e["fecha"]) for e in registro]
    t_train = pd.Timestamp(corte_train)
    t_test = pd.Timestamp(corte_test)
    train_rows = [e for e, f in zip(registro, fechas) if f < t_train]
    test_rows = [e for e, f in zip(registro, fechas) if f >= t_test]

    # Baselines en train y test
    pvs_tr = [
        e["pivote_real"]["zz25"]["direccion"]
        for e in train_rows
        if e.get("pivote_real") and e["pivote_real"].get("zz25", {}).get("resuelto")
    ]
    b_tr_alza = pvs_tr.count("ALZA") / len(pvs_tr) if pvs_tr else 0.5
    b_tr_baja = pvs_tr.count("BAJA") / len(pvs_tr) if pvs_tr else 0.5
    b_train = round(max(b_tr_alza, b_tr_baja), 4) if pvs_tr else 0.5
    stats["baseline_train_zz25"] = b_train
    stats["baseline_train_alza_zz25"] = round(b_tr_alza, 4)
    stats["baseline_train_baja_zz25"] = round(b_tr_baja, 4)

    baselines = {}
    baselines_alza = {}
    baselines_baja = {}
    res_rates = {}
    for sc in ("zz25", "zz50", "zz75"):
        pvs = [
            e["pivote_real"][sc]["direccion"]
            for e in test_rows
            if e.get("pivote_real") and e["pivote_real"].get(sc, {}).get("resuelto")
        ]
        if pvs:
            p_a = pvs.count("ALZA") / len(pvs)
            p_b = pvs.count("BAJA") / len(pvs)
            b = max(p_a, p_b)
        else:
            p_a = p_b = b = 0.5
        baselines[sc] = round(b, 4)
        baselines_alza[sc] = round(p_a, 4)
        baselines_baja[sc] = round(p_b, 4)
        res_rates[sc] = round(len(pvs) / max(len(test_rows), 1), 4)

    b_primary = baselines["zz25"]
    stats["baseline"] = b_primary
    stats["baselines_triada"] = baselines
    stats["baselines_alza_test"] = baselines_alza
    stats["baselines_baja_test"] = baselines_baja
    stats["resolution_rates_test"] = res_rates
    stats["n_pivotes_test"] = len([
        e for e in test_rows
        if e.get("pivote_real") and e["pivote_real"].get("zz25", {}).get("resuelto")
    ])

    def _pred(f):
        if not f:
            return None
        return "ALZA" if f > 0 else "BAJA"

    # --- tune T en train sobre escala táctica zz25 -------------------------
    best_T, best_score = None, None
    T_vals = [round(i * 0.1, 2) for i in range(0, 41)]      # 0.0..4.0
    for T in T_vals:
        hits = tot = 0
        for e in train_rows:
            f = e.get("flujo_neto")
            pr = e.get("pivote_real")
            if f is None or pr is None or abs(f) < T:
                continue
            sc_info = pr.get("zz25")
            if not sc_info or not sc_info.get("resuelto"):
                continue
            pred = _pred(f)
            if pred is None:
                continue
            tot += 1
            hits += int(pred == sc_info["direccion"])
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

    # --- evaluación en test con T congelado (multiescala + embargo) --------
    def _eval_escala(rows, scale_name, b_alza, b_baja):
        hits = tot = 0
        n_a = h_a = n_b = h_b = 0
        corpus = []
        for r in rows:
            f = r.get("flujo_neto")
            pr = r.get("pivote_real")
            if f is None or pr is None or abs(f) < T:
                continue
            sc_info = pr.get(scale_name)
            if not sc_info or not sc_info.get("resuelto"):
                continue
            pred = _pred(f)
            if pred is None:
                continue
            tot += 1
            gt = sc_info["direccion"]
            hit = int(pred == gt)
            hits += hit
            if pred == "ALZA":
                n_a += 1
                if hit:
                    h_a += 1
            elif pred == "BAJA":
                n_b += 1
                if hit:
                    h_b += 1

            corpus.append({
                "episodio_id": r.get("episodio_id"),
                "fecha": r.get("fecha"),
                "t0": r.get("t0"),
                "bars": sc_info.get("bars", 1),
                "flujo_neto": round(f, 2),
                "pred": pred,
                "pivote_direccion": sc_info["direccion"],
                "hit": bool(hit),
            })
        base_maj = max(b_alza, b_baja)
        m = metricas(hits, tot, base_maj)
        ed = edge_direccional(n_a, h_a, n_b, h_b, b_alza, b_baja)
        m["direccional"] = ed
        return m, corpus

    # Train eval en zz25 (con baseline de train)
    tr_m, tr_corpus = _eval_escala(train_rows, "zz25", b_tr_alza, b_tr_baja)
    stats["train"] = tr_m
    stats["train"]["n_episodios"] = len(train_rows)

    # Test triada eval
    te_triada = {}
    te_corpora = {}
    for sc in ("zz25", "zz50", "zz75"):
        m_sc, c_sc = _eval_escala(test_rows, sc, baselines_alza[sc], baselines_baja[sc])
        m_sc["n_episodios"] = len(test_rows)
        te_triada[sc] = m_sc
        te_corpora[sc] = c_sc

    stats["test_tunado_triada"] = te_triada
    stats["test_tunado"] = te_triada["zz25"]
    stats["test_tunado"]["porcentaje_con_importancia"] = {
        "episodios_con_senal_net": te_triada["zz25"]["n_episodios_con_senal"],
        "total_test": len(test_rows),
        "cobertura_pct": round(te_triada["zz25"]["n_episodios_con_senal"] / max(len(test_rows), 1), 4),
    }

    # Ejemplos de test (zz25)
    corpus_25 = te_corpora.get("zz25", [])
    stats["ejemplos_test"] = [
        (c["episodio_id"], c["fecha"], c["flujo_neto"], c["pred"],
         c["pivote_direccion"], c["hit"])
        for c in corpus_25[:25]
    ]

    # --- Embargo Temporal (purga de solapamiento forward) en zz25 ----------
    corpus_sorted = sorted(corpus_25, key=lambda c: c["t0"])
    corpus_indep = []
    last_end = -1
    for item in corpus_sorted:
        t0_ep = item["t0"]
        dur = item.get("bars", 8)
        if t0_ep > last_end:
            corpus_indep.append(item)
            last_end = t0_ep + dur

    hits_indep = sum(1 for c in corpus_indep if c["hit"])
    n_indep_a = sum(1 for c in corpus_indep if c["pred"] == "ALZA")
    h_indep_a = sum(1 for c in corpus_indep if c["pred"] == "ALZA" and c["hit"])
    n_indep_b = sum(1 for c in corpus_indep if c["pred"] == "BAJA")
    h_indep_b = sum(1 for c in corpus_indep if c["pred"] == "BAJA" and c["hit"])

    m_indep = metricas(hits_indep, len(corpus_indep), b_primary)
    ed_indep = edge_direccional(n_indep_a, h_indep_a, n_indep_b, h_indep_b,
                                baselines_alza["zz25"], baselines_baja["zz25"])
    m_indep["direccional"] = ed_indep

    stats["embargo_temporal"] = {
        "n_nominal": len(corpus_sorted),
        "n_indep": len(corpus_indep),
        "ratio_independencia": round(len(corpus_indep) / max(len(corpus_sorted), 1), 4),
        "metricas_indep_zz25": m_indep,
    }

    # --- Raw confluencia (sin umbral T) sobre test para las 3 escalas -------
    raw_triada = {}
    for sc in ("zz25", "zz50", "zz75"):
        raw_hits = raw_tot = 0
        rn_a = rh_a = rn_b = rh_b = 0
        for r in test_rows:
            cf = r.get("confluencia") or {}
            pr = r.get("pivote_real")
            if not pr:
                continue
            sc_info = pr.get(sc)
            if not sc_info or not sc_info.get("resuelto"):
                continue
            conf_dir = cf.get("direccion_confluente")
            if conf_dir not in ("ALZA", "BAJA"):
                continue
            raw_tot += 1
            gt = sc_info["direccion"]
            hit = int(conf_dir == gt)
            raw_hits += hit
            if conf_dir == "ALZA":
                rn_a += 1
                if hit:
                    rh_a += 1
            elif conf_dir == "BAJA":
                rn_b += 1
                if hit:
                    rh_b += 1
        m_raw = metricas(raw_hits, raw_tot, baselines[sc])
        m_raw["direccional"] = edge_direccional(rn_a, rh_a, rn_b, rh_b,
                                                baselines_alza[sc], baselines_baja[sc])
        m_raw["cobertura"] = round(raw_tot / max(len(test_rows), 1), 4)
        raw_triada[sc] = m_raw

    stats["raw_obra"] = "confluencia_sin_umbral_triada"
    stats["raw_confluencia_triada_test"] = raw_triada
    stats["raw_confluencia_test"] = raw_triada["zz25"]

    # Tallies desglosados para análisis OOS
    stats["tally_test"] = tally_desde_frames(test_rows)
    stats["tally_train"] = tally_desde_frames(train_rows)

    return stats