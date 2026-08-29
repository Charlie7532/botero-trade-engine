#!/usr/bin/env python3
"""Estabilidad por década de las 9 señales significativas (p<0.05) del ranking v6.
Reproduce el check que la auditoría Gemini aplicó a bsi_recovery (spike 2010s)."""
import sys
from pathlib import Path
ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))
import numpy as np, pandas as pd
from medir_senal import SEÑALES, cargar_datos
from evaluador_vela_a_vela import first_passage, BLANCOS

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
    last = valid[-1]
    return "ALZA" if piv_types[last] == "MIN" else "BAJA"

# Las 9 señales con p<0.05 y su mejor celda (ranking v6)
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
DECADAS = [(1993, 2000), (2000, 2010), (2010, 2020), (2020, 2027)]

print(f"{'señal':>26s} | " + " | ".join(f"{a}-{b}" for a, b in DECADAS) + " | estable?")
for s, (esc, thr, reg_obj) in SIGNIFICATIVAS.items():
    blanco = BLANCOS[s]
    sig = SEÑALES[s](df).astype(bool)
    disp = df[sig]
    celdas = {d: [] for d in DECADAS}
    for _, row in disp.iterrows():
        d = pd.Timestamp(row["pivot_date"])
        t = spy_idx.searchsorted(d)
        if t >= len(prices) - 1:
            continue
        if régimen_en(t) != reg_obj:
            continue
        r = first_passage(prices, t, thr, blanco)
        if not r or not r["resuelto"]:
            continue
        yr = d.year
        for lo, hi in DECADAS:
            if lo <= yr < hi:
                celdas[(lo, hi)].append(r["hit"])
                break
    tasas = []
    partes = []
    for dd in DECADAS:
        hs = celdas[dd]
        if len(hs) >= 3:
            t_ = np.mean(hs)
            tasas.append(t_)
            partes.append(f"{t_:>4.0%} n={len(hs):<3d}")
        else:
            partes.append(f"{'N/A':>4s} n={len(hs):<3d}")
    if len(tasas) >= 2:
        spread = max(tasas) - min(tasas)
        estable = "🟢" if spread <= 0.20 else ("🟡" if spread <= 0.35 else "🔴")
        extra = f" spread={spread:.0%}"
    else:
        estable, extra = "⚪", " pocas décadas"
    print(f"{s:>26s} | " + " | ".join(partes) + f" | {estable}{extra}")
