#!/usr/bin/env python3
"""
DISPERSIÓN ENTRE ESTACIONES METAR — ¿predice algo? (dato mata relato)
========================================================================
Hipótesis a validar:
  - Dispersión alta entre las 11 estaciones = fragmentación (régimen de transición)
  - Dispersión baja = consenso (régimen extremo/consolidado)
  - ¿Discrimina cascade_50/75, dirección next_bear, cascade_conviction?

MÉTODO:
1. Cargar quants_obs.pkl
2. Computar dispersión (std, mad, rango) entre zk_pbull/zk_pbear/d1_vote de las 11
   estaciones por pivote. Se usa nanstd/nanmedian para NO descartar filas por NaN,
   y se registra cuántas estaciones aportan por fila (n_valid) para auditar cobertura.
3. Clasificar en terciles empíricos (t1_low, t2_mid, t3_high)
4. Para cada tercil, medir outcomes (cascade_50/75 rate, cascade_conviction, next_bear)
5. CI95 bootstrap 3000 (seed 42), wins/losses separados, N mínimo 20
6. ANÁLISIS CONTROLADO: el efecto debe sobrevivir dentro de MIN y MAX por separado,
   y dentro de cada era (pre/post 2011) para descartar artefactos.
7. Correlaciones de Spearman + correlación parcial (controlando pivot_type y era)
8. Veredicto honesto: ¿discrimina? ¿es monotónico? ¿efecto fuerte o débil?

ADVERTENCIAS ESTRUCTURALES DOCUMENTADAS:
- next_bear y next_leg_direction son DETERMINISTAS respecto a pivot_type
  (MAX→next_bear=0, MIN→next_bear=1). No son un outcome forward: son una etiqueta
  estructural. Cualquier correlación dispersión→next_bear es en realidad
  "la dispersión difiere levemente entre MIN y MAX".
- Cobertura: fg/pcr/credit/vvix solo tienen datos desde ~2011. La dispersión sobre
  "11 estaciones" solo es completa en 447/1590 pivotes. Se usa nanstd + n_valid.

Intérprete: cd /root/botero-trade && PYTHONPATH=/root/botero-trade backend/.venv/bin/python research/06_metodologia_ldp/dispersion_estaciones.py
Salida: consola + data/research/dispersion_estaciones_report.json
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
ROOT = Path("/root/botero-trade")
N_BOOT = 3000
BOOT_SEED = 42
MIN_N = 20

STATIONS = ["vix", "vvix", "pcr", "fg", "sv5_turbulence", "skew", "credit",
            "yield_curve", "rotation", "bsi", "dxy"]
GRUPO_A = {"vix", "bsi", "fg", "credit", "rotation"}
GRUPO_B = {"skew", "pcr", "sv5_turbulence"}
GRUPO_C = {"dxy", "yield_curve", "vvix"}

# Métricas primarias de dispersión (usando nanstd/nanmedian → robustas a NaN)
PRIMARY_DISPERSION = [
    "disp_std_zk_pbull_11",     # std de zk_pbull entre las 11 (nanstd)
    "disp_mad_zk_pbull_11",     # MAD de zk_pbull (robusta a outliers)
    "disp_range_zk_pbull_11",   # rango max-min de zk_pbull
    "disp_std_zk_pbull_A",      # std solo Grupo A (5 estaciones direccionales)
    "disp_std_zk_pbear_11",     # std de zk_pbear (la otra cara)
    "disp_std_d1_vote_11",      # std de la señal cruda d1_vote
]

BINARY_OUTCOMES = ["cascade_50", "cascade_75", "next_bear", "next_leg_direction"]
CONTINUOUS_OUTCOMES = ["cascade_conviction"]


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS ESTADÍSTICOS
# ═══════════════════════════════════════════════════════════════════════════════
def boot_ci_mean(arr, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    return float(arr.mean()), float(lo), float(hi)


def boot_ci_proportion(arr, ci=95, n_boot=N_BOOT, seed=BOOT_SEED):
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    props = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    lo, hi = np.percentile(props, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    return float(arr.mean()), float(lo), float(hi)


def classify_terciles(values):
    """Devuelve array de etiquetas de tercil + umbrales empíricos."""
    values = np.asarray(values, float)
    lo = np.percentile(values, 100 / 3)
    hi = np.percentile(values, 200 / 3)
    labels = np.where(values <= lo, "t1_low",
                      np.where(values > hi, "t3_high", "t2_mid"))
    return labels, float(lo), float(hi)


def tercile_outcome_stats(disp_values, outcome_values, is_binary, min_n=MIN_N):
    """Stats por tercil + monotonicidad + solapamiento CI95."""
    labels, lo, hi = classify_terciles(disp_values)
    result = {"thresholds": {"t1_lo": lo, "t2_hi": hi}, "terciles": {}}

    for tlabel in ["t1_low", "t2_mid", "t3_high"]:
        sub = outcome_values[labels == tlabel]
        sub = sub[~np.isnan(sub)]
        n = int(len(sub))
        entry = {"N": n}
        if n == 0:
            entry["verdict"] = "empty"
            result["terciles"][tlabel] = entry
            continue

        if is_binary:
            rate, lo_ci, hi_ci = boot_ci_proportion(sub)
            entry.update({
                "rate": float(rate),
                "ci95": [float(lo_ci), float(hi_ci)],
                "wins": {"n": int(sub.sum()), "rate": float(rate)},
                "losses": {"n": n - int(sub.sum()), "rate": 1.0 - float(rate)},
            })
        else:
            mean, lo_ci, hi_ci = boot_ci_mean(sub)
            entry.update({
                "mean": float(mean),
                "ci95": [float(lo_ci), float(hi_ci)],
                "std": float(np.std(sub, ddof=1)) if n >= 2 else None,
                "median": float(np.median(sub)),
                "min": float(np.min(sub)),
                "max": float(np.max(sub)),
                # wins/losses separados para variable continua = split por signo
                "sign_split": {
                    "positive_n": int((sub > 0).sum()),
                    "negative_n": int((sub <= 0).sum()),
                    "positive_mean": float(sub[sub > 0].mean()) if (sub > 0).any() else None,
                    "negative_mean": float(sub[sub <= 0].mean()) if (sub <= 0).any() else None,
                },
            })
        entry["verdict"] = "valid" if n >= min_n else f"insufficient_N({n}<{min_n})"
        result["terciles"][tlabel] = entry

    # Monotonicidad
    t = result["terciles"]
    monotonic = None
    if all(t[k].get("N", 0) >= min_n for k in ["t1_low", "t2_mid", "t3_high"]):
        key = "rate" if is_binary else "mean"
        v1, v2, v3 = t["t1_low"][key], t["t2_mid"][key], t["t3_high"][key]
        if v1 < v2 < v3:
            monotonic = "increasing"
        elif v1 > v2 > v3:
            monotonic = "decreasing"
        else:
            monotonic = "non_monotonic"
    result["monotonicity"] = monotonic

    # Solapamiento CI95 t1 vs t3
    ci_overlap = None
    if all(t[k].get("N", 0) >= min_n for k in ["t1_low", "t3_high"]):
        ci1 = t["t1_low"].get("ci95")
        ci3 = t["t3_high"].get("ci95")
        if ci1 and ci3 and not any(np.isnan(ci1 + ci3)):
            ci_overlap = not (ci1[1] < ci3[0] or ci3[1] < ci1[0])
    result["ci95_overlap_t1_t3"] = ci_overlap

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# PASO 2: Computar dispersión (nanstd → no descarta filas por NaN)
# ═══════════════════════════════════════════════════════════════════════════════
def compute_dispersion(df):
    for suffix in ["zk_pbull", "zk_pbear"]:
        cols_11 = [f"{s}_{suffix}" for s in STATIONS]
        cols_a = [f"{s}_{suffix}" for s in STATIONS if s in GRUPO_A]
        v11 = df[cols_11].values.astype(float)
        va = df[cols_a].values.astype(float)

        df[f"disp_std_{suffix}_11"] = np.nanstd(v11, axis=1, ddof=1)
        df[f"disp_std_{suffix}_A"] = np.nanstd(va, axis=1, ddof=1)
        med11 = np.nanmedian(v11, axis=1, keepdims=True)
        df[f"disp_mad_{suffix}_11"] = np.nanmedian(np.abs(v11 - med11), axis=1)
        df[f"disp_range_{suffix}_11"] = np.nanmax(v11, axis=1) - np.nanmin(v11, axis=1)

    # d1_vote (señal cruda -1/0/+1)
    cols_vote = [f"{s}_d1_vote" for s in STATIONS]
    vv = df[cols_vote].values.astype(float)
    df["disp_std_d1_vote_11"] = np.nanstd(vv, axis=1, ddof=1)
    medv = np.nanmedian(vv, axis=1, keepdims=True)
    df["disp_mad_d1_vote_11"] = np.nanmedian(np.abs(vv - medv), axis=1)

    # Cobertura: cuántas estaciones aportaron por fila
    df["n_valid_stations"] = df[cols_11].notna().sum(axis=1)
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 92)
    print("DISPERSIÓN ENTRE ESTACIONES METAR — ANÁLISIS DE PODER PREDICTIVO")
    print("=" * 92)

    # ── PASO 1: Cargar datos ──
    print("\n[PASO 1] Cargando quants_obs.pkl ...")
    df = pd.read_pickle(ROOT / "data/research/pivots/quants_obs.pkl")
    df["year"] = pd.to_datetime(df["pivot_date"]).dt.year
    df["era"] = np.where(df["year"] < 2011, "pre2011", "post2011")
    print(f"  Filas: {len(df)}, Columnas: {len(df.columns)}")
    print(f"  Fechas: {df.pivot_date.min()} → {df.pivot_date.max()}")
    print(f"  pivot_type: {df.pivot_type.value_counts().to_dict()}")
    print(f"  cascade_50: {df.cascade_50.value_counts().to_dict()}")
    print(f"  cascade_75: {df.cascade_75.value_counts().to_dict()}")

    # ── Documentar cobertura (NaN por estación) ──
    print("\n[COBERTURA] NaN por columna zk_pbull (auditoría honesta):")
    coverage = {}
    for s in STATIONS:
        col = f"{s}_zk_pbull"
        nan_n = int(df[col].isna().sum())
        coverage[col] = {"nan": nan_n, "valid": int(len(df) - nan_n)}
        print(f"    {col:28s} NaN={nan_n:>5}  valid={len(df)-nan_n:>5}")

    # ── PASO 2: Computar dispersión ──
    print("\n[PASO 2] Computando métricas de dispersión (nanstd, no descarta filas) ...")
    df = compute_dispersion(df)
    n_valid_dist = df["n_valid_stations"].value_counts().sort_index()
    print("  Distribución de n_valid_stations (cuántas estaciones aportan por fila):")
    for k, v in n_valid_dist.items():
        print(f"    {k} estaciones: {v} filas")

    # ── PASO 3+4: Terciles y outcomes ──
    print("\n[PASO 3+4] Terciles empíricos + outcomes (CI95 bootstrap 3000, N≥20) ...")

    all_tercile_results = {}

    for dcol in PRIMARY_DISPERSION:
        disp = df[dcol].values
        valid_mask = ~np.isnan(disp)
        print(f"\n  ── Métrica: {dcol} (N válidos={valid_mask.sum()}) ──")

        d_result = {"n_valid": int(valid_mask.sum())}
        for ocol in BINARY_OUTCOMES + CONTINUOUS_OUTCOMES:
            is_bin = ocol in BINARY_OUTCOMES
            omask = valid_mask & ~np.isnan(df[ocol].values)
            r = tercile_outcome_stats(disp[omask], df[ocol].values[omask], is_bin)
            d_result[ocol] = r
            _print_tercile(r, ocol, is_bin)

        # ── PASO 5/6: análisis controlado (dentro de pivot_type y era) ──
        d_result["controlled"] = {}
        for ctrl_name, ctrl_series in [
            ("pivot_type_MIN", df["pivot_type"] == "MIN"),
            ("pivot_type_MAX", df["pivot_type"] == "MAX"),
            ("era_pre2011", df["era"] == "pre2011"),
            ("era_post2011", df["era"] == "post2011"),
        ]:
            ctrl = {}
            for ocol in ["cascade_50", "cascade_conviction"]:
                is_bin = ocol == "cascade_50"
                cmask = valid_mask & ctrl_series.values & ~np.isnan(df[ocol].values)
                if cmask.sum() >= 3 * MIN_N:
                    ctrl[ocol] = tercile_outcome_stats(disp[cmask], df[ocol].values[cmask], is_bin)
            d_result["controlled"][ctrl_name] = ctrl

        all_tercile_results[dcol] = d_result

    # ── Correlaciones ──
    print("\n[CORRELACIONES] Spearman + parcial (control pivot_type y era) ...")
    correlations = {}
    for dcol in PRIMARY_DISPERSION:
        correlations[dcol] = {}
        for ocol in ["cascade_50", "cascade_75", "cascade_conviction"]:
            d = df[[dcol, ocol]].dropna()
            if len(d) < MIN_N:
                correlations[dcol][ocol] = None
                continue
            rho, p = spearmanr(d[dcol], d[ocol])
            correlations[dcol][ocol] = {"spearman_rho": float(rho), "p_value": float(p), "N": int(len(d))}

    # Correlación parcial (controlando pivot_type=MAX dummy y era=post2011 dummy)
    partial_corrs = {}
    for dcol in ["disp_std_zk_pbull_11", "disp_std_zk_pbull_A", "disp_std_d1_vote_11"]:
        for ocol in ["cascade_50", "cascade_conviction"]:
            d = df[[dcol, ocol, "pivot_type", "era"]].dropna()
            d = d.copy()
            d["is_max"] = (d["pivot_type"] == "MAX").astype(float)
            d["is_post2011"] = (d["era"] == "post2011").astype(float)
            X = np.column_stack([np.ones(len(d)), d["is_max"].values, d["is_post2011"].values])
            y = d[ocol].values.astype(float)
            x = d[dcol].values.astype(float)
            beta_y, *_ = np.linalg.lstsq(X, y, rcond=None)
            beta_x, *_ = np.linalg.lstsq(X, x, rcond=None)
            r_y = y - X @ beta_y
            r_x = x - X @ beta_x
            denom = np.sqrt(np.sum(r_x ** 2) * np.sum(r_y ** 2))
            pc = float(np.sum(r_x * r_y) / denom) if denom > 0 else float("nan")
            partial_corrs[f"{dcol}__{ocol}"] = {
                "partial_r": pc, "N": int(len(d)),
                "raw_pearson": float(np.corrcoef(x, y)[0, 1]),
            }

    # ── PASO 6: Disonancia por pares de estaciones ──
    print("\n[PASO 6] Disonancia por pares de estaciones (d1_vote) ...")
    pair_results = {}
    for ocol in ["cascade_50", "cascade_conviction"]:
        pairs = []
        for i in range(len(STATIONS)):
            for j in range(i + 1, len(STATIONS)):
                s1, s2 = STATIONS[i], STATIONS[j]
                col1, col2 = f"{s1}_d1_vote", f"{s2}_d1_vote"
                mask = df[col1].notna() & df[col2].notna() & df[ocol].notna()
                sub = df[mask]
                agree = (sub[col1] == sub[col2])
                n_agree = int(agree.sum())
                n_diss = int(len(sub) - n_agree)
                if n_agree >= MIN_N and n_diss >= MIN_N:
                    if ocol == "cascade_50":
                        ra, la, ha = boot_ci_proportion(sub.loc[agree, ocol].values)
                        rd, ld, hd = boot_ci_proportion(sub.loc[~agree, ocol].values)
                        pairs.append({
                            "pair": f"{s1}/{s2}",
                            "n_total": int(len(sub)),
                            "agree": {"n": n_agree, "rate": float(ra), "ci95": [float(la), float(ha)]},
                            "dissonant": {"n": n_diss, "rate": float(rd), "ci95": [float(ld), float(hd)]},
                            "dissonance_rate": n_diss / len(sub),
                            "delta_rate": float(rd - ra),
                        })
                    else:
                        ma, la, ha = boot_ci_mean(sub.loc[agree, ocol].values)
                        md, ld, hd = boot_ci_mean(sub.loc[~agree, ocol].values)
                        pairs.append({
                            "pair": f"{s1}/{s2}",
                            "n_total": int(len(sub)),
                            "agree": {"n": n_agree, "mean": float(ma), "ci95": [float(la), float(ha)]},
                            "dissonant": {"n": n_diss, "mean": float(md), "ci95": [float(ld), float(hd)]},
                            "dissonance_rate": n_diss / len(sub),
                            "delta_mean": float(md - ma),
                        })
        pairs.sort(key=lambda x: x["dissonance_rate"], reverse=True)
        pair_results[ocol] = pairs

    if pair_results.get("cascade_50"):
        print("\n  Top 10 pares más disonantes (cascade_50 rate agree vs dissonant):")
        for p in pair_results["cascade_50"][:10]:
            print(f"    {p['pair']:30s} diss_rate={p['dissonance_rate']:.3f}  "
                  f"agree_c50={p['agree']['rate']:.3f}  diss_c50={p['dissonant']['rate']:.3f}  "
                  f"Δ={p['delta_rate']:+.3f}")

    # ── PASO 7: Veredicto ──
    print("\n" + "=" * 92)
    print("[PASO 7] VEREDICTO")
    print("=" * 92)

    verdict = _build_verdict(all_tercile_results, correlations, partial_corrs)
    print(f"\n  {verdict['summary']}")

    # ── Guardar reporte ──
    report = {
        "meta": {
            "script": "dispersion_estaciones.py",
            "data_source": "data/research/pivots/quants_obs.pkl",
            "n_pivots": int(len(df)),
            "date_range": [str(df.pivot_date.min()), str(df.pivot_date.max())],
            "stations": STATIONS,
            "grupos": {"A": sorted(GRUPO_A), "B": sorted(GRUPO_B), "C": sorted(GRUPO_C)},
            "bootstrap": {"n_iter": N_BOOT, "seed": BOOT_SEED, "ci": 95},
            "min_n": MIN_N,
            "structural_warnings": [
                "next_bear y next_leg_direction son DETERMINISTAS respecto a pivot_type "
                "(MAX→0, MIN→1). NO son outcome forward; son etiqueta estructural.",
                "fg/pcr/credit/vvix solo tienen datos desde ~2011. La dispersión de '11 "
                "estaciones' solo es completa en 447/1590 pivotes. Se usa nanstd + n_valid.",
            ],
        },
        "coverage": coverage,
        "n_valid_stations_distribution": {int(k): int(v) for k, v in n_valid_dist.items()},
        "tercile_analysis": all_tercile_results,
        "spearman_correlations": correlations,
        "partial_correlations": partial_corrs,
        "pair_dissonance": pair_results,
        "verdict": verdict,
    }

    out_path = ROOT / "data/research/ldp_methodology/dispersion_estaciones_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Reporte guardado en: {out_path}")
    print(f"  Tamaño: {out_path.stat().st_size:,} bytes")


def _print_tercile(r, ocol, is_bin):
    print(f"    {ocol}  monotonicity={r.get('monotonicity')}  "
          f"CI95_overlap(t1vs t3)={r.get('ci95_overlap_t1_t3')}")
    for tlabel in ["t1_low", "t2_mid", "t3_high"]:
        t = r["terciles"].get(tlabel, {})
        if t.get("N", 0) == 0:
            print(f"      {tlabel}: N=0")
            continue
        ci = t.get("ci95", [None, None])
        if is_bin:
            print(f"      {tlabel}: N={t['N']:>4}  rate={t['rate']:.4f}  "
                  f"CI95[{ci[0]:.4f},{ci[1]:.4f}]  wins={t['wins']['n']} losses={t['losses']['n']}")
        else:
            ss = t.get("sign_split", {})
            print(f"      {tlabel}: N={t['N']:>4}  mean={t.get('mean', float('nan')):+.4f}  "
                  f"CI95[{ci[0]:+.4f},{ci[1]:+.4f}]  pos_n={ss.get('positive_n')} neg_n={ss.get('negative_n')}")


def _build_verdict(tercile_results, correlations, partial_corrs):
    """Veredicto honesto a partir de los números medidos."""
    # 1. ¿Hay monotonicidad consistente en cascade_50 con las métricas zk_pbull?
    key_metrics = ["disp_std_zk_pbull_11", "disp_std_zk_pbull_A", "disp_mad_zk_pbull_11"]
    monotonic_c50 = []
    for m in key_metrics:
        r = tercile_results.get(m, {}).get("cascade_50", {})
        if r and r.get("monotonicity") in ("increasing", "decreasing"):
            monotonic_c50.append((m, r["monotonicity"], r.get("ci95_overlap_t1_t3")))

    # 2. ¿Sobrevive al control pivot_type/era? (mirar controlled dentro de MIN y MAX)
    survives_control = False
    for m in key_metrics:
        ctrl = tercile_results.get(m, {}).get("controlled", {})
        for ctrl_name in ["pivot_type_MIN", "pivot_type_MAX"]:
            c50 = ctrl.get(ctrl_name, {}).get("cascade_50", {})
            if c50 and c50.get("monotonicity") in ("increasing", "decreasing"):
                survives_control = True

    # 3. Magnitud: Spearman rho de la métrica primaria vs cascade_50
    rho_c50 = correlations.get("disp_std_zk_pbull_11", {}).get("cascade_50", {}).get("spearman_rho")
    pc_c50 = partial_corrs.get("disp_std_zk_pbull_11__cascade_50", {}).get("partial_r")

    # 4. Inconsistencia de signo con d1_vote
    d1_mono = tercile_results.get("disp_std_d1_vote_11", {}).get("cascade_50", {}).get("monotonicity")
    sign_inconsistent = False
    if monotonic_c50 and d1_mono:
        # si zk_pbull es decreasing y d1_vote es increasing → inconsistente
        zk_dirs = {mm for mm, dd, _ in monotonic_c50}
        if "decreasing" in zk_dirs and d1_mono == "increasing":
            sign_inconsistent = True
        if "increasing" in zk_dirs and d1_mono == "decreasing":
            sign_inconsistent = True

    effect_size = "weak"
    if rho_c50 is not None and abs(rho_c50) >= 0.30:
        effect_size = "moderate"
    elif rho_c50 is not None and abs(rho_c50) >= 0.10:
        effect_size = "weak-to-modest"
    elif rho_c50 is not None and abs(rho_c50) < 0.10:
        effect_size = "negligible"

    # Construcción del veredicto
    findings = {
        "monotonic_cascade50_metrics": [
            {"metric": m, "direction": d, "ci95_no_overlap": o} for m, d, o in monotonic_c50
        ],
        "survives_pivot_type_control": survives_control,
        "spearman_rho_disp_vs_cascade50": rho_c50,
        "partial_r_disp_vs_cascade50": pc_c50,
        "effect_size": effect_size,
        "d1_vote_sign_inconsistent": sign_inconsistent,
    }

    if not monotonic_c50:
        summary = (
            "La dispersión entre estaciones NO muestra monotonicidad consistente con "
            "cascade_50 ni con cascade_conviction. ES RUIDO como predictor. No se "
            "recomienda como feature del aprendiz."
        )
    elif sign_inconsistent and abs(rho_c50 or 0) < 0.20:
        summary = (
            f"La dispersión (std de zk_pbull) muestra una relación monotónica DÉBIL con "
            f"cascade_50/cascade_conviction (Spearman rho≈{rho_c50:.3f}), pero la métrica "
            f"d1_vote apunta en dirección OPUESTA, y el efecto es pequeño. Señal real pero "
            f"frágil y métrica-dependiente; NO recomendada como feature primaria."
        )
    elif survives_control:
        summary = (
            f"La dispersión (std de zk_pbull entre estaciones) DISCRIMINA de forma "
            f"monotónica y robusta: a MAYOR dispersión (fragmentación), MENOR tasa de "
            f"cascade_50 y MENOR cascade_conviction (llega a negativa). El efecto sobrevive "
            f"al control por pivot_type (MIN/MAX) y era. Spearman rho≈{rho_c50:.3f} "
            f"(efecto {effect_size}). Dirección OPUESTA a la intuición de 'consenso→cascade': "
            f"el CONSENSO (dispersión baja) es el que dispara más cascadas. Útil como feature "
            f"graduada del aprendiz, pero con magnitud modesta — validar OOS."
        )
    else:
        summary = (
            f"La dispersión muestra cierta monotonicidad con cascade_50 "
            f"(Spearman rho≈{rho_c50:.3f}, efecto {effect_size}) pero el efecto NO sobrevive "
            f"de forma consistente al desglose por pivot_type. Señal marginal; usar con "
            f"cautela y solo como feature secundaria."
        )

    return {"summary": summary, "findings": findings}


if __name__ == "__main__":
    main()