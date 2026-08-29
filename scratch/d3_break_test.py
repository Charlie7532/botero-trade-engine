#!/usr/bin/env python3
"""BREAK TEST GFC — candidatas D3 marginales (lección credit_ease_exit)
========================================================================
Las candidatas D3 con mejor perfil (p<0.15) se verifican contra el quiebre
2009-03-09. Ninguna señal marginal puede promoverse sin este test:
credit_ease_exit tenía p=0.0013 agregado y resultó reliquia pre-QE.
"""
import sys
from pathlib import Path
ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))
sys.path.insert(0, str(ROOT / "backend/modules/entry_decision/domain/rules"))

import numpy as np, pandas as pd
from scipy.stats import fisher_exact
from medir_senal import cargar_datos
from evaluador_vela_a_vela import first_passage
from sigma_overflow import validate_overflow

df, spy = cargar_datos()
prices = spy["close"].astype(float).values
spy_idx = spy.close.index
piv_dates = df["pivot_date"].values
piv_types = df["pivot_type"].values
piv_pos = np.array([spy_idx.searchsorted(pd.Timestamp(d)) for d in piv_dates])
n_piv = len(piv_dates)
BREAK = pd.Timestamp("2009-03-09")

# ── Reconstruir máscaras D3 (idénticas a senales_d3_candidatas.py) ──
EST_D3 = {"vix": "vix_vol", "vvix": "vvix_vol", "pcr": "pcr_vol", "fg": "fg_vol",
          "sv5_turbulence": "sv5_turbulence_vol", "skew": "skew_vol",
          "credit": "credit_vol", "bsi": "bsi_vol", "dxy": "dxy_vol",
          "rotation": "rotation_vol", "yield_curve": "yield_curve_vol"}
depths = {}
for est, col in EST_D3.items():
    vals = df[col].astype(float)
    d = pd.Series(np.nan, index=df.index)
    for i, v in vals.items():
        if pd.isna(v):
            continue
        depth, flag = validate_overflow(est, "d3", float(v))
        if depth is not None:
            d.iloc[i] = float(depth)
    depths[est] = d
dep = pd.DataFrame(depths)

mascaras = {
    "d3_bsi": dep["bsi"] > 3.0,
    "d3_yield": dep["yield_curve"] > 3.0,
    "d3_extremo": (dep > 4.0).any(axis=1),
}

# candidatas a testear: (nombre, blanco, escala, umbral, régimen objetivo)
CANDIDATAS = [
    ("d3_bsi_max",   "d3_bsi",     "MAX", 0.05,  "ALZA"),   # p=0.069
    ("d3_bsi_max25", "d3_bsi",     "MAX", 0.025, "ALZA"),   # p=0.108
    ("d3_yield_min", "d3_yield",   "MIN", 0.075, "BAJA"),   # p=0.088
    ("d3_yield_min50","d3_yield",  "MIN", 0.05,  "BAJA"),   # p=0.106
    ("d3_extremo_min","d3_extremo","MIN", 0.075, "BAJA"),   # p=0.147
]

def régimen_en(t_pos):
    idx = np.arange(n_piv - 1)
    conf = piv_pos[1:]
    valid = idx[conf <= t_pos]
    if len(valid) == 0:
        return "NA"
    last = valid[-1]
    return "ALZA" if piv_types[last] == "MIN" else "BAJA"

def resultados(mask, blanco, thr, reg_obj, desde, hasta):
    tipo = "MAX" if blanco == "MAX" else "MIN"
    disp_idx = np.where(mask.values)[0]
    señal_fechas = set(pd.DatetimeIndex(df["pivot_date"].iloc[disp_idx]))
    sig_out, base_out = [], []
    for i in disp_idx:
        d = pd.Timestamp(piv_dates[i])
        if not (desde <= d < hasta):
            continue
        t = piv_pos[i]
        if t >= len(prices) - 1 or régimen_en(t) != reg_obj:
            continue
        r = first_passage(prices, t, thr, blanco)
        if r and r["resuelto"]:
            sig_out.append(r)
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

print(f"BREAK TEST GFC (2009-03-09) — candidatas D3")
print(f"{'='*115}")
print(f"{'candidata':>16s} | {'PRE n':>5s} {'hit':>4s} {'favN':>7s} | {'POST n':>6s} {'hit':>4s} {'favN':>7s} | {'Δfav':>7s} | fisher p | veredicto")
for nombre, mask_key, blanco, thr, reg_obj in CANDIDATAS:
    mask = mascaras[mask_key]
    pre_sig, pre_base = resultados(mask, blanco, thr, reg_obj, T0, BREAK)
    post_sig, post_base = resultados(mask, blanco, thr, reg_obj, BREAK, T1)

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
        print(f"{nombre:>16s} | sin datos suficientes en un período")
        continue
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
        ver = "⚫ negativa en ambos"
    print(f"{nombre:>16s} | {pre['n']:>5d} {pre['hit']:>3.0%} {pre['fav_neto']*100:>+6.2f}% | "
          f"{post['n']:>6d} {post['hit']:>3.0%} {post['fav_neto']*100:>+6.2f}% | "
          f"{dfav*100:>+6.2f}% | {fp:>7.4f} | {ver}")
