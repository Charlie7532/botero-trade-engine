#!/usr/bin/env python3
"""
VALIDADOR OOS — Catálogo v7 (capa separada del calificador post-mortem)
========================================================================
Pregunta: el edge medido por el evaluador vela a vela (post-mortem), ¿se
repite cuando la celda se elige SOLO con datos pasados?

Método (walk-forward ANCLADO, estándar del plan inventario_validacion_final):
  Folds cronológicos: train = [inicio, t), test = [t, t+BLOQUE)
  1. En TRAIN: medir favorable neto por celda (escala×régimen) y elegir la
     mejor celda con N≥N_MIN_TRAIN (selección con solo datos pasados).
  2. En TEST: medir la celda elegida. Baseline = pivotes del mismo tipo en el
     MISMO período de test (nunca mezclar mercados).
  3. Métricas: edge OOS medio, decay = OOS/IS, sign-test sobre los folds
     (¿el edge train→test es consistentemente positivo?), estabilidad.

Esto es el "OOS validator" — capa separada del calificador (shooter principle):
el calificador juzga el tiro ya hecho; el validador responde si se repetirá.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import binomtest

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))

from medir_senal import SEÑALES, cargar_datos
from evaluador_vela_a_vela import first_passage, BLANCOS, ESCALAS

# ── Catálogo v7 post-auditoría: las señales a validar OOS ──
CATALOGO_V7 = [
    "pcr_put_panic", "credit_stress", "capitulacion", "panico_total",
    "vvix_entry", "bsi_washed_out", "breadth_contraction_exit",
    "skew_paranoia_exit",  # rescatada diamante — validación exigente
]

BLOQUE_TEST_DIAS = 1095     # ~3 años por fold
MIN_TRAIN_DIAS = 1825       # mínimo 5 años de train antes del primer test
N_MIN_TRAIN = 10            # celdas elegibles en train

df, spy = cargar_datos()
prices = spy["close"].astype(float).values
spy_idx = spy.close.index
piv_dates = df["pivot_date"].values
piv_types = df["pivot_type"].values
piv_pos = np.array([spy_idx.searchsorted(pd.Timestamp(d)) for d in piv_dates])
n_piv = len(piv_dates)

def régimen_en(t_pos):
    idx = np.arange(n_piv - 1)
    conf = piv_pos[1:]
    valid = idx[conf <= t_pos]
    if len(valid) == 0:
        return "NA"
    return "ALZA" if piv_types[valid[-1]] == "MIN" else "BAJA"

def fichas_celda(señal_mask, blanco, desde, hasta):
    """Fichas first-passage de la señal en [desde, hasta), todas las escalas."""
    idx_disp = np.where(señal_mask.values)[0]
    out = []
    for i in idx_disp:
        d = pd.Timestamp(piv_dates[i])
        if not (desde <= d < hasta):
            continue
        t = piv_pos[i]
        if t >= len(prices) - 1:
            continue
        reg = régimen_en(t)
        for esc, thr in ESCALAS.items():
            r = first_passage(prices, t, thr, blanco)
            if r and r["resuelto"]:
                out.append({"escala": esc, "régimen": reg, **r})
    return pd.DataFrame(out)

def fichas_baseline(tipo, blanco, desde, hasta, excluir_fechas):
    """Baseline: pivotes del mismo tipo en [desde, hasta), sin los de la señal."""
    out = []
    for i in range(n_piv):
        if piv_types[i] != tipo:
            continue
        d = pd.Timestamp(piv_dates[i])
        if not (desde <= d < hasta) or d in excluir_fechas:
            continue
        t = piv_pos[i]
        if t >= len(prices) - 1:
            continue
        reg = régimen_en(t)
        for esc, thr in ESCALAS.items():
            r = first_passage(prices, t, thr, blanco)
            if r and r["resuelto"]:
                out.append({"escala": esc, "régimen": reg, **r})
    return pd.DataFrame(out)

def edge_por_celda(F, B):
    """Favorable neto y N por celda (escala|régimen)."""
    out = {}
    if F.empty:
        return out
    for celda, sub in F.groupby(["escala", "régimen"]):
        esc, reg = celda
        n = len(sub)
        bsub = B[(B["escala"] == esc) & (B["régimen"] == reg)]
        b_fav = bsub["favorable"].mean() if not bsub.empty else 0.0
        fav_neto = (sub["favorable"] - b_fav).mean()
        out[f"{esc}|{reg}"] = {"n": n, "fav_neto": float(fav_neto),
                               "hit": float(sub["hit"].mean())}
    return out

# ── Folds cronológicos anclados ──
T0 = pd.Timestamp(df["pivot_date"].min())
T1 = pd.Timestamp(df["pivot_date"].max()) + pd.Timedelta(days=1)
folds = []
t = T0 + pd.Timedelta(days=MIN_TRAIN_DIAS)
while t < T1:
    folds.append((t, min(t + pd.Timedelta(days=BLOQUE_TEST_DIAS), T1)))
    t += pd.Timedelta(days=BLOQUE_TEST_DIAS)

print(f"VALIDADOR OOS — catálogo v7 | {len(folds)} folds (train anclado ≥5 años, test ~3 años)")
print(f"{'='*120}")

resultados = {}
for s in CATALOGO_V7:
    blanco = BLANCOS[s]
    tipo = "MAX" if blanco == "MAX" else "MIN"
    mask = SEÑALES[s](df).astype(bool)

    # Edge IN-SAMPLE completo (lo que el evaluador midió, referencia)
    F_all = fichas_celda(mask, blanco, T0, T1)
    B_all = fichas_baseline(tipo, blanco, T0, T1,
                            set(pd.DatetimeIndex(df.loc[mask, "pivot_date"])))
    is_cells = edge_por_celda(F_all, B_all)
    is_best = max(is_cells.items(), key=lambda kv: kv[1]["fav_neto"]) \
        if is_cells else (None, None)

    # Walk-forward fold a fold
    oos_edges, elegidas = [], []
    for (t_from, t_to) in folds:
        F_train = fichas_celda(mask, blanco, T0, t_from)
        B_train = fichas_baseline(tipo, blanco, T0, t_from,
                                  set(pd.DatetimeIndex(df.loc[mask, "pivot_date"])))
        train_cells = {c: v for c, v in edge_por_celda(F_train, B_train).items()
                       if v["n"] >= N_MIN_TRAIN}
        if not train_cells:
            continue
        mejor_celda = max(train_cells, key=lambda c: train_cells[c]["fav_neto"])

        # Test: la celda elegida, medida en el bloque que nunca vio
        F_test = fichas_celda(mask, blanco, t_from, t_to)
        B_test = fichas_baseline(tipo, blanco, t_from, t_to,
                                 set(pd.DatetimeIndex(df.loc[mask, "pivot_date"])))
        test_cells = edge_por_celda(F_test, B_test)
        if mejor_celda in test_cells and test_cells[mejor_celda]["n"] >= 3:
            e = test_cells[mejor_celda]["fav_neto"]
            oos_edges.append(e)
            elegidas.append((str(t_from.date()), mejor_celda,
                             train_cells[mejor_celda]["fav_neto"], e,
                             test_cells[mejor_celda]["n"]))

    res = {"in_sample_mejor_celda": is_best[0],
           "in_sample_fav_neto": round(is_best[1]["fav_neto"] * 100, 2) if is_best[1] else None,
           "in_sample_n": is_best[1]["n"] if is_best[1] else 0,
           "folds_con_test": len(oos_edges),
           "oos_edge_medio_pct": round(float(np.mean(oos_edges)) * 100, 2) if oos_edges else None,
           "oos_edges_pct": [round(e * 100, 2) for e in oos_edges],
           "folds_positivos": int(sum(1 for e in oos_edges if e > 0)) if oos_edges else 0,
           "decay_oos_vs_is": None, "sign_test_p": None}
    if oos_edges and is_best[1] and is_best[1]["fav_neto"] > 0:
        res["decay_oos_vs_is"] = round(float(np.mean(oos_edges)) / is_best[1]["fav_neto"], 2)
    if len(oos_edges) >= 4:
        res["sign_test_p"] = round(float(
            binomtest(sum(1 for e in oos_edges if e > 0), len(oos_edges),
                      0.5, alternative="greater").pvalue), 4)
    resultados[s] = res

# ── Tabla final ──
print(f"{'señal':>26s} | {'IS celda':>12s} {'IS neto':>8s} {'N':>4s} | {'folds':>5s} {'OOS medio':>9s} {'folds+':>6s} {'decay':>6s} {'sign-test p':>11s} | veredicto")
for s in CATALOGO_V7:
    r = resultados[s]
    if r["oos_edge_medio_pct"] is None:
        print(f"{s:>26s} | sin folds con N suficiente en test")
        continue
    pos = r["folds_positivos"]
    tot = r["folds_con_test"]
    if r["oos_edge_medio_pct"] > 0 and pos / tot >= 0.6:
        ver = "🟢 SE REPITE OOS"
    elif r["oos_edge_medio_pct"] > 0:
        ver = "🟡 OOS positivo, inestable"
    elif r["decay_oos_vs_is"] is not None and r["decay_oos_vs_is"] > 0:
        ver = "🟠 OOS negativo (edge no se repite)"
    else:
        ver = "🔴 NO SE REPITE OOS"
    decay = f"{r['decay_oos_vs_is']:>5.2f}" if r["decay_oos_vs_is"] is not None else "  n/a"
    stp = f"{r['sign_test_p']:>10.4f}" if r["sign_test_p"] is not None else "       n/a"
    print(f"{s:>26s} | {str(r['in_sample_mejor_celda']):>12s} {r['in_sample_fav_neto']:>+7.2f}% {r['in_sample_n']:>4d} | "
          f"{tot:>5d} {r['oos_edge_medio_pct']:>+8.2f}% {pos:>3d}/{tot:<2d} {decay} {stp} | {ver}")

import json
out = ROOT / "data" / "research" / "signals" / "validacion_oos_catalogo_v7.json"
out.write_text(json.dumps({"fecha": str(pd.Timestamp.now()),
                           "metodo": "walk-forward anclado: celda elegida en train, medida en test; baseline por período de test",
                           "bloque_test_dias": BLOQUE_TEST_DIAS,
                           "min_train_dias": MIN_TRAIN_DIAS,
                           "n_min_train": N_MIN_TRAIN,
                           "resultados": resultados},
                          indent=2, ensure_ascii=False, default=str))
print(f"\nGuardado: {out}")
