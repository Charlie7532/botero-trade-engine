#!/usr/bin/env python3
"""TRÍADAS DE ZIGZAG EN TECHOS Y PISOS — ¿aportan un patrón común?
===================================================================
Pregunta del arquitecto: analizar los vectores de estado (tríadas D1__D2__D3)
en las posiciones de pivote y verificar si tienen un patrón común.

PREGUNTA CORRECTA (tiempo real, sin sesgo de posición):
  P(pivote | tríada) — "si HOY observo esta tríada, ¿es hoy un pivote?"
  NO P(tríada | pivote) — que sería la falacia de la tasa base.

Material: fact stores (n de días por tríada, 8,438 días) × quants_obs
(1,590 pivotes con su state_key por estación).

Tasa base: P(MIN) = 795/8438 = 9.42%, P(MAX) = 795/8438 = 9.42%.
"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import binomtest
from statsmodels.stats.multitest import multipletests

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))
from medir_senal import cargar_datos

FS_DIR = ROOT / "backend/modules/entry_decision/domain/rules"
df, spy = cargar_datos()
tipos = df["pivot_type"].values
N_DIAS = 8438                      # sample_size de los fact stores
N_MIN = int((tipos == "MIN").sum())
N_MAX = int((tipos == "MAX").sum())
P_MIN_BASE = N_MIN / N_DIAS        # 9.42%
P_MAX_BASE = N_MAX / N_DIAS
print(f"Tasa base diaria: P(MIN)={P_MIN_BASE:.2%}  P(MAX)={P_MAX_BASE:.2%}")
print(f"Pivotes: {N_MIN} MIN / {N_MAX} MAX sobre {N_DIAS} días\n")

ESTACIONES = ["vix", "vvix", "pcr", "fg", "sv5_turbulence", "skew",
              "credit", "bsi", "dxy", "rotation", "yield_curve"]

rows = []
for est in ESTACIONES:
    fp = FS_DIR / f"{est}_fact_store.json"
    if not fp.exists():
        continue
    fs = json.loads(fp.read_text())
    states = fs.get("states", {})
    sk_col = f"{est}_sk"
    if sk_col not in df.columns:
        continue
    sk_piv = df[sk_col].astype(str)
    for key, st in states.items():
        n_dias = st.get("n", 0) or 0
        if n_dias < 5:
            continue
        mask = (sk_piv == key)
        n_min_e = int(((tipos == "MIN") & mask).sum())
        n_max_e = int(((tipos == "MAX") & mask).sum())
        p_min = n_min_e / n_dias
        p_max = n_max_e / n_dias
        # binomial: ¿n_min_e sobre n_dias excede la tasa base?
        # k se acota a n_dias (fechas con 2 pivotes MIN+MAX multi-escala pueden
        # hacer #pivotes > #días únicos del estado)
        k_min = min(n_min_e, n_dias)
        k_max = min(n_max_e, n_dias)
        pval_min = binomtest(k_min, n_dias, P_MIN_BASE, alternative="greater").pvalue
        pval_max = binomtest(k_max, n_dias, P_MAX_BASE, alternative="greater").pvalue
        rows.append({"estacion": est, "triada": key, "n_dias": n_dias,
                     "n_min": n_min_e, "n_max": n_max_e,
                     "p_min_dado_triada": p_min, "p_max_dado_triada": p_max,
                     "lift_min": p_min / P_MIN_BASE, "lift_max": p_max / P_MAX_BASE,
                     "pval_min": pval_min, "pval_max": pval_max})

T = pd.DataFrame(rows)
print(f"Tríadas evaluadas: {len(T)} (n_dias >= 5)\n")

# BH sobre los p-values MIN y MAX por separado
rej_min, q_min, _, _ = multipletests(T["pval_min"], alpha=0.10, method="fdr_bh")
rej_max, q_max, _, _ = multipletests(T["pval_max"], alpha=0.10, method="fdr_bh")
T["q_min"], T["q_max"] = q_min, q_max
T["sig_min"], T["sig_max"] = rej_min, rej_max

def tier(n):
    if n <= 2: return "ANECDOTAL"
    if n <= 5: return "LOW"
    if n <= 10: return "MODERATE"
    if n <= 20: return "HIGH"
    return "ROBUST"

# ── PATRÓN DE PISOS: tríadas con exceso significativo de MIN ──
print("="*115)
print("PATRÓN COMÚN DE LOS PISOS — P(MIN | tríada) vs tasa base 9.4% [BH q=0.10]")
print("="*115)
print(f"{'estación':>14s} {'tríada':>60s} | {'n_días':>6s} {'#MIN':>4s} {'P(MIN|t)':>8s} {'lift':>5s} {'q_BH':>8s}")
pm = T[T["sig_min"]].sort_values("q_min")
for _, r in pm.head(20).iterrows():
    print(f"{r['estacion']:>14s} {r['triada']:>60s} | {r['n_dias']:>6d} {r['n_min']:>4d} "
          f"{r['p_min_dado_triada']:>7.1%} {r['lift_min']:>5.2f} {r['q_min']:>8.2e}")
print(f"\nTríadas con exceso significativo de MIN: {len(pm)}")

# ── PATRÓN DE TECHOS ──
print(f"\n{'='*115}")
print("PATRÓN COMÚN DE LOS TECHOS — P(MAX | tríada) vs tasa base 9.4% [BH q=0.10]")
print("="*115)
print(f"{'estación':>14s} {'tríada':>60s} | {'n_días':>6s} {'#MAX':>4s} {'P(MAX|t)':>8s} {'lift':>5s} {'q_BH':>8s}")
px = T[T["sig_max"]].sort_values("q_max")
for _, r in px.head(20).iterrows():
    print(f"{r['estacion']:>14s} {r['triada']:>60s} | {r['n_dias']:>6d} {r['n_max']:>4d} "
          f"{r['p_max_dado_triada']:>7.1%} {r['lift_max']:>5.2f} {r['q_max']:>8.2e}")
print(f"\nTríadas con exceso significativo de MAX: {len(px)}")

# ── DIAMANTES: tríadas raras (n<21) con pivotes ──
print(f"\n{'='*115}")
print("DIAMANTES — tríadas raras (n_días<21) que concentran pivotes")
print("="*115)
dia = T[(T["n_dias"] < 21) & ((T["n_min"] >= 2) | (T["n_max"] >= 2))]
dia = dia.sort_values("n_dias")
for _, r in dia.head(15).iterrows():
    t = tier(r["n_dias"])
    tot_piv = r["n_min"] + r["n_max"]
    print(f"  {r['estacion']:>14s} | {r['triada'][:55]:>55s} | n={r['n_dias']:>3d} ({t:>9s}) | "
          f"pivotes: {tot_piv} (MIN={r['n_min']}, MAX={r['n_max']}) → {tot_piv/r['n_dias']:.0%} de sus días son pivote")

# ── ¿Hay un patrón COMPARTIDO? (D1 común entre tríadas significativas) ──
print(f"\n{'='*115}")
print("¿PATRÓN COMPARTIDO? — D1 dominante entre las tríadas significativas")
print("="*115)
for etiqueta, sub in (("PISOS", pm), ("TECHOS", px)):
    if sub.empty:
        continue
    d1s = sub["triada"].str.split("__").str[0]
    print(f"  {etiqueta}: {dict(d1s.value_counts().head(6))}")
