#!/usr/bin/env python3
"""
CASCADE ADD-ONE-IN — ¿YIELD_CURVE y DXY tienen valor independiente en cascade_conviction?
========================================================================================
Mide si AÑADIR yield_curve y dxy al Grupo A (d1_bear_5) mejora el IC del cascade_conviction
contra cascade_50. Replica la fórmula validada y compara 4 configuraciones.

Fórmula (referencia: decay_check_cascade_conviction.py + cascade_calibration.json):
    d1_bear_5 = conteo FRACCIONAL de votos bearish del Grupo A (type-mask MIN/MAX)
    z_bear    = (d1_bear_5 - mean) / std          mean=0.41, std=0.3206
    z_dom     = (abs_prev_leg_return - 0.0532)/0.035
    cascade_conviction = 0.66 * z_bear + 0.34 * z_dom
    IC = Spearman(cascade_conviction, cascade_50)

Configuraciones (type-mask: FG es MIN-only, se mantiene FIJA en las 4):
    base            MIN={vix,bsi,fg,credit,rotation}          MAX={vix,bsi,credit,rotation}
    plus_yield_curve  añade yield_curve a MIN y MAX
    plus_dxy          añade dxy       a MIN y MAX
    plus_both         añade ambas     a MIN y MAX

DATOS: data/research/pivots/quants_obs.pkl (1,590 pivotes zz25). CI95 bootstrap 3000 (seed 42), ΔIC pareado.
"""
import json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

BASE = "/root/botero-trade"
PKL = f"{BASE}/data/research/pivots/quants_obs.pkl"
CAL = f"{BASE}/backend/modules/entry_decision/domain/rules/cascade_calibration.json"
OUT = f"{BASE}/data/research/cascade/cascade_add_one_in_report.json"

RNG_SEED = 42
N_BOOT = 3000


def load_calibration():
    with open(CAL, "r", encoding="utf-8") as f:
        return json.load(f)


def frac_bear(df, stations):
    """Conteo FRACCIONAL de votos bearish: sum(-v para v<0) / nº de votos válidos (no-NaN).
    -1.0 cuenta 1.0, -0.5 cuenta 0.5, 0.0/bullish no suman al numerador pero SÍ al denominador.
    NaN (estación sin dato en ese pivote) queda FUERA del denominador."""
    v = df[[f"{s}_d1_vote" for s in stations]].astype(float).values
    num = np.where(v < 0, -v, 0.0).sum(axis=1)
    den = (~np.isnan(v)).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den > 0, num / den, np.nan)
    return out


def conviction(df, d1, cal):
    zb = (d1 - cal["d1_bear_5"]["mean"]) / cal["d1_bear_5"]["std"]
    zd = (df["abs_prev_leg_return"].astype(float).values - cal["domino_zz25"]["mean"]) / cal["domino_zz25"]["std"]
    wb = cal["type_mask"]["MIN"]["w_bear"]
    wd = cal["type_mask"]["MIN"]["w_dom"]
    return wb * zb + wd * zd


def ic(score, target):
    m = ~np.isnan(score) & ~np.isnan(target)
    s, t = score[m], target[m]
    if len(s) < 5 or np.std(s) == 0 or np.std(t) == 0:
        return np.nan, m.sum()
    return float(spearmanr(s, t)[0]), int(m.sum())


def bootstrap_ic_ci(score, target, n=N_BOOT, seed=RNG_SEED):
    """CI95 percentil del IC, remuestreando filas con reposición."""
    rng = np.random.default_rng(seed)
    m = ~np.isnan(score) & ~np.isnan(target)
    s, t = score[m], target[m]
    N = len(s)
    ics = np.empty(n)
    for i in range(n):
        idx = rng.integers(0, N, N)
        r = spearmanr(s[idx], t[idx])[0]
        ics[i] = 0.0 if np.isnan(r) else r
    return float(np.percentile(ics, 2.5)), float(np.percentile(ics, 97.5)), ics


def paired_delta(score_base, score_cfg, target, n=N_BOOT, seed=RNG_SEED):
    """Bootstrap PAREADO: mismo remuestreo para base y cfg, ΔIC = IC_cfg - IC_base."""
    rng = np.random.default_rng(seed)
    m = ~np.isnan(score_base) & ~np.isnan(score_cfg) & ~np.isnan(target)
    sb, sc, t = score_base[m], score_cfg[m], target[m]
    N = len(sb)
    deltas = np.empty(n)
    for i in range(n):
        idx = rng.integers(0, N, N)
        rb = spearmanr(sb[idx], t[idx])[0]
        rc = spearmanr(sc[idx], t[idx])[0]
        rb = 0.0 if np.isnan(rb) else rb
        rc = 0.0 if np.isnan(rc) else rc
        deltas[i] = rc - rb
    lo, hi = float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))
    return lo, hi, deltas


def main():
    cal = load_calibration()
    df = pd.read_pickle(PKL)

    target = df["cascade_50"].astype(float).values
    is_max = (df["pivot_type"] == "MAX").values

    GRUPO_A = ["vix", "bsi", "fg", "credit", "rotation"]
    MIN_BASE = list(GRUPO_A)
    MAX_BASE = ["vix", "bsi", "credit", "rotation"]

    configs = {
        "base": {"min": MIN_BASE, "max": MAX_BASE, "n_label": 5},
        "plus_yield_curve": {"min": MIN_BASE + ["yield_curve"], "max": MAX_BASE + ["yield_curve"], "n_label": 6},
        "plus_dxy": {"min": MIN_BASE + ["dxy"], "max": MAX_BASE + ["dxy"], "n_label": 6},
        "plus_both": {"min": MIN_BASE + ["yield_curve", "dxy"], "max": MAX_BASE + ["yield_curve", "dxy"], "n_label": 7},
    }

    # --- scores por configuración ---
    scores = {}
    d1s = {}
    for name, cfg in configs.items():
        d1_min = frac_bear(df, cfg["min"])
        d1_max = frac_bear(df, cfg["max"])
        d1 = np.where(is_max, d1_max, d1_min)
        d1s[name] = d1
        scores[name] = conviction(df, d1, cal)

    # --- IC base + CI95 por configuración ---
    results = {}
    for name in configs:
        ic_val, n_valid = ic(scores[name], target)
        lo, hi, _ = bootstrap_ic_ci(scores[name], target)
        results[name] = {
            "ic": round(ic_val, 4),
            "ci95": [round(lo, 4), round(hi, 4)],
            "n_valid": n_valid,
            "stations_min": configs[name]["min"],
            "stations_max": configs[name]["max"],
            "n_stations_label": configs[name]["n_label"],
        }

    # --- ΔIC pareado vs base ---
    deltas = {}
    base_score = scores["base"]
    for name in configs:
        if name == "base":
            continue
        lo, hi, d = paired_delta(base_score, scores[name], target)
        frac_gt0 = float((d > 0).mean())
        frac_lt0 = float((d < 0).mean())
        deltas[name] = {
            "delta_ic_vs_base": round(float(np.mean(d)), 4),
            "ci95": [round(lo, 4), round(hi, 4)],
            "frac_boot_gt0": round(frac_gt0, 4),
            "frac_boot_lt0": round(frac_lt0, 4),
        }

    # --- descomposición MIN vs MAX (IC dentro de cada pivot_type) ---
    by_type = {}
    for name in configs:
        by_type[name] = {}
        for pt in ["MIN", "MAX"]:
            m = (df["pivot_type"].values == pt)
            ic_val, n_valid = ic(scores[name][m], target[m])
            by_type[name][pt] = {"ic": round(ic_val, 4), "n": int(n_valid)}

    # --- contexto: IC standalone de yield_curve / dxy y redundancia con d1_bear_5 ---
    context = {}
    for s in ["yield_curve", "dxy"]:
        v = df[f"{s}_d1_vote"].astype(float).values
        ic_val, n_valid = ic(v, target)
        r_with_base = float(spearmanr(v[~np.isnan(v)], d1s["base"][~np.isnan(v)])[0])
        context[s] = {
            "standalone_ic_vs_cascade_50": round(ic_val, 4),
            "n_covered": int(n_valid),
            "spearman_vs_base_d1_bear_5": round(r_with_base, 4),
        }

    # --- variante robustez: Grupo A uniforme SIN type-mask (5/6/6/7 siempre) ---
    robust = {}
    uniform = {
        "base": GRUPO_A,
        "plus_yield_curve": GRUPO_A + ["yield_curve"],
        "plus_dxy": GRUPO_A + ["dxy"],
        "plus_both": GRUPO_A + ["yield_curve", "dxy"],
    }
    for name, st in uniform.items():
        d1 = frac_bear(df, st)
        cc = conviction(df, d1, cal)
        ic_val, n_valid = ic(cc, target)
        lo, hi, _ = bootstrap_ic_ci(cc, target)
        robust[name] = {"ic": round(ic_val, 4), "ci95": [round(lo, 4), round(hi, 4)], "n": int(n_valid)}

    # --- veredicto ---
    def verdict_text(name):
        d = deltas.get(name)
        if d is None:
            return "baseline"
        delta = d["delta_ic_vs_base"]
        lo, hi = d["ci95"]
        if lo > 0 and hi > 0:
            return "mejora significativa (CI95 todo > 0) -> valor independiente, añadir"
        if hi < 0 and lo < 0:
            return "degrada significativa (CI95 todo < 0) -> añade ruido, excluir"
        return "no significativo (CI95 cruza 0) -> redundante / sin valor marginal"

    report = {
        "_meta": {
            "task": "cascade_add_one_in",
            "question": "¿AÑADIR yield_curve y dxy al Grupo A mejora el IC del cascade_conviction vs cascade_50?",
            "data": "data/research/pivots/quants_obs.pkl (1,590 pivotes zz25)",
            "formula": "cascade_conviction = 0.66*(d1_bear_5-0.41)/0.3206 + 0.34*(abs_prev_leg_return-0.0532)/0.035",
            "weights": {"w_bear": 0.66, "w_dom": 0.34},
            "calibration": {"d1_bear_5_mean": 0.41, "d1_bear_5_std": 0.3206, "domino_zz25_mean": 0.0532, "domino_zz25_std": 0.035},
            "counting": "FRACCIONAL (type-mask MIN/MAX; FG MIN-only)",
            "bootstrap": {"n_iter": N_BOOT, "seed": RNG_SEED},
            "baseline_documented": 0.4155,
            "note": "z_bear usa calibración FIJA del Grupo A base (0.41/0.3206); no se re-estandariza al añadir estaciones.",
        },
        "baseline_replication": {
            "ic": results["base"]["ic"],
            "ci95": results["base"]["ci95"],
            "n_valid": results["base"]["n_valid"],
        },
        "configs": results,
        "delta_ic_vs_base": deltas,
        "verdicts": {name: verdict_text(name) for name in configs},
        "by_pivot_type": by_type,
        "context": context,
        "robustness_no_type_mask": robust,
        "conclusion": None,
    }

    # conclusión textual
    best = max((k for k in configs if k != "base"), key=lambda k: deltas[k]["delta_ic_vs_base"])
    report["conclusion"] = {
        "base_ic": results["base"]["ic"],
        "best_additive": best,
        "best_delta": deltas[best]["delta_ic_vs_base"],
        "verdict": verdict_text(best),
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # --- salida consola ---
    print("=" * 100)
    print("CASCADE ADD-ONE-IN  (IC vs cascade_50, Spearman)")
    print("=" * 100)
    print(f"Base (type-mask) IC = {results['base']['ic']:+.4f}  CI95 {results['base']['ci95']}  N={results['base']['n_valid']}")
    print(f"  (documentado baseline = +0.4155)")
    print()
    print(f"{'config':22s} {'IC':>8s} {'CI95':>20s} {'delta vs base':>14s} {'delta CI95':>20s}  veredicto")
    for name in configs:
        r = results[name]
        ic_s = f"{r['ic']:+.4f}"
        ci_s = f"[{r['ci95'][0]:+.4f},{r['ci95'][1]:+.4f}]"
        if name == "base":
            print(f"{name:22s} {ic_s:>8s} {ci_s:>20s} {'-':>14s} {'-':>20s}  baseline")
        else:
            d = deltas[name]
            d_s = f"{d['delta_ic_vs_base']:+.4f}"
            dci = f"[{d['ci95'][0]:+.4f},{d['ci95'][1]:+.4f}]"
            print(f"{name:22s} {ic_s:>8s} {ci_s:>20s} {d_s:>14s} {dci:>20s}  {verdict_text(name)}")
    print()
    print("MIN / MAX:")
    for name in configs:
        print(f"  {name:22s}  MIN IC={by_type[name]['MIN']['ic']:+.4f} (N={by_type[name]['MIN']['n']})  "
              f"MAX IC={by_type[name]['MAX']['ic']:+.4f} (N={by_type[name]['MAX']['n']})")
    print()
    print("Contexto (standalone + redundancia con d1_bear_5 base):")
    for s, c in context.items():
        print(f"  {s:14s} standalone IC={c['standalone_ic_vs_cascade_50']:+.4f} (N={c['n_covered']})  "
              f"rho vs base d1_bear_5 = {c['spearman_vs_base_d1_bear_5']:+.4f}")
    print()
    print("Robustez (Grupo A uniforme, SIN type-mask):")
    for name, r in robust.items():
        print(f"  {name:22s} IC={r['ic']:+.4f}  CI95 {r['ci95']}  N={r['n']}")
    print()
    print(f"Reporte escrito en: {OUT}")


if __name__ == "__main__":
    main()
