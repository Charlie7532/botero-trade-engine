#!/usr/bin/env python3
"""TEST DE STRUCTURAL BREAK — las 9 señales significativas antes/después del quiebre GFC.
Break = 2009-03-09 (piso de SPY en la GFC, fin de la era pre-QE).
Cada período tiene su PROPIO baseline (pivotes del tipo dentro del período) para
no mezclar mercados distintos. Pregunta: ¿el edge sobrevive después del quiebre?"""
import sys
from pathlib import Path
ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))
import numpy as np, pandas as pd
from scipy.stats import fisher_exact
from medir_senal import SEÑALES, cargar_datos
from evaluador_vela_a_vela import first_passage, BLANCOS

df, spy = cargar_datos()
prices = spy["close"].astype(float).values
spy_idx = spy.close.index
piv_dates = df["pivot_date"].values
piv_types = df["pivot_type"].values
piv_pos = np.array([spy_idx.searchsorted(pd.Timestamp(d)) for d in piv_dates])
n_piv = len(piv_dates)
BREAK = pd.Timestamp("2009-03-09")

def régimen_en(t_pos):
    idx = np.arange(n_piv - 1)
    conf = piv_pos[1:]
    valid = idx[conf <= t_pos]
    if len(valid) == 0:
        return "NA"
    last = valid[-1]
    return "ALZA" if piv_types[last] == "MIN" else "BAJA"

SIGNIFICATIVAS = {
    "pcr_put_panic": ("zz75", 0.075, "BAJA"),
    "credit_stress": ("zz75", 0.075, "ALZA"),
    "capitulacion": ("zz25", 0.025, "BAJA"),
    "panico_total": ("zz75", 0.075, "BAJA"),
    "vvix_entry": ("zz75", 0.075, "ALZA"),
    "bsi_washed_out": ("zz25", 0.025, "BAJA"),
    "bsi_recovery": ("zz75", 0.075, "BAJA"),
    "credit_ease_exit": ("zz75", 0.075, "ALZA"),
    "breadth_contraction_exit": ("zz75", 0.075, "ALZA"),
}

def resultados(s_name, esc, thr, reg_obj, desde, hasta):
    """Favorables + hits de la señal en [desde, hasta), y su baseline del período."""
    blanco = BLANCOS[s_name]
    sig = SEÑALES[s_name](df).astype(bool)
    disp = df[sig]
    tipo = "MAX" if blanco == "MAX" else "MIN"
    señal_fechas = set(pd.DatetimeIndex(disp["pivot_date"]))
    sig_out, base_out = [], []
    for _, row in disp.iterrows():
        d = pd.Timestamp(row["pivot_date"])
        if not (desde <= d < hasta):
            continue
        t = spy_idx.searchsorted(d)
        if t >= len(prices) - 1 or régimen_en(t) != reg_obj:
            continue
        r = first_passage(prices, t, thr, blanco)
        if r and r["resuelto"]:
            sig_out.append(r)
    # baseline: pivotes del tipo en el período, excluidos los de la señal
    for i in range(n_piv):
        if piv_types[i] != tipo:
            continue
        d = pd.Timestamp(piv_dates[i])
        if not (desde <= d < hasta) or d in señal_fechas:
            continue
        t = piv_pos[i]
        if t >= len(prices) - 1 or régimen_en(t) != reg_obj:
            continue
        r = first_passage(prices, t, thr, blanco)
        if r and r["resuelto"]:
            base_out.append(r)
    return sig_out, base_out

T0 = pd.Timestamp(df["pivot_date"].min())
T1 = pd.Timestamp(df["pivot_date"].max()) + pd.Timedelta(days=1)

print(f"STRUCTURAL BREAK en {BREAK.date()} — mejor celda de cada señal, antes vs después")
print(f"{'='*120}")
print(f"{'señal':>26s} | {'PRE n':>5s} {'hit':>4s} {'favN':>7s} | {'POST n':>6s} {'hit':>4s} {'favN':>7s} | {'Δfav':>7s} | fisher p | veredicto")
for s, (esc, thr, reg_obj) in SIGNIFICATIVAS.items():
    pre_sig, pre_base = resultados(s, esc, thr, reg_obj, T0, BREAK)
    post_sig, post_base = resultados(s, esc, thr, reg_obj, BREAK, T1)
    def stats(sig, base):
        if not sig:
            return None
        favs = np.array([r["favorable"] for r in sig])
        hits = np.array([r["hit"] for r in sig])
        b_fav = np.mean([r["favorable"] for r in base]) if base else 0.0
        return {"n": len(sig), "hit": hits.mean(), "fav_neto": (favs - b_fav).mean(),
                "hits": int(hits.sum())}
    pre, post = stats(pre_sig, pre_base), stats(post_sig, post_base)
    if pre is None or post is None:
        print(f"{s:>26s} | sin datos suficientes en un período")
        continue
    # Fisher: ¿cambió el hit rate entre períodos?
    _, fp = fisher_exact([[pre["hits"], pre["n"] - pre["hits"]],
                          [post["hits"], post["n"] - post["hits"]]])
    dfav = post["fav_neto"] - pre["fav_neto"]
    if post["fav_neto"] > 0 and dfav > -0.005:
        ver = "🟢 ROBUSTA al quiebre"
    elif post["fav_neto"] > 0:
        ver = "🟡 sobrevive degradada"
    elif post["fav_neto"] > -0.005 and pre["fav_neto"] > 0.005:
        ver = "🔴 RELIQUIA (edge pre-quiebre)"
    else:
        ver = "🔴 sin edge post-quiebre"
    print(f"{s:>26s} | {pre['n']:>5d} {pre['hit']:>3.0%} {pre['fav_neto']:>+6.2%} | "
          f"{post['n']:>6d} {post['hit']:>3.0%} {post['fav_neto']:>+6.2%} | {dfav:>+6.2%} | "
          f"{fp:>7.4f} | {ver}")
