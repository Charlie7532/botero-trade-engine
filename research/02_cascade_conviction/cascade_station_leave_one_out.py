#!/usr/bin/env python3
"""
CASCADE (Grupo A) Leave-One-Out Analysis
=========================================
Mide la contribución marginal de cada una de las 5 estaciones del Grupo A
(vix, bsi, fg, credit, rotation) al IC del cascade_conviction contra cascade_50.

Fórmula replicada:
  d1_bear_5 = Σ(-vote for vote in masked_votes if vote < 0) / n_active  (fractional)
  z_bear = (d1_bear_5 - d1_mean) / d1_std
  z_dom25 = (abs_prev_leg_return - dom25_mean) / dom25_std
  cascade_conviction = 0.66 * z_bear + 0.34 * z_dom25

Calibración autoritativa: cascade_calibration.json
  d1_mean=0.41, d1_std=0.3206, dom25_mean=0.0532, dom25_std=0.035

DATOS: quants_obs.pkl (1,590 pivotes zz25)
MÉTRICA PRIMARIA: Spearman IC vs cascade_50
CI95 bootstrap 3000 (seed 42) — paired resampling.

Estaciones Grupo A: vix, bsi, fg, credit, rotation.
Máscara por pivot_type:
  MIN:  [vix, bsi, fg, credit, rotation]
  MAX:  [vix, bsi,      credit, rotation]  (sin fg)
"""

import json, pickle, time, sys
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from pathlib import Path

np.random.seed(42)
RNG = np.random.RandomState(42)

# ── Config ──────────────────────────────────────────────────────────────────
PROJECT_DIR = Path("/root/botero-trade")
SCRATCH = PROJECT_DIR / "data/research"
CALIBRATION_PATH = PROJECT_DIR / "backend/modules/entry_decision/domain/rules/cascade_calibration.json"
QUANTS_PATH = SCRATCH / "quants_obs.pkl"

GRUPO_A = ["vix", "bsi", "fg", "credit", "rotation"]
TYPE_MASKS = {
    "MIN": ["vix", "bsi", "fg", "credit", "rotation"],
    "MAX": ["vix", "bsi", "credit", "rotation"],  # fg excluded for MAX
}

# ── Helpers ─────────────────────────────────────────────────────────────────

def compute_d1_bear_5(df, allowed_stations_per_row):
    """
    Fractional bear fraction: sum(-v for v<0) / n_active.
    Returns array of d1_bear_5 and n_active.
    """
    N = len(df)
    d1 = np.full(N, np.nan)
    n_active = np.zeros(N, dtype=int)
    for i in range(N):
        allowed = allowed_stations_per_row[i]
        vs = [df.iloc[i][f"{s}_d1_vote"] for s in allowed
              if pd.notna(df.iloc[i][f"{s}_d1_vote"])]
        n_active[i] = len(vs)
        if len(vs) == 0:
            continue
        m_bear = sum(-float(v) for v in vs if v < 0)
        d1[i] = m_bear / len(vs)
    return d1, n_active


def compute_cascade_conviction(df, allowed_per_row, d1_mean, d1_std,
                                 dom25_mean, dom25_std, w_bear=0.66, w_dom=0.34):
    """
    Replicate cascade_conviction from d1_bear_5 + domino zz25.
    """
    d1_bear, n_active = compute_d1_bear_5(df, allowed_per_row)
    z_bear = (d1_bear - d1_mean) / d1_std
    abs_ret = df["abs_prev_leg_return"].values
    z_dom25 = (abs_ret - dom25_mean) / dom25_std
    cascade = w_bear * z_bear + w_dom * z_dom25
    return cascade, d1_bear, n_active, z_bear, z_dom25


def safe_ic(score, target):
    """Spearman IC, returns NaN if < 10 valid pairs."""
    mask = ~np.isnan(score) & ~np.isnan(target)
    if mask.sum() < 10 or np.std(score[mask]) == 0 or np.std(target[mask]) == 0:
        return np.nan
    ic, _ = spearmanr(score[mask], target[mask])
    return float(ic)


def paired_bootstrap(
    y_full, y_loo_list, target, n_iter=3000, seed=42
):
    """
    Paired bootstrap: within each resample compute IC(full) and IC(loo),
    then delta = IC(full) - IC(loo). Returns mean_delta, ci_lo, ci_hi, p_leq0.
    """
    rng = np.random.RandomState(seed)
    N = len(target)
    D = len(y_loo_list)
    # precompute valid mask once
    deltas = np.full((n_iter, D), np.nan)
    for b in range(n_iter):
        idx = rng.choice(N, size=N, replace=True)
        t_b = target[idx]
        f_b = y_full[idx]
        m_full = ~np.isnan(f_b)
        if m_full.sum() < 10:
            continue
        full_ic = safe_ic(f_b[m_full], t_b[m_full])
        if np.isnan(full_ic):
            continue
        for d in range(D):
            loo_b = y_loo_list[d][idx]
            # use intersection of full + loo valid
            m_loo = ~np.isnan(loo_b)
            m_common = m_full & m_loo
            if m_common.sum() < 10:
                continue
            loo_ic = safe_ic(loo_b[m_common], t_b[m_common])
            if np.isnan(loo_ic):
                continue
            deltas[b, d] = full_ic - loo_ic
    mean_delta = np.nanmean(deltas, axis=0)
    ci_lo = np.nanpercentile(deltas, 2.5, axis=0)
    ci_hi = np.nanpercentile(deltas, 97.5, axis=0)
    p_leq0 = np.nanmean(deltas <= 0, axis=0)
    return mean_delta, ci_lo, ci_hi, p_leq0


# ═══════════════════════════════════════════════════════════════════════════════
# PASO 1: Cargar datos y calibración
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 70)
print("CASCADE STATION LEAVE-ONE-OUT — GRUPO A (vix, bsi, fg, credit, rotation)")
print("=" * 70)

t0 = time.time()

# Calibración
with open(CALIBRATION_PATH, "r", encoding="utf-8") as f:
    calib = json.load(f)
d1_mean = calib["d1_bear_5"]["mean"]
d1_std  = calib["d1_bear_5"]["std"]
dom25_mean = calib["domino_zz25"]["mean"]
dom25_std  = calib["domino_zz25"]["std"]
baseline = calib.get("baseline_ic_in_sample", calib.get("baseline_ic", {}))
print(f"Calibración: d1_mean={d1_mean}, d1_std={d1_std}, dom25_mean={dom25_mean}, dom25_std={dom25_std}")
print(f"Baseline IC: cascade_50={baseline.get('cascade_50')}")

# Datos
df = pd.read_pickle(QUANTS_PATH)
N = len(df)
print(f"quants_obs.pkl: {N} pivotes, cascade_50=1: {df['cascade_50'].sum()}")

target = df["cascade_50"].values.astype(float)

# Estadísticas de cobertura
print("\nCobertura de votos D1 por estación:")
for s in GRUPO_A:
    col = f"{s}_d1_vote"
    n_valid = df[col].notna().sum()
    vals = df[col].dropna().unique().tolist()
    print(f"  {s:10s}: {n_valid}/{N} ({100*n_valid/N:.1f}%)  valores={sorted(vals)}")

print()

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 2: Compute cascade_conviction FULL (all 5 stations with type mask)
# ═══════════════════════════════════════════════════════════════════════════════

full_allowed = df["pivot_type"].apply(lambda pt: TYPE_MASKS.get(pt, GRUPO_A))
full_cascade, full_d1, full_nact, full_z_bear, full_z_dom = compute_cascade_conviction(
    df, full_allowed, d1_mean, d1_std, dom25_mean, dom25_std
)

full_ic = safe_ic(full_cascade, target)
n_full = (~np.isnan(full_cascade) & ~np.isnan(target)).sum()
print(f"[FULL] Cascade Conviction (5 estaciones + type_mask)")
print(f"  IC vs cascade_50:  {full_ic:+.6f}  (n={n_full})")
print(f"  d1_bear_5 mean/std: {np.nanmean(full_d1):.4f} / {np.nanstd(full_d1):.4f}")
print(f"  n_active mean: {np.nanmean(full_nact):.2f}")

# Compare with stored cascade_conviction
stored_conv = df["cascade_conviction"].values
ic_stored = safe_ic(stored_conv, target)
print(f"  IC stored cascade_conviction vs cascade_50: {ic_stored:+.6f}")
print(f"  Spearman(full vs stored): {safe_ic(full_cascade, stored_conv):+.6f}")

# Baseline check
try:
    b50 = baseline.get("cascade_50")
    if b50 is not None:
        deg = np.abs(b50 - full_ic)
        print(f"  vs baseline in-sample ({b50}): Δ={deg:+.6f}")
except:
    pass

print()

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 3: Leave-one-out por estación
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 60)
print("LEAVE-ONE-OUT — una estación fuera del Grupo A cada vez")
print("=" * 60)

loo_cascades = {}   # station → cascade_conviction_loo array
loo_d1 = {}         # station → d1_bear_5_loo array
loo_nact = {}       # station → n_active_loo array

for removed_station in GRUPO_A:
    # Build allowed stations per row WITHOUT the removed station
    def build_loo_allowed(pt):
        base = TYPE_MASKS.get(pt, [])
        return [s for s in base if s != removed_station]

    loo_allowed = df["pivot_type"].apply(build_loo_allowed)

    loo_cascade, loo_d1_bear, loo_n, _, _ = compute_cascade_conviction(
        df, loo_allowed, d1_mean, d1_std, dom25_mean, dom25_std
    )
    loo_cascades[removed_station] = loo_cascade
    loo_d1[removed_station] = loo_d1_bear
    loo_nact[removed_station] = loo_n

    loo_ic = safe_ic(loo_cascade, target)
    n_loo = (~np.isnan(loo_cascade) & ~np.isnan(target)).sum()
    delta = full_ic - loo_ic
    sign = "APORTA" if delta > 0 else ("NEUTRAL" if delta == 0 else "PESO MUERTO")

    print(f"  SIN {removed_station:10s} → IC={loo_ic:+.6f}  Δ={delta:+.6f}  "
          f"n={n_loo}  d1_bear_5_mean={np.nanmean(loo_d1_bear):.4f}  → {sign}")

print()

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 4: Bootstrap CI95 (paired, 3000 iteraciones)
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 60)
print("BOOTSTRAP CI95 (3000 iter, paired, seed=42)")
print("=" * 60)

# Use only rows where full cascade is valid
valid_mask = ~np.isnan(full_cascade) & ~np.isnan(target)
full_boot = full_cascade[valid_mask]
target_boot = target[valid_mask]
loo_boot_list = [loo_cascades[s][valid_mask] for s in GRUPO_A]

mean_deltas, ci_lo, ci_hi, p_leq0 = paired_bootstrap(
    full_boot, loo_boot_list, target_boot, n_iter=3000, seed=42
)

# Bootstrap for full IC
print("\n[FULL] Bootstrap del IC completo vs cascade_50:")
full_ic_boot = []
rng_boot = np.random.RandomState(42)
for _ in range(3000):
    idx = rng_boot.choice(len(target_boot), size=len(target_boot), replace=True)
    m = ~np.isnan(full_boot[idx])
    ic_b = safe_ic(full_boot[idx][m], target_boot[idx][m])
    if not np.isnan(ic_b):
        full_ic_boot.append(ic_b)
full_ic_boot = np.array(full_ic_boot)
full_ic_mean = np.mean(full_ic_boot)
full_ic_ci = (np.percentile(full_ic_boot, 2.5), np.percentile(full_ic_boot, 97.5))
print(f"  IC medio = {full_ic_mean:+.6f}  CI95 = [{full_ic_ci[0]:+.6f}, {full_ic_ci[1]:+.6f}]")

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 5: Veredictos por estación
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("VEREDICTOS — Contribución marginal al IC del cascade")
print("=" * 60)

station_verdicts = []
for j, s in enumerate(GRUPO_A):
    loo_ic = safe_ic(loo_cascades[s], target)
    delta = full_ic - loo_ic
    d_ci = (ci_lo[j], ci_hi[j])
    p_dead = p_leq0[j]

    # Veredicto basado en CI95
    if not np.isnan(d_ci[0]) and not np.isnan(d_ci[1]):
        if d_ci[0] > 0 and d_ci[1] > 0:
            verdict = "APORTA_VALOR"
        elif d_ci[1] < 0 and d_ci[0] < 0:
            verdict = "PESO_MUERTO"
        elif delta > 0:
            verdict = "APORTA_DEBIL"
        else:
            verdict = "PESO_MUERTO_DEBIL"
    else:
        verdict = "INDETERMINADO"

    # Cobertura: fracción donde la estación tiene voto + era allowed
    col = f"{s}_d1_vote"
    n_covered = 0
    for i in range(N):
        pt = df.iloc[i]["pivot_type"]
        allowed = TYPE_MASKS.get(pt, GRUPO_A)
        if s not in allowed:
            continue
        if pd.notna(df.iloc[i][col]):
            n_covered += 1
    total_allowed = sum(1 for i in range(N) if s in TYPE_MASKS.get(df.iloc[i]["pivot_type"], GRUPO_A))
    coverage = n_covered / total_allowed if total_allowed > 0 else 0.0

    # Frecuencia de voto bearish
    vals = df[col].dropna().values
    frac_bear = (vals < 0).mean() if len(vals) > 0 else 0.0
    frac_zero = (vals == 0).mean() if len(vals) > 0 else 0.0
    frac_bull = (vals > 0).mean() if len(vals) > 0 else 0.0

    # n_active medio en LOO (cuántas estaciones activas después de remover)
    mean_n_loo = np.nanmean(loo_nact[s])

    v = {
        "station": s,
        "delta_ic": round(float(delta), 6),
        "delta_ci95": [round(float(d_ci[0]), 6), round(float(d_ci[1]), 6)],
        "p_dead_weight": round(float(p_dead), 4),
        "verdict": verdict,
        "full_ic": round(float(full_ic), 6),
        "loo_ic": round(float(loo_ic), 6) if not np.isnan(loo_ic) else None,
        "coverage": round(float(coverage), 4),
        "n_active_mean_loo": round(float(mean_n_loo), 2),
        "d1_bear_5_full_mean": round(float(np.nanmean(full_d1)), 6),
        "d1_bear_5_loo_mean": round(float(np.nanmean(loo_d1[s])), 6),
        "vote_distribution": {
            "bear": round(float(frac_bear), 4),
            "neutral": round(float(frac_zero), 4),
            "bull": round(float(frac_bull), 4),
        },
        "n_valid_votes": int((~df[col].isna()).sum()),
    }
    station_verdicts.append(v)

    ci_str = f"[{d_ci[0]:+.4f}, {d_ci[1]:+.4f}]" if not (np.isnan(d_ci[0]) or np.isnan(d_ci[1])) else "[NaN]"
    print(f"  {s:10s}  Δ_IC={delta:+.4f}  CI95={ci_str}  p≤0={p_dead:.4f}  → {verdict}")

# ── Determinar locomotora y peso muerto ─────────────────────────────────────
print("\n" + "=" * 60)
print("LOCOMOTORA Y PESO MUERTO DEL CASCADE")
print("=" * 60)

ranked = sorted(station_verdicts, key=lambda v: v["delta_ic"], reverse=True)
locomotora = ranked[0]
peso_muerto = ranked[-1]

print(f"  LOCOMOTORA: {locomotora['station']}  Δ_IC={locomotora['delta_ic']:+.4f}  ({locomotora['verdict']})")
print(f"  PESO MUERTO: {peso_muerto['station']}  Δ_IC={peso_muerto['delta_ic']:+.4f}  ({peso_muerto['verdict']})")
print(f"  Ranking completo: ", " > ".join(f"{v['station']}({v['delta_ic']:+.4f})" for v in ranked))

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 6: Descomposición por pivot_type (MIN vs MAX)
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("DESCOMPOSICIÓN POR PIVOT_TYPE (MIN vs MAX)")
print("=" * 60)

by_type = {}
for ptype in ["MIN", "MAX"]:
    mask = (df["pivot_type"] == ptype).values
    n_pt = mask.sum()
    print(f"\n  [{ptype}] n={n_pt}, cascade_50=1: {df.loc[mask, 'cascade_50'].sum()}")

    # Full IC for this pivot type
    full_pt = full_cascade[mask]
    target_pt = target[mask]
    ic_full_pt = safe_ic(full_pt, target_pt)
    print(f"    IC_full = {ic_full_pt:+.6f}")

    by_type[ptype] = {}
    for s in GRUPO_A:
        loo_pt = loo_cascades[s][mask]
        ic_loo_pt = safe_ic(loo_pt, target_pt)
        delta_pt = ic_full_pt - ic_loo_pt if not (np.isnan(ic_full_pt) or np.isnan(ic_loo_pt)) else np.nan
        sign = "APORTA" if delta_pt > 0 else ("PESO MUERTO" if delta_pt < 0 else "NEUTRAL")
        print(f"    SIN {s:10s} → IC_loo={ic_loo_pt:+.6f}  Δ={delta_pt:+.6f}  → {sign}")
        by_type[ptype][s] = {
            "ic_full": round(float(ic_full_pt), 6) if not np.isnan(ic_full_pt) else None,
            "ic_loo": round(float(ic_loo_pt), 6) if not np.isnan(ic_loo_pt) else None,
            "delta_ic": round(float(delta_pt), 6) if not np.isnan(delta_pt) else None,
            "verdict": sign,
            "n_pivots": int(n_pt),
        }

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 7: Guardar reporte JSON
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("ESCRIBIENDO REPORTE JSON")
print("=" * 60)

report = {
    "_meta": {
        "analysis": "CASCADE (Grupo A) Leave-One-Out",
        "formula": "d1_bear_5(fractional) → z_bear → cascade_conviction = 0.66*z_bear + 0.34*z_dom25",
        "target": "cascade_50 (0/1)",
        "metric": "Spearman IC",
        "data": "quants_obs.pkl",
        "n_pivots": int(N),
        "bootstrap": "3000 iteraciones, paired, seed=42",
        "generated_at": pd.Timestamp.now().isoformat(),
    },
    "calibration": {
        "d1_mean": d1_mean,
        "d1_std": d1_std,
        "dom25_mean": dom25_mean,
        "dom25_std": dom25_std,
        "w_bear": 0.66,
        "w_dom": 0.34,
        "baseline_ic_in_sample": baseline,
    },
    "full_cascade": {
        "ic_vs_cascade_50": round(float(full_ic), 6),
        "ic_bootstrap_mean": round(float(full_ic_mean), 6),
        "ic_bootstrap_ci95": [round(float(full_ic_ci[0]), 6), round(float(full_ic_ci[1]), 6)],
        "n_valid": int(n_full),
        "ic_vs_stored_cascade_conviction": round(float(ic_stored), 6),
        "d1_bear_5_mean": round(float(np.nanmean(full_d1)), 6),
        "d1_bear_5_std": round(float(np.nanstd(full_d1)), 6),
    },
    "leave_one_out": station_verdicts,
    "locomotora": {
        "station": locomotora["station"],
        "delta_ic": locomotora["delta_ic"],
        "verdict": locomotora["verdict"],
    },
    "peso_muerto": {
        "station": peso_muerto["station"],
        "delta_ic": peso_muerto["delta_ic"],
        "verdict": peso_muerto["verdict"],
    },
    "ranked_contributions": [
        {"rank": i + 1, "station": v["station"], "delta_ic": v["delta_ic"],
         "verdict": v["verdict"]}
        for i, v in enumerate(ranked)
    ],
    "by_pivot_type": by_type,
    "summary": (
        f"Locomotora del cascade: {locomotora['station']} (Δ_IC={locomotora['delta_ic']:+.4f}). "
        f"Peso muerto: {peso_muerto['station']} (Δ_IC={peso_muerto['delta_ic']:+.4f}). "
        f"El cascade completo tiene IC={full_ic:+.4f} (n={n_full}) contra cascade_50."
    ),
}

report_path = SCRATCH / "cascade_station_leave_one_out_report.json"
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

elapsed = time.time() - t0
print(f"\nReporte guardado en: {report_path}")
print(f"Tiempo total: {elapsed:.1f}s")
print("\n" + "=" * 70)
print("RESUMEN FINAL")
print("=" * 70)
print(report["summary"])
print()
for v in ranked:
    print(f"  {v['station']:10s}  Δ_IC={v['delta_ic']:+.4f}  CI95={v['delta_ci95']}  → {v['verdict']}")
print()