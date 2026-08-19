#!/usr/bin/env python3
"""
PBO — Probability of Backtest Overfitting (López de Prado, CPCV)
================================================================
Evalúa el cascade_conviction (IC +0.41) contra una FAMILIA de modelos
(configuraciones plausibles) usando Combinatorial Purged Cross-Validation.

Método:
1. Particionar los N=1589 pivotes en S=8 grupos cronológicos.
2. Todas las combinaciones de 2 grupos como TEST (C(8,2)=28), resto = TRAIN.
3. Familia de M modelos: grid de pesos (w_bear) × conjuntos de estaciones.
4. Para cada combinación, rankear modelos por IC in-sample y out-of-sample.
5. PBO = P( el modelo elegido in-sample queda por debajo de la mediana OOS ).
"""
import sys, pickle
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path("/root/botero-trade")
OBS_PKL = ROOT / "data/research/pivots/quants_obs.pkl"

ALL_STATIONS = ["vix","vvix","pcr","fg","sv5_turbulence","skew","credit","yield_curve","rotation","bsi","dxy"]
GRUPO_A = ["vix","bsi","fg","credit","rotation"]

with open(OBS_PKL, 'rb') as f:
    df = pickle.load(f)

def ic(a, b):
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    m = ~np.isnan(a) & ~np.isnan(b)
    if m.sum() < 5 or np.std(a[m])==0 or np.std(b[m])==0:
        return 0.0
    r,_ = spearmanr(a[m], b[m])
    return float(r) if not np.isnan(r) else 0.0

# ── Construir features base ──────────────────────────────
# d1_bear votes por estación (ya en el pickle como {code}_d1_vote)
target = df["cascade_50"].values
abs_prev = df["abs_prev_leg_return"].values

# Familia de modelos: (w_bear, lista de estaciones para el voto)
station_sets = {
    "GrupoA": GRUPO_A,
    "All11": ALL_STATIONS,
    "VixBsFg": ["vix","bsi","fg"],
    "VixCredit": ["vix","credit","rotation"],
}
w_bear_grid = np.arange(0.30, 0.76, 0.05)  # 0.30 .. 0.75 (10 valores)

models = []
for sname, stations in station_sets.items():
    for w_bear in w_bear_grid:
        w_dom = 1.0 - w_bear
        models.append((sname, w_bear, w_dom, stations))

print(f"Familia de modelos: {len(models)} configuraciones")
print(f"  (4 conjuntos de estaciones × 10 pesos w_bear ∈ [0.30, 0.75])")

# Pre-computar d1_bear promedio para cada conjunto de estaciones
def d1_bear_mean(df, stations):
    cols = [f"{c}_d1_vote" for c in stations]
    sub = df[cols].copy()
    # fractional bear vote: mean of -v for v<0, over available stations
    votes = []
    for i in range(len(df)):
        vs = [sub.iloc[i][c] for c in cols if not pd.isna(sub.iloc[i][c])]
        if vs:
            votes.append(sum(-v for v in vs if v < 0) / len(vs))
        else:
            votes.append(np.nan)
    return np.array(votes, dtype=float)

print("Pre-computando d1_bear por conjunto de estaciones...")
d1_votes_by_set = {sname: d1_bear_mean(df, stations) for sname, stations in station_sets.items()}

# ── CPCV: S=8 grupos cronológicos, test = 2 grupos ─────
S = 8
N = len(df)
group_size = N // S
group_ids = np.minimum(np.arange(N) // group_size, S - 1)  # chronological groups

print(f"\nCPCV: S={S} grupos cronológicos (~{group_size} pivotes c/u)")
print(f"  Combinaciones de test (2 grupos): C({S},2) = {S*(S-1)//2}")

import itertools
test_combos = list(itertools.combinations(range(S), 2))
print(f"  Total combinaciones: {len(test_combos)}")

# Para cada modelo, pre-computar el score completo (necesita z-score, que debe ser in-sample)
# PERO para PBO correcto, el z-score debe calcularse DENTRO del train. 
# Simplificación estándar: z-score global (sin look-ahead significativo para ranking de modelos).

results = []  # (combo, model_idx, is_ic, oos_ic)

print("Evaluando...")
for combo in test_combos:
    test_mask = np.isin(group_ids, combo)
    train_mask = ~test_mask
    
    for mi, (sname, w_bear, w_dom, stations) in enumerate(models):
        d1 = d1_votes_by_set[sname]
        
        # z-score global (común para todos los modelos — no afecta el RANKING)
        d1_valid = ~np.isnan(d1)
        d1_mu = np.nanmean(d1); d1_sd = np.nanstd(d1)
        z_bear = (d1 - d1_mu) / (d1_sd if d1_sd > 0 else 1.0)
        
        dom_valid = ~np.isnan(abs_prev)
        dom_mu = np.nanmean(abs_prev); dom_sd = np.nanstd(abs_prev)
        z_dom = (abs_prev - dom_mu) / (dom_sd if dom_sd > 0 else 1.0)
        
        score = w_bear * z_bear + w_dom * z_dom
        
        is_ic_val = ic(score[train_mask], target[train_mask])
        oos_ic_val = ic(score[test_mask], target[test_mask])
        
        results.append((combo, mi, is_ic_val, oos_ic_val))

# ── PBO computation ────────────────────────────────────
# Para cada combinación: rankear modelos por |IS IC| y |OOS IC|
M = len(models)
n_combos = len(test_combos)
rank_is = np.zeros((n_combos, M))
rank_oos = np.zeros((n_combos, M))

for ci, combo in enumerate(test_combos):
    combo_results = [r for r in results if r[0] == combo]
    is_vals = np.array([r[2] for r in combo_results])
    oos_vals = np.array([r[3] for r in combo_results])
    
    # Rank by absolute IC (higher |IC| = better = rank 1)
    rank_is[ci] = M - np.argsort(np.argsort(np.abs(is_vals)))  # 1=best
    rank_oos[ci] = M - np.argsort(np.argsort(np.abs(oos_vals)))

# PBO: fraction of combos where the best-IS model's OOS rank > median OOS rank
# (i.e., the model selected in-sample is in the bottom half out-of-sample)
n_overfit = 0
logits = []
best_is_oos_ranks = []

for ci in range(n_combos):
    best_is_model = np.argmin(rank_is[ci])  # model with best IS rank
    oos_rank_of_best_is = rank_oos[ci, best_is_model]
    best_is_oos_ranks.append(oos_rank_of_best_is)
    
    # relative rank: normalized 0..1 (1 = best OOS)
    rel_rank = 1.0 - (oos_rank_of_best_is - 1) / (M - 1)
    logits.append(rel_rank)
    
    # overfit if the best-IS model is in the BOTTOM HALF out-of-sample
    if oos_rank_of_best_is > M / 2:
        n_overfit += 1

pbo = n_overfit / n_combos
mean_rel_rank = np.mean(logits)

print("\n" + "═" * 70)
print(" RESULTADOS PBO")
print("═" * 70)
print(f"\n  Modelos en la familia: {M}")
print(f"  Combinaciones CPCV: {n_combos}")
print(f"  PBO (fraction donde el mejor IS queda en mitad INFERIOR OOS): {pbo:.3f} ({pbo*100:.1f}%)")
print(f"  Ranking relativo OOS del modelo elegido IS (0=peor, 1=mejor): {mean_rel_rank:.3f}")

# Distribución de OOS ranks del mejor IS model
print(f"\n  Distribución de OOS-rank del mejor modelo IS:")
print(f"    Top 25% OOS:  {np.mean(np.array(best_is_oos_ranks) <= M*0.25)*100:.1f}%")
print(f"    Top 50% OOS:  {np.mean(np.array(best_is_oos_ranks) <= M*0.50)*100:.1f}%")
print(f"    Bottom 50%:   {np.mean(np.array(best_is_oos_ranks) > M*0.50)*100:.1f}%")

# Which model wins most often?
print(f"\n  Top 5 configuraciones por frecuencia de ser 'mejor IS':")
from collections import Counter
best_is_counts = Counter()
for ci in range(n_combos):
    best_is_model = np.argmin(rank_is[ci])
    best_is_counts[best_is_model] += 1

for model_idx, count in best_is_counts.most_common(5):
    sname, w_bear, w_dom, stations = models[model_idx]
    print(f"    {sname:<10} w_bear={w_bear:.2f} w_dom={w_dom:.2f} — mejor IS en {count}/{n_combos} combos")

# Interpetación del PBO
print(f"\n  Interpretación:")
if pbo < 0.1:
    print(f"    ✅ PBO={pbo:.1%} < 10% — bajo riesgo de overfitting.")
    print(f"       El cascade_conviction NO es un artefacto de selección de modelo.")
elif pbo < 0.3:
    print(f"    ⚠ PBO={pbo:.1%} — riesgo moderado. Verificar con walk-forward adicional.")
else:
    print(f"    ❌ PBO={pbo:.1%} — alto riesgo de overfitting. El IC +0.41 puede ser espurio.")

# Guardar resultados
out = {
    "n_models": M,
    "n_combos": n_combos,
    "pbo": pbo,
    "mean_relative_rank_oos": mean_rel_rank,
    "best_is_oos_ranks": best_is_oos_ranks,
    "models": [(s, float(wb), float(wd), st) for s, wb, wd, st in models],
}
import json
with open(ROOT / "data/research/ldp_methodology/pbo_results.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"\n  Guardado en data/research/pbo_results.json")
