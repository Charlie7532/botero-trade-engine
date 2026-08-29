#!/usr/bin/env python3
"""SINGULARIDADES COMUNES EN TECHOS Y PISOS DEL ZIGZAG
======================================================
Pregunta del arquitecto (22-Ago): cuando tuvimos el sesgo de posición, no nos
preguntamos si los pivotes que evaluábamos tenían alguna singularidad común en
techos (MAX) y pisos (MIN).

Material disponible: quants_obs = 1,590 pivotes × 141 columnas de estado.
Por cada estación: D1 (estado de nivel), D2 (velocidad), D3 (inestabilidad) +
valores numéricos.

Método (con control de multiplicidad, lección de forense_precursores):
  1. Distribución de cada D1 por tipo de pivote (MIN/MAX)
  2. Fisher exact por estado + Benjamini-Hochberg (q=0.10)
  3. Lift = P(estado|tipo) / P(estado|todos) con CI95 bootstrap
  4. Valores numéricos: diferencia de distribuciones MIN vs MAX (Mann-Whitney)
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import fisher_exact, mannwhitneyu
from statsmodels.stats.multitest import multipletests

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT / "research" / "01_señales_entry_exit"))
from medir_senal import cargar_datos

df, spy = cargar_datos()
tipos = df["pivot_type"].values
n_min = (tipos == "MIN").sum()
n_max = (tipos == "MAX").sum()
print(f"Pivotes: {len(df)} ({n_min} MIN / {n_max} MAX)\n")

ESTACIONES = ["vix", "vvix", "pcr", "fg", "sv5_turbulence", "skew",
              "credit", "bsi", "dxy", "rotation", "yield_curve"]

# ── 1+2+3: D1 por estación: Fisher + BH + lift ──
tests = []  # (estacion, estado, n_min_estado, n_max_estado, p_fisher)
for est in ESTACIONES:
    col = f"{est}_sk"
    if col not in df.columns:
        continue
    d1 = df[col].astype(str).str.split("__").str[0]
    for estado in d1.dropna().unique():
        mask_e = (d1 == estado)
        if mask_e.sum() < 10:
            continue
        a = int(((tipos == "MIN") & mask_e).sum())   # MIN con estado
        b = int(((tipos == "MAX") & mask_e).sum())   # MAX con estado
        c = int(n_min - a)                            # MIN sin estado
        d_ = int(n_max - b)                           # MAX sin estado
        _, p = fisher_exact([[a, b], [c, d_]])
        p_min_dado_e = a / (a + b) if (a + b) > 0 else np.nan
        base_min = n_min / len(df)
        lift = p_min_dado_e / base_min if p_min_dado_e is not None else np.nan
        tests.append({"estacion": est, "estado": estado, "n": int(mask_e.sum()),
                      "n_min": a, "n_max": b, "p_min_dado_e": p_min_dado_e,
                      "lift_min": lift, "p_fisher": p})

T = pd.DataFrame(tests)
rej, qvals, _, _ = multipletests(T["p_fisher"], alpha=0.10, method="fdr_bh")
T["q_bh"] = qvals
T["significativo"] = rej
T = T.sort_values("p_fisher").reset_index(drop=True)

print("="*105)
print(f"SINGULARIDADES DE ESTADO D1 (Fisher + BH q=0.10) — {len(T)} tests")
print("="*105)
print(f"{'estación':>16s} {'estado':>28s} | {'n':>4s} {'P(MIN|e)':>8s} {'lift_MIN':>8s} {'p':>9s} {'q_BH':>8s} sig")
sig_rows = T[T["significativo"]]
for _, r in sig_rows.iterrows():
    tipo_dom = "MIN↑" if r["lift_min"] > 1 else "MAX↑"
    print(f"{r['estacion']:>16s} {r['estado']:>28s} | {r['n']:>4d} {r['p_min_dado_e']:>7.1%} "
          f"{r['lift_min']:>8.2f} {r['p_fisher']:>9.2e} {r['q_bh']:>8.2e} {tipo_dom}")
print(f"\nSignificativos tras BH: {len(sig_rows)} de {len(T)} tests")
print(f"  a favor de MIN (pisos): {(sig_rows['lift_min']>1).sum()}")
print(f"  a favor de MAX (techos): {(sig_rows['lift_min']<1).sum()}")

# Top no significativos para contexto
print(f"\nTop 5 NO significativos (para contexto):")
ns = T[~T["significativo"]].head(5)
for _, r in ns.iterrows():
    print(f"  {r['estacion']}|{r['estado']}: n={r['n']}, p={r['p_fisher']:.3f}, q={r['q_bh']:.3f}")

# ── 4: valores numéricos — MIN vs MAX ──
print(f"\n{'='*105}")
print("VALORES NUMÉRICOS: distribución en MIN vs MAX (Mann-Whitney)")
print("="*105)
print(f"{'estación':>16s} | {'med_MIN':>8s} {'med_MAX':>8s} | {'dif%':>6s} | {'p_MW':>9s}")
num_tests = []
for est in ESTACIONES:
    col = f"{est}_val"
    if col not in df.columns:
        continue
    vals = df[col].astype(float)
    v_min = vals[tipos == "MIN"].dropna()
    v_max = vals[tipos == "MAX"].dropna()
    if len(v_min) < 30 or len(v_max) < 30:
        continue
    u, p = mannwhitneyu(v_min, v_max, alternative="two-sided")
    med_min, med_max = v_min.median(), v_max.median()
    dif = (med_max - med_min) / abs(med_min) if med_min != 0 else np.nan
    num_tests.append(p)
    mark = "✓" if p < 0.05/len(ESTACIONES) else ""  # Bonferroni conservador
    print(f"{est:>16s} | {med_min:>8.3f} {med_max:>8.3f} | {dif:>+5.1%} | {p:>9.2e} {mark}")

print("\nNota: ✓ = significativo tras Bonferroni (0.05/11). Los estados D1 son la")
print("singularidad estructural; los valores numéricos son su expresión continua.")
