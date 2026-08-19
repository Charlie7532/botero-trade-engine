#!/usr/bin/env python3
"""
CASCADE WALK-FORWARD — VALIDACIÓN OOS DE LA REDUCCIÓN DEL GRUPO A
==================================================================
P1-prerequisito: ANTES de tocar el cascade (columna vertebral, IC +0.41, PBO=0%),
validar si la reducción del Grupo A (5 estaciones → vix+bsi) SOBREVIVE out-of-sample.

El leave-one-out IN-SAMPLE mostró:
  - VIX es la locomotora (+0.1147)
  - ROTATION resta (-0.0124): quitarla mejora IS de +0.4147 -> +0.4271
  - CREDIT resta (-0.0020): quitarlo mejora a +0.4167
  - BSI y FG aportan marginalmente (ns)

Sospecha: el cascade óptimo podría ser VIX+BSI (2 estaciones).

PERO leave-one-out es IN-SAMPLE. Aquí se valida con walk-forward expanding window.

MÉTODO
------
5 configuraciones:
  A (actual): vix + bsi + fg + credit + rotation  (5 estaciones)
  B:          vix + bsi                            (2)
  C:          vix + bsi + fg                       (3)
  D:          vix + bsi + credit                   (3)
  E:          vix + bsi + rotation                 (3)

Walk-forward expanding window:
  - Train inicial: primeras 500 observaciones.
  - Expandir de a 50 observaciones.
  - En cada fold, se computa cascade_conviction para cada configuración sobre el
    fold OOS (test) y se mide Spearman IC contra cascade_50.

Fórmula (referencia decay_check_cascade_conviction.py, replica exacta):
  d1_bear_5 = fracción de votos bearish (conteo FRACCIONAL, type-mask MIN/MAX)
  z_bear    = (d1_bear_5 - 0.41) / 0.3206
  z_dom25   = (abs_prev_leg_return - 0.0532) / 0.035
  cascade_conviction = 0.66 * z_bear + 0.34 * z_dom25

Type-mask (cascade_calibration.json):
  MIN: [vix, bsi, fg, credit, rotation]
  MAX: [vix, bsi, credit, rotation]   (fg MIN-only)

Convención (igual que leave-one-out / add-one-in): calibración FIJA del Grupo A base
(0.41/0.3206) aplicada a TODAS las configuraciones. Variante secundaria REFIT por fold
(mu/sigma re-estimados en el train de cada fold) como chequeo de robustez.

DATOS: quants_obs.pkl (1,590 pivotes zz25)
MÉTRICA PRIMARIA: Spearman IC OOS vs cascade_50, CI95 bootstrap.
"""

import json, time
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from pathlib import Path

RNG_SEED = 42
BOOT_ITER = 3000

# ── Config ──────────────────────────────────────────────────────────────────
PROJECT_DIR = Path("/root/botero-trade")
SCRATCH = PROJECT_DIR / "data/research"
CALIBRATION_PATH = PROJECT_DIR / "backend/modules/entry_decision/domain/rules/cascade_calibration.json"
QUANTS_PATH = SCRATCH / "quants_obs.pkl"

GRUPO_A = ["vix", "bsi", "fg", "credit", "rotation"]

CONFIGS = {
    "A_5estaciones":    ["vix", "bsi", "fg", "credit", "rotation"],
    "B_vix_bsi":        ["vix", "bsi"],
    "C_vix_bsi_fg":     ["vix", "bsi", "fg"],
    "D_vix_bsi_credit": ["vix", "bsi", "credit"],
    "E_vix_bsi_rotation": ["vix", "bsi", "rotation"],
}

# Type mask (autoritativo, del JSON de calibración)
TYPE_MASKS = {
    "MIN": ["vix", "bsi", "fg", "credit", "rotation"],
    "MAX": ["vix", "bsi", "credit", "rotation"],
}

TRAIN_INIT = 500
STEP = 50


# ── Helpers ─────────────────────────────────────────────────────────────────

def compute_d1_bear_5(df, config):
    """
    Fracción bearish fraccional: sum(-v para v<0) / n_active, donde n_active =
    nº de estaciones de `config` permitidas por el type-mask del pivot_type con
    voto no-NaN. Vectorizado.
    Retorna (d1_bear_5, n_active).
    """
    N = len(df)
    pt = df["pivot_type"].values  # 'MIN' / 'MAX'
    votes = np.column_stack([df[f"{s}_d1_vote"].values.astype(float) for s in config])
    allowed = np.zeros_like(votes, dtype=bool)
    for j, s in enumerate(config):
        for pt_val, stations in TYPE_MASKS.items():
            if s in stations:
                allowed[pt == pt_val, j] = True
    valid = ~np.isnan(votes)
    m = allowed & valid
    n_active = m.sum(axis=1)
    bear_contrib = np.where(votes < 0, -votes, 0.0)
    bear_sum = np.where(m, bear_contrib, 0.0).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        d1 = np.where(n_active > 0, bear_sum / np.where(n_active > 0, n_active, 1), np.nan)
    return d1, n_active


def cascade_conviction_from_d1(d1_bear, abs_ret, d1_mean, d1_std, dom_mean, dom_std,
                               w_bear=0.66, w_dom=0.34):
    """cascade_conviction = w_bear*(d1-d1_mean)/d1_std + w_dom*(abs_ret-dom_mean)/dom_std"""
    z_bear = (d1_bear - d1_mean) / d1_std
    z_dom = (abs_ret - dom_mean) / dom_std
    return w_bear * z_bear + w_dom * z_dom


def safe_ic(score, target):
    """Spearman IC, NaN si < 10 pares válidos o varianza nula."""
    mask = ~np.isnan(score) & ~np.isnan(target)
    if mask.sum() < 10 or np.std(score[mask]) == 0 or np.std(target[mask]) == 0:
        return np.nan
    ic, _ = spearmanr(score[mask], target[mask])
    return float(ic)


def bootstrap_ic(score, target, n_iter=BOOT_ITER, seed=RNG_SEED):
    """CI95 (percentil 2.5/97.5) del Spearman IC vía bootstrap por pares."""
    rng = np.random.RandomState(seed)
    valid = ~np.isnan(score) & ~np.isnan(target)
    s = score[valid]
    t = target[valid]
    n = len(s)
    if n < 10:
        return np.nan, np.nan, np.nan, 0
    ics = []
    for _ in range(n_iter):
        idx = rng.choice(n, size=n, replace=True)
        ic_b = safe_ic(s[idx], t[idx])
        if not np.isnan(ic_b):
            ics.append(ic_b)
    ics = np.array(ics)
    return float(np.mean(ics)), float(np.percentile(ics, 2.5)), float(np.percentile(ics, 97.5)), len(ics)


def bootstrap_mean_folds(fold_ics, n_iter=BOOT_ITER, seed=RNG_SEED):
    """CI95 de la media de IC por fold vía bootstrap sobre folds."""
    rng = np.random.RandomState(seed)
    a = np.asarray(fold_ics, dtype=float)
    a = a[~np.isnan(a)]
    if len(a) == 0:
        return np.nan, np.nan, np.nan
    means = []
    for _ in range(n_iter):
        means.append(np.mean(rng.choice(a, size=len(a), replace=True)))
    means = np.array(means)
    return float(np.mean(a)), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def bootstrap_paired_delta(fold_ic_x, fold_ic_a, n_iter=BOOT_ITER, seed=RNG_SEED):
    """
    Delta pareado por fold: delta_fold = IC(X) - IC(A) en el MISMO fold.
    Bootstrap sobre folds. Retorna (mean_delta, ci_lo, ci_hi, frac_folds_x_gt_a,
    p_delta_le0_boot).
    """
    rng = np.random.RandomState(seed)
    x = np.asarray(fold_ic_x, dtype=float)
    a = np.asarray(fold_ic_a, dtype=float)
    m = ~np.isnan(x) & ~np.isnan(a)
    x, a = x[m], a[m]
    if len(x) == 0:
        return np.nan, np.nan, np.nan, np.nan, np.nan
    deltas = x - a
    frac_gt0 = float(np.mean(deltas > 0))
    boots = []
    for _ in range(n_iter):
        idx = rng.choice(len(deltas), size=len(deltas), replace=True)
        boots.append(np.mean(deltas[idx]))
    boots = np.array(boots)
    mean_delta = float(np.mean(deltas))
    ci_lo = float(np.percentile(boots, 2.5))
    ci_hi = float(np.percentile(boots, 97.5))
    p_le0 = float(np.mean(boots <= 0))
    return mean_delta, ci_lo, ci_hi, frac_gt0, p_le0


# ═══════════════════════════════════════════════════════════════════════════════
# PASO 1: Cargar datos y calibración
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 78)
print("CASCADE WALK-FORWARD REDUCCIÓN — GRUPO A (5 vs 2-3 estaciones)")
print("=" * 78)

t0 = time.time()

with open(CALIBRATION_PATH, "r", encoding="utf-8") as f:
    calib = json.load(f)
d1_mean = calib["d1_bear_5"]["mean"]
d1_std = calib["d1_bear_5"]["std"]
dom25_mean = calib["domino_zz25"]["mean"]
dom25_std = calib["domino_zz25"]["std"]
w_bear = calib["type_mask"]["MIN"]["w_bear"]
w_dom = calib["type_mask"]["MIN"]["w_dom"]
baseline_is = calib.get("baseline_ic_in_sample", {})
baseline_oos = calib.get("baseline_ic_oos", {})
print(f"Calibración FIJA: d1_mean={d1_mean}, d1_std={d1_std}, "
      f"dom25_mean={dom25_mean}, dom25_std={dom25_std}, w_bear={w_bear}, w_dom={w_dom}")
print(f"Baseline IS (json): cascade_50={baseline_is.get('cascade_50')}  "
      f"| Baseline OOS (json): cascade_50={baseline_oos.get('cascade_50')}")

df = pd.read_pickle(QUANTS_PATH)
N = len(df)
target = df["cascade_50"].values.astype(float)
abs_ret = df["abs_prev_leg_return"].values.astype(float)
print(f"quants_obs.pkl: {N} pivotes  |  cascade_50=1: {int(df['cascade_50'].sum())}  "
      f"({100*df['cascade_50'].mean():.1f}%)")

# Precomputar d1_bear_5 y cascade_conviction FULL-SAMPLE por configuración (calibración FIJA)
d1_bear_full = {}
conv_full = {}
n_active_full = {}
for cname, cfg in CONFIGS.items():
    d1, nact = compute_d1_bear_5(df, cfg)
    conv = cascade_conviction_from_d1(d1, abs_ret, d1_mean, d1_std, dom25_mean, dom25_std, w_bear, w_dom)
    d1_bear_full[cname] = d1
    conv_full[cname] = conv
    n_active_full[cname] = nact

# ── In-sample IC por configuración (referencia, para el relato IS vs OOS) ──
print("\n" + "=" * 78)
print("IN-SAMPLE (referencia, full 1,590 pivotes, calibración FIJA)")
print("=" * 78)
print(f"  {'config':20s}  {'IC_IS':>9s}  {'n_valid':>8s}  {'n_active_medio':>14s}")
is_ics = {}
for cname, cfg in CONFIGS.items():
    ic = safe_ic(conv_full[cname], target)
    n_valid = (~np.isnan(conv_full[cname]) & ~np.isnan(target)).sum()
    nact_mean = np.nanmean(n_active_full[cname])
    is_ics[cname] = ic
    print(f"  {cname:20s}  {ic:+.6f}  {n_valid:8d}  {nact_mean:14.2f}")

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 2: Walk-forward expanding window (calibración FIJA — primaria)
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f"WALK-FORWARD EXPANDING (train_init={TRAIN_INIT}, step={STEP}) — calibración FIJA")
print("=" * 78)

folds = []
train_end = TRAIN_INIT
while train_end < N:
    test_end = min(train_end + STEP, N)
    folds.append((0, train_end, train_end, test_end))
    train_end = test_end
n_folds = len(folds)
print(f"Folds: {n_folds}  (último fold test={folds[-1][2]}:{folds[-1][3]}, tamaño={folds[-1][3]-folds[-1][2]})")

# Per-fold IC por configuración (calibración FIJA)
fold_ic_fixed = {cname: [] for cname in CONFIGS}
fold_details = []
for fi, (tr_s, tr_e, te_s, te_e) in enumerate(folds):
    row = {"fold": fi + 1, "train_range": [int(tr_s), int(tr_e)],
           "test_range": [int(te_s), int(te_e)], "test_size": int(te_e - te_s)}
    for cname in CONFIGS:
        ic = safe_ic(conv_full[cname][te_s:te_e], target[te_s:te_e])
        fold_ic_fixed[cname].append(ic)
        row[cname] = (round(float(ic), 6) if not np.isnan(ic) else None)
    fold_details.append(row)

# ── Resumen OOS FIJO ──
print("\n" + "-" * 78)
print("IC OOS (calibración FIJA) por configuración")
print("-" * 78)
print(f"  {'config':20s}  {'IC_OOS_mean':>11s}  {'CI95':>23s}  {'pooled':>9s}  {'%folds>0':>9s}")
summary_fixed = {}
for cname in CONFIGS:
    fics = np.array(fold_ic_fixed[cname], dtype=float)
    mean_f, lo_f, hi_f = bootstrap_mean_folds(fics)
    # Pooled: concatenar OOS scores de todos los folds
    oos_score = np.concatenate([conv_full[cname][te_s:te_e] for _, _, te_s, te_e in folds])
    oos_target = np.concatenate([target[te_s:te_e] for _, _, te_s, te_e in folds])
    pooled, plo, phi, _ = bootstrap_ic(oos_score, oos_target)
    pct_pos = float(np.nanmean(fics > 0)) * 100
    summary_fixed[cname] = {
        "mean_fold_ic": round(float(np.nanmean(fics)), 6),
        "ci95_mean_fold": [round(lo_f, 6), round(hi_f, 6)],
        "pooled_ic": round(pooled, 6),
        "ci95_pooled": [round(plo, 6), round(phi, 6)],
        "pct_folds_positive": round(pct_pos, 2),
        "n_folds": int(n_folds),
        "n_folds_valid": int((~np.isnan(fics)).sum()),
    }
    ci_str = f"[{lo_f:+.4f}, {hi_f:+.4f}]"
    print(f"  {cname:20s}  {np.nanmean(fics):+.6f}  {ci_str}  {pooled:+.4f}  {pct_pos:8.1f}%")

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 3: Comparación pareada por fold (reducidas vs A)
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print("COMPARACIÓN PAREADA OOS — reducidas vs A (5 estaciones), mismo fold")
print("=" * 78)
print(f"  {'config':20s}  {'delta_OOS':>10s}  {'CI95_delta':>23s}  {'%folds>':>8s}  {'p(d<=0)':>8s}")

paired = {}
ref = "A_5estaciones"
for cname in [c for c in CONFIGS if c != ref]:
    mean_d, dlo, dhi, frac_gt, p_le = bootstrap_paired_delta(
        np.array(fold_ic_fixed[cname]), np.array(fold_ic_fixed[ref]))
    paired[cname] = {
        "delta_mean_fold_ic": round(float(mean_d), 6),
        "ci95_delta": [round(dlo, 6), round(dhi, 6)],
        "frac_folds_beats_A": round(float(frac_gt), 4),
        "p_delta_le0_boot": round(float(p_le), 4),
    }
    ci_str = f"[{dlo:+.4f}, {dhi:+.4f}]"
    print(f"  {cname:20s}  {mean_d:+.6f}  {ci_str}  {100*frac_gt:7.1f}%  {p_le:8.4f}")

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 4: Variante de robustez — REFIT por fold (mu/sigma del train)
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print("ROBUSTEZ — REFIT por fold (mu/sigma re-estimados en train de cada fold)")
print("=" * 78)

fold_ic_refit = {cname: [] for cname in CONFIGS}
for fi, (tr_s, tr_e, te_s, te_e) in enumerate(folds):
    # Refit de calibración sobre el train window (por configuración)
    for cname in CONFIGS:
        d1_tr = d1_bear_full[cname][tr_s:tr_e]
        ar_tr = abs_ret[tr_s:tr_e]
        m1 = np.nanmean(d1_tr)
        s1 = np.nanstd(d1_tr)
        md = np.nanmean(ar_tr)
        sd = np.nanstd(ar_tr)
        if s1 == 0 or sd == 0 or np.isnan(m1) or np.isnan(md):
            ic = np.nan
        else:
            conv_te = cascade_conviction_from_d1(
                d1_bear_full[cname][te_s:te_e], abs_ret[te_s:te_e],
                m1, s1, md, sd, w_bear, w_dom)
            ic = safe_ic(conv_te, target[te_s:te_e])
        fold_ic_refit[cname].append(ic)

print(f"  {'config':20s}  {'IC_OOS_mean':>11s}  {'CI95':>23s}  {'%folds>0':>9s}")
summary_refit = {}
for cname in CONFIGS:
    fics = np.array(fold_ic_refit[cname], dtype=float)
    mean_f, lo_f, hi_f = bootstrap_mean_folds(fics)
    pct_pos = float(np.nanmean(fics > 0)) * 100
    summary_refit[cname] = {
        "mean_fold_ic": round(float(np.nanmean(fics)), 6),
        "ci95_mean_fold": [round(lo_f, 6), round(hi_f, 6)],
        "pct_folds_positive": round(pct_pos, 2),
    }
    ci_str = f"[{lo_f:+.4f}, {hi_f:+.4f}]"
    print(f"  {cname:20s}  {np.nanmean(fics):+.6f}  {ci_str}  {pct_pos:8.1f}%")

# ── Paired refit ──
paired_refit = {}
for cname in [c for c in CONFIGS if c != ref]:
    mean_d, dlo, dhi, frac_gt, p_le = bootstrap_paired_delta(
        np.array(fold_ic_refit[cname]), np.array(fold_ic_refit[ref]))
    paired_refit[cname] = {
        "delta_mean_fold_ic": round(float(mean_d), 6),
        "ci95_delta": [round(dlo, 6), round(dhi, 6)],
        "frac_folds_beats_A": round(float(frac_gt), 4),
        "p_delta_le0_boot": round(float(p_le), 4),
    }

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 5: Veredicto
# ═══════════════════════════════════════════════════════════════════════════════

def verdict_for(cname):
    s = summary_fixed[cname]
    p = paired.get(cname)
    return {
        "ic_oos_mean": s["mean_fold_ic"],
        "ci95_mean_fold": s["ci95_mean_fold"],
        "pooled_ic": s["pooled_ic"],
        "pct_folds_positive": s["pct_folds_positive"],
        "ic_is": is_ics[cname],
    }

print("\n" + "=" * 78)
print("VEREDICTO")
print("=" * 78)

# Criterio: ¿alguna reducida supera a A de forma ROBUSTA OOS?
#   robusta = delta_mean_fold_ic > 0 Y (ci95_delta no cruza 0 hacia abajo, o
#             frac_folds_beats_A >= 0.6)
winners = []
for cname in [c for c in CONFIGS if c != ref]:
    p = paired[cname]
    mean_d = p["delta_mean_fold_ic"]
    dlo, dhi = p["ci95_delta"]
    frac = p["frac_folds_beats_A"]
    robust = mean_d > 0 and (dlo > 0 or frac >= 0.6)
    status = ("SOBREVIVE_OOS" if robust else "NO_SOBREVIVE_OOS")
    print(f"  {cname:20s}  delta_OOS={mean_d:+.4f} CI95=[{dlo:+.4f},{dhi:+.4f}] "
          f"folds>A={100*frac:.0f}%  → {status}")
    winners.append({"config": cname, "delta_mean_fold_ic": mean_d,
                    "ci95_delta": [dlo, dhi], "frac_folds_beats_A": frac,
                    "status": status})

best_reduced = max(winners, key=lambda w: w["delta_mean_fold_ic"])
best_status = best_reduced["status"]

if best_status == "SOBREVIVE_OOS":
    overall = (
        f"LA REDUCCIÓN SOBREVIVE OOS. Configuración ganadora: {best_reduced['config']} "
        f"(delta_OOS={best_reduced['delta_mean_fold_ic']:+.4f} vs 5 estaciones). "
        "Documentar para el prompt de Gemini."
    )
else:
    overall = (
        "LA REDUCCIÓN NO SOBREVIVE OOS. La mejora in-sample del leave-one-out es "
        "overfitting in-sample. NO tocar el cascade: mantener las 5 estaciones del Grupo A."
    )

print(f"\n  {overall}")
print(f"  Mejor reducida: {best_reduced['config']} (delta_OOS={best_reduced['delta_mean_fold_ic']:+.4f})")

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 6: Guardar reporte JSON
# ═══════════════════════════════════════════════════════════════════════════════

report = {
    "_meta": {
        "task": "cascade_walkforward_reduccion",
        "question": "¿La reducción del Grupo A (5 estaciones → vix+bsi y variantes) sobrevive OOS, o es overfitting in-sample?",
        "data": "data/research/pivots/quants_obs.pkl (1,590 pivotes zz25)",
        "formula": "cascade_conviction = 0.66*(d1_bear_5-0.41)/0.3206 + 0.34*(abs_prev_leg_return-0.0532)/0.035",
        "counting": "FRACCIONAL, type-mask MIN/MAX (fg MIN-only)",
        "metric": "Spearman IC vs cascade_50",
        "walk_forward": {"train_init": TRAIN_INIT, "step": STEP, "n_folds": n_folds,
                         "expanding": True, "test_size_last_fold": int(folds[-1][3] - folds[-1][2])},
        "bootstrap": {"n_iter": BOOT_ITER, "seed": RNG_SEED},
        "calibration_primary": "FIJA (0.41/0.3206 Grupo A base, aplicada a todas las configs)",
        "calibration_robustness": "REFIT por fold (mu/sigma del train)",
        "generated_at": pd.Timestamp.now().isoformat(),
    },
    "calibration": {
        "d1_mean": d1_mean, "d1_std": d1_std,
        "dom25_mean": dom25_mean, "dom25_std": dom25_std,
        "w_bear": w_bear, "w_dom": w_dom,
        "baseline_ic_in_sample": baseline_is,
        "baseline_ic_oos": baseline_oos,
    },
    "configs": {cname: {"stations": cfg, "stations_min": [s for s in cfg if s in TYPE_MASKS["MIN"]],
                        "stations_max": [s for s in cfg if s in TYPE_MASKS["MAX"]],
                        "n_stations_label": len(cfg)} for cname, cfg in CONFIGS.items()},
    "in_sample_reference": {cname: {"ic_is": round(is_ics[cname], 6),
                                    "n_active_mean": round(float(np.nanmean(n_active_full[cname])), 3)}
                            for cname in CONFIGS},
    "oos_fixed_calibration": summary_fixed,
    "oos_refit_calibration": summary_refit,
    "paired_vs_A_fixed": paired,
    "paired_vs_A_refit": paired_refit,
    "fold_details": fold_details,
    "verdict": {
        "overall": overall,
        "best_reduced_config": best_reduced["config"],
        "best_reduced_delta_oos": best_reduced["delta_mean_fold_ic"],
        "best_reduced_status": best_status,
        "criterion": "robusta = delta_OOS_mean_fold > 0 y (CI95 no cruza 0 hacia abajo o folds>A >= 60%)",
        "action": ("DOCUMENTAR config ganadora para prompt de Gemini" if best_status == "SOBREVIVE_OOS"
                   else "NO TOCAR el cascade (mantener 5 estaciones Grupo A)"),
    },
}

report_path = SCRATCH / "cascade_walkforward_reduccion_report.json"
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

elapsed = time.time() - t0
print(f"\nReporte guardado en: {report_path}")
print(f"Tiempo total: {elapsed:.1f}s")
print()
print("RESUMEN FINAL")
print("-" * 78)
for cname in CONFIGS:
    s = summary_fixed[cname]
    print(f"  {cname:20s}  IS={is_ics[cname]:+.4f}  OOS_mean={s['mean_fold_ic']:+.4f} "
          f"CI95={s['ci95_mean_fold']}  pooled={s['pooled_ic']:+.4f}  folds>0={s['pct_folds_positive']:.0f}%")
print(f"\n  VEREDICTO: {overall}")
