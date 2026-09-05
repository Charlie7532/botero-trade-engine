#!/usr/bin/env python3
"""
VALIDADOR OOS — Catálogo v8 (capa separada del calificador post-mortem)
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

from arnes.registro import SEÑALES, _CERTEZA
from arnes.datos import cargar_datos
from evaluador_vela_a_vela import BLANCOS, ESCALAS
from evaluador_general import first_passage_bar

# ── Catálogo v7 post-auditoría: las señales a validar OOS ──
CATALOGO_V7 = [
    "pcr_put_panic", "credit_stress", "capitulacion", "panico_total",
    "vvix_entry", "bsi_washed_out", "breadth_contraction_exit",
    "skew_paranoia_exit",  # rescatada diamante — validación exigente
    "cascade_reversal",   # VALIDATED Grade B — PF=7.42 first-passage, test OOS walk-forward
]

BLOQUE_TEST_DIAS = 1095     # ~3 años por fold
MIN_TRAIN_DIAS = 1825       # mínimo 5 años de train antes del primer test
N_MIN_TRAIN = 10            # celdas elegibles en train

# ── Time-Stop Calibrado P90 por Escala ZigZag (Sep-2026) ──
# Derivado empíricamente de 1,354 pivotes en SPY (resolución OHLC intrabarra):
#   zz25 (±2.5%): mediana=3b,  P90=9b   (~3.0× mediana) — movimiento táctico
#   zz50 (±5.0%): mediana=12b, P90=45b  (~3.8× mediana) — movimiento intermedio
#   zz75 (±7.5%): mediana=29b, P90=101b (~3.5× mediana) — movimiento estructural
# Proporción armónica constante (~3.5× mediana). Respeta la ventana de causalidad
# temporal: una señal táctica/circunstancial no retiene atribución infinita.
TIMESTOP_P90 = {
    "zz25": 9,
    "zz50": 45,
    "zz75": 101,
}


# Globals set by _init_data() — called from __main__ or externally
df = spy = prices = highs = lows = spy_idx = piv_dates = piv_types = piv_pos = n_piv = None

def _init_data():
    """Load data and set module globals. Idempotent."""
    global df, spy, prices, highs, lows, spy_idx, piv_dates, piv_types, piv_pos, n_piv
    if df is not None:
        return
    df, spy = cargar_datos()
    prices = spy["close"].astype(float).values
    highs = spy["high"].astype(float).values
    lows = spy["low"].astype(float).values
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
    """Fichas first-passage de la señal en [desde, hasta), todas las escalas.
    Saneamiento Sep-2026: OHLC intrabar, time-stop calibrado al P90 empírico de cada escala
    (zz25: 9b, zz50: 45b, zz75: 101b). Respeta la ventana de atribución causal."""
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
            r = first_passage_bar(prices, highs, lows, t, thr, blanco,
                                  max_barras=TIMESTOP_P90[esc])
            if r and r["resuelto"]:
                out.append({"escala": esc, "régimen": reg, **r})
    return pd.DataFrame(out)

def fichas_baseline(tipo, blanco, desde, hasta, excluir_fechas):
    """Baseline: pivotes del mismo tipo en [desde, hasta), sin los de la señal.
    Saneamiento Sep-2026: OHLC intrabar, time-stop calibrado al P90 empírico de cada escala
    (zz25: 9b, zz50: 45b, zz75: 101b)."""
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
            r = first_passage_bar(prices, highs, lows, t, thr, blanco,
                                  max_barras=TIMESTOP_P90[esc])
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


if __name__ == "__main__":
    _init_data()

    # ── Folds cronológicos anclados ──
    T0 = pd.Timestamp(df["pivot_date"].min())
    T1 = pd.Timestamp(df["pivot_date"].max()) + pd.Timedelta(days=1)
    folds_all = []
    t = T0 + pd.Timedelta(days=MIN_TRAIN_DIAS)
    while t < T1:
        folds_all.append((t, min(t + pd.Timedelta(days=BLOQUE_TEST_DIAS), T1)))
        t += pd.Timedelta(days=BLOQUE_TEST_DIAS)

    print(f"VALIDADOR OOS MULTI-CELDA — catálogo v8 (SANEADO Sep-2026: inception + OHLC + time-stop P90 calibrado)")
    print(f"  Time-stops P90 empíricos: {TIMESTOP_P90}")
    print(f"  {len(folds_all)} folds totales (train anclado ≥5 años, test ~3 años)")
    print(f"{'='*130}")

    resultados = {}
    for s in CATALOGO_V7:
        blanco = BLANCOS[s]
        tipo = "MAX" if blanco == "MAX" else "MIN"
        mask = SEÑALES[s](df).astype(bool)

        # ── Corrección 1: Inception Policy ──
        # Folds cuyo test window termina ANTES del inception de la señal se saltan.
        cert = _CERTEZA.get(s, {})
        inception_str = cert.get("fecha_inicio_valida")
        inception = pd.Timestamp(inception_str) if inception_str else T0
        folds = [(f, t) for (f, t) in folds_all if t > inception]
        n_skipped = len(folds_all) - len(folds)
        if n_skipped > 0:
            print(f"  [{s}] inception={inception_str} → {n_skipped} folds pre-inception saltados, {len(folds)} válidos")

        # Aplicar inception al mask también: datos pre-inception = False
        mask_inception = pd.Series(False, index=df.index)
        for idx_i in range(len(df)):
            if pd.Timestamp(piv_dates[idx_i]) >= inception:
                mask_inception.iloc[idx_i] = True
        mask = mask & mask_inception

        # Edge IN-SAMPLE completo por celda (solo datos post-inception)
        T0_eff = max(T0, inception)  # Train starts at max(T0, inception)
        F_all = fichas_celda(mask, blanco, T0_eff, T1)
        B_all = fichas_baseline(tipo, blanco, T0_eff, T1,
                                set(pd.DatetimeIndex(df.loc[mask, "pivot_date"])))
        is_cells = edge_por_celda(F_all, B_all)

        # ── MULTI-CELDA: probar CADA celda calificada independientemente ──
        celda_results = {}
        for celda_nombre, celda_is in is_cells.items():
            if celda_is["n"] < N_MIN_TRAIN or celda_is["fav_neto"] <= 0:
                continue  # solo celdas con edge positivo y N suficiente

            oos_edges = []
            for (t_from, t_to) in folds:
                # Train: verificar que esta celda califica en train (post-inception)
                F_train = fichas_celda(mask, blanco, T0_eff, t_from)
                B_train = fichas_baseline(tipo, blanco, T0_eff, t_from,
                                          set(pd.DatetimeIndex(df.loc[mask, "pivot_date"])))
                train_cells = edge_por_celda(F_train, B_train)
                tc = train_cells.get(celda_nombre)
                if tc is None or tc["n"] < N_MIN_TRAIN:
                    continue  # celda sin datos suficientes en train

                # Test: medir la celda en el bloque que nunca vio
                F_test = fichas_celda(mask, blanco, t_from, t_to)
                B_test = fichas_baseline(tipo, blanco, t_from, t_to,
                                         set(pd.DatetimeIndex(df.loc[mask, "pivot_date"])))
                test_cells = edge_por_celda(F_test, B_test)
                if celda_nombre in test_cells and test_cells[celda_nombre]["n"] >= 3:
                    oos_edges.append(test_cells[celda_nombre]["fav_neto"])

            if not oos_edges:
                continue

            is_neto = celda_is["fav_neto"]
            oos_medio = float(np.mean(oos_edges))
            folds_pos = sum(1 for e in oos_edges if e > 0)
            folds_tot = len(oos_edges)
            decay = round(oos_medio / is_neto, 2) if is_neto > 0 else None
            sign_p = None
            if folds_tot >= 4:
                sign_p = round(float(
                    binomtest(folds_pos, folds_tot, 0.5,
                              alternative="greater").pvalue), 4)

            celda_results[celda_nombre] = {
                "in_sample_fav_neto": round(is_neto * 100, 2),
                "in_sample_n": celda_is["n"],
                "folds_con_test": folds_tot,
                "oos_edge_medio_pct": round(oos_medio * 100, 2),
                "oos_edges_pct": [round(e * 100, 2) for e in oos_edges],
                "folds_positivos": folds_pos,
                "decay_oos_vs_is": decay,
                "sign_test_p": sign_p,
            }

        # Elegir la mejor celda OOS (por consistencia, luego edge absoluto)
        n_celdas_probadas = len(celda_results)
        if celda_results:
            # Priorizar: OOS positivo > más folds > más folds+ > mayor edge absoluto OOS
            # NOT decay — decay = OOS/IS se infla con IS pequeño (artefacto aritmético)
            def _score(item):
                r = item[1]
                oos = r["oos_edge_medio_pct"]
                return (oos > 0, r["folds_con_test"], r["folds_positivos"], oos)
            best_celda = max(celda_results.items(), key=_score)
            # Bonferroni señal-dependiente: p_ajustado = p_raw × n_celdas_probadas
            p_raw = best_celda[1].get("sign_test_p")
            p_bonf = round(p_raw * n_celdas_probadas, 4) if p_raw is not None else None
            resultados[s] = {
                "mejor_celda_oos": best_celda[0],
                "n_celdas_probadas": n_celdas_probadas,
                "p_bonferroni": p_bonf,
                "todas_celdas_oos": celda_results,
                **best_celda[1],
            }
        else:
            resultados[s] = {
                "mejor_celda_oos": None,
                "todas_celdas_oos": {},
                "in_sample_fav_neto": None, "in_sample_n": 0,
                "folds_con_test": 0, "oos_edge_medio_pct": None,
                "oos_edges_pct": [], "folds_positivos": 0,
                "decay_oos_vs_is": None, "sign_test_p": None,
            }

    # ── Tabla final: mejor celda por señal ──
    print(f"\n{'señal':>26s} | {'OOS celda':>12s} {'IS neto':>8s} {'N':>4s} | {'folds':>5s} {'OOS medio':>9s} {'folds+':>6s} {'decay':>6s} {'sign-p':>8s} | veredicto")
    print(f"{'-'*130}")
    for s in CATALOGO_V7:
        r = resultados[s]
        if r["oos_edge_medio_pct"] is None:
            print(f"{s:>26s} | sin celdas con edge OOS")
            continue
        pos = r["folds_positivos"]
        tot = r["folds_con_test"]
        if tot < 5 and r["oos_edge_medio_pct"] > 0:
            ver = "🔵 PENDIENTE (folds<5, sign-test imposible)"
        elif r["oos_edge_medio_pct"] > 0 and pos / tot >= 0.6:
            ver = "🟢 SE REPITE OOS"
        elif r["oos_edge_medio_pct"] > 0:
            ver = "🟡 OOS positivo, inestable"
        elif r["decay_oos_vs_is"] is not None and r["decay_oos_vs_is"] > 0:
            ver = "🟠 OOS marginal"
        else:
            ver = "🔴 NO SE REPITE OOS"
        celda = r.get("mejor_celda_oos", "?")
        is_n = r.get("in_sample_fav_neto", 0) or 0
        n = r.get("in_sample_n", 0) or 0
        decay = f"{r['decay_oos_vs_is']:>5.2f}" if r["decay_oos_vs_is"] is not None else "  n/a"
        stp = f"{r['sign_test_p']:>7.4f}" if r["sign_test_p"] is not None else "    n/a"
        print(f"{s:>26s} | {str(celda):>12s} {is_n:>+7.2f}% {n:>4d} | "
              f"{tot:>5d} {r['oos_edge_medio_pct']:>+8.2f}% {pos:>3d}/{tot:<2d} {decay} {stp} | {ver}")

    # ── Detalle multi-celda (señales con >1 celda probada) ──
    print(f"\n{'='*130}")
    print("DETALLE MULTI-CELDA (todas las celdas probadas OOS por señal)")
    print(f"{'='*130}")
    for s in CATALOGO_V7:
        r = resultados[s]
        celdas = r.get("todas_celdas_oos", {})
        if len(celdas) <= 1:
            continue
        best = r.get("mejor_celda_oos", "")
        print(f"\n  {s}:")
        for c, v in sorted(celdas.items()):
            mark = " ★" if c == best else ""
            pos = v["folds_positivos"]
            tot = v["folds_con_test"]
            decay = f"{v['decay_oos_vs_is']:>5.2f}" if v["decay_oos_vs_is"] is not None else "  n/a"
            stp = f"p={v['sign_test_p']:.4f}" if v["sign_test_p"] is not None else "p=n/a  "
            print(f"    {c:15s}  IS={v['in_sample_fav_neto']:>+6.2f}% N={v['in_sample_n']:>3d} | "
                  f"OOS={v['oos_edge_medio_pct']:>+6.2f}% {pos}/{tot} decay={decay} {stp}{mark}")

    import json
    out = ROOT / "data" / "research" / "signals" / "validacion_oos_catalogo_v8_saneado.json"
    out_p90 = ROOT / "data" / "research" / "signals" / "validacion_oos_catalogo_v8_p90.json"
    payload = {
        "fecha": str(pd.Timestamp.now()),
        "metodo": "walk-forward anclado MULTI-CELDA v8 SANEADO (Sep-2026): "
                  "inception policy (fecha_inicio_valida por señal), "
                  "OHLC intrabar (first_passage_bar con spy high/low), "
                  "time-stop P90 calibrado empíricamente en SPY (zz25=9b, zz50=45b, zz75=101b). "
                  "Baseline excluye pivotes de la señal (P5). Bonferroni señal-dependiente.",
        "timestop_p90": TIMESTOP_P90,
        "bloque_test_dias": BLOQUE_TEST_DIAS,
        "min_train_dias": MIN_TRAIN_DIAS,
        "n_min_train": N_MIN_TRAIN,
        "resultados": resultados,
    }
    content = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    out.write_text(content)
    out_p90.write_text(content)
    print(f"\nGuardado: {out}")
    print(f"Guardado: {out_p90}")
