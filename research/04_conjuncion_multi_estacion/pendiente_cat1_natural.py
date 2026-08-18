#!/usr/bin/env python
"""
pendiente_cat1_natural.py
=========================

Mide el PERÍODO NATURAL de las estaciones LENTAS (CAT1 economía) para definir
operativamente la "activación" de régimen.

Para CADA estación de CAT1 (CREDIT, YIELD, DXY, ROTATION):
  1. Autocorrelación del valor raw -> half-life (lag donde la ACF cruza 0.5 por
     primera vez). Reportado en pivotes Y en días (vía mediana de espaciamiento
     entre pivotes = 4.0 días).
  2. Pendiente en esa ventana natural: (val[t] - val[t-W]) / span_días[t].
  3. Tendencia de SPY en la MISMA ventana (misma longitud W en pivotes): suma
     acumulada de prev_leg_return sobre los W pivotes que terminan en t.
     (No existe serie diaria de SPY en quants_obs.pkl; la suma de prev_leg_return
     sobre piernas consecutivas es el retorno EXACTO de SPY en esa ventana, porque
     las piernas teselan el camino del precio.)
  4. Correlación pendiente-estación vs tendencia-SPY (Spearman + Pearson),
     CI95 bootstrap 3000 (seed 42), descomposición por pivot_type (MIN vs MAX).
  5. Veredicto: ¿la pendiente en ventana natural predice? Comparación contra
     ventanas fijas (1/2/5/10/15/20/30/40/60 pivotes ≈ 4/8/20/40/60/80/120/160/240 días).

IMPORTANTE METODOLÓGICO
-----------------------
* Los datos son PIVOTES zigzag (no series diarias): la autocorrelación y la
  pendiente se miden en LAGS DE PIVOTE. La conversión a "días" es interpretativa
  (mediana de espaciamiento = 4.0 días/pivote). Se reporta AMBAS.
* La ACF del valor RAW de variables macro NO-estacionarias (credit/yield/dxy
  tienen tendencias seculares) puede estar inflada por la tendencia, no por
  mean-reversion. Se corre un test ADF y se reporta el caveat.
* prev_leg_return NO es 100% estructural con pivot_type (81.3% de coincidencia de
  signo): tiene varianza real y es un retorno medible válido de SPY.
* "Predice" se mide en dos formas:
    (A) CONTEMPORÁNEA: pendiente[t-W..t] vs tendencia-SPY[t-W..t] (misma ventana).
    (B) PREDICTIVA/LEAD: pendiente[t-W..t] vs tendencia-SPY[t..t+W] (ventana forward).
  El veredicto principal usa (B); (A) es la asociación co-movida.

Solo CAT1, solo estas 4 estaciones.
"""

import json
import os

import numpy as np
import pandas as pd
from scipy import stats

# ----------------------------------------------------------------------------
# Configuración
# ----------------------------------------------------------------------------
DATA = os.path.join(os.path.dirname(__file__), "quants_obs.pkl")
REPORT = os.path.join(os.path.dirname(__file__), "pendiente_cat1_natural_report.json")

CAT1_STATIONS = ["credit", "yield_curve", "dxy", "rotation"]

N_BOOT = 3000
SEED = 42
MAX_LAG = 300          # lags de pivote máximos para la ACF
FIXED_WINDOWS = [1, 2, 5, 10, 15, 20, 30, 40, 60]   # en pivotes

rng = np.random.default_rng(SEED)


# ----------------------------------------------------------------------------
# Utilidades estadísticas
# ----------------------------------------------------------------------------
def acf_series(values, max_lag):
    """ACF (Pearson) del vector `values` para lags 1..max_lag, ignorando NaN
    por pares. Devuelve dict {lag: rho}. `values` es un np.array 1D (puede tener
    NaN)."""
    values = np.asarray(values, dtype=float)
    n = len(values)
    out = {}
    for lag in range(1, min(max_lag, n) + 1):
        v0 = values[:-lag]
        v1 = values[lag:]
        mask = ~(np.isnan(v0) | np.isnan(v1))
        if mask.sum() < 10:
            continue
        a, b = v0[mask], v1[mask]
        if np.std(a) == 0 or np.std(b) == 0:
            out[lag] = 1.0 if np.array_equal(a, b) else 0.0
            continue
        r, _ = stats.pearsonr(a, b)
        out[lag] = float(r)
    return out


def half_life(acf_dict):
    """Primer lag donde la ACF cruza 0.5 (cae por debajo). Interpola linealmente
    para el cruce fraccional. Devuelve (hl_pivots_float, crossed_bool, lag_hi, lag_lo)."""
    lags = sorted(acf_dict.keys())
    if not lags:
        return None, False, None, None
    # Encontrar primer lag donde rho < 0.5
    for i, lag in enumerate(lags):
        if acf_dict[lag] < 0.5:
            if i == 0:
                return float(lag), True, lag, lag
            prev_lag = lags[i - 1]
            prev_rho = acf_dict[prev_lag]
            rho_hi = acf_dict[lag]
            # interpolación lineal del cruce
            if prev_rho - rho_hi != 0:
                frac = (prev_rho - 0.5) / (prev_rho - rho_hi)
                hl = prev_lag + frac * (lag - prev_lag)
            else:
                hl = float(lag)
            return hl, True, lag, prev_lag
    # nunca cruza dentro de max_lag
    return float(lags[-1]), False, None, lags[-1]


def _fast_corr(x, y):
    """Pearson entre dos arrays 1D (sin NaN). Devuelve float."""
    xm = x - x.mean()
    ym = y - y.mean()
    denom = np.sqrt((xm * xm).sum() * (ym * ym).sum())
    if denom == 0:
        return 0.0
    return float((xm * ym).sum() / denom)


def bootstrap_corr(x, y, method="spearman", n_boot=N_BOOT, seed=SEED):
    """CI95 bootstrap de la correlación Spearman/Pearson sobre pares (x,y) no-NaN.
    Vectorizado (rápido). Devuelve dict {rho, ci_lo, ci_hi, n, p_leq0, p_ge0}.

    Spearman = Pearson sobre ranks (equivale a scipy.stats.spearmanr con empates
    en rango promedio)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 2:
        return {"rho": None, "ci_lo": None, "ci_hi": None, "n": n,
                "p_leq0": None, "p_ge0": None}

    if method == "spearman":
        x = stats.rankdata(x)
        y = stats.rankdata(y)

    rho = _fast_corr(x, y)

    rng_boot = np.random.default_rng(seed)
    idx = rng_boot.integers(0, n, size=(n_boot, n))
    xs = x[idx]          # (n_boot, n)
    ys = y[idx]
    xm = xs - xs.mean(axis=1, keepdims=True)
    ym = ys - ys.mean(axis=1, keepdims=True)
    num = (xm * ym).sum(axis=1)
    den = np.sqrt((xm * xm).sum(axis=1) * (ym * ym).sum(axis=1))
    boot = np.where(den > 0, num / np.where(den > 0, den, 1.0), 0.0)

    ci_lo, ci_hi = float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))
    p_leq0 = float((boot <= 0).mean())
    p_ge0 = float((boot >= 0).mean())
    return {"rho": rho, "ci_lo": ci_lo, "ci_hi": ci_hi, "n": n,
            "p_leq0": p_leq0, "p_ge0": p_ge0}


def adf_test(values):
    """Augmented Dickey-Fuller sobre el segmento válido contiguo."""
    v = pd.Series(values).dropna().values
    if len(v) < 20:
        return None
    try:
        from statsmodels.tsa.stattools import adfuller
        res = adfuller(v, autolag="AIC")
        return {"adf_stat": float(res[0]), "p_value": float(res[1]),
                "stationary_at_5pct": bool(res[1] < 0.05)}
    except Exception:
        return None


# ----------------------------------------------------------------------------
# Carga de datos
# ----------------------------------------------------------------------------
def load_data():
    df = pd.read_pickle(DATA)
    df = df.copy()
    df["date"] = pd.to_datetime(df["pivot_date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


# ----------------------------------------------------------------------------
# Análisis por estación
# ----------------------------------------------------------------------------
def analyze_station(df, station):
    val_col = f"{station}_val"
    out = {"station": station, "value_column": val_col}

    # ---- Serie de valor y espaciamiento ------------------------------------
    val = df[val_col].values
    n_total = len(val)
    n_valid = int(np.sum(~np.isnan(val)))
    n_nan = n_total - n_valid
    out["n_total"] = n_total
    out["n_valid"] = n_valid
    out["n_nan"] = n_nan

    # ---- PASO 2: ACF + half-life ------------------------------------------
    acf = acf_series(val, MAX_LAG)
    hl_pivots, crossed, _, _ = half_life(acf)
    out["acf_max_lag"] = MAX_LAG
    out["acf_at"] = {str(k): acf[k] for k in sorted(acf) if k in
                     [1, 2, 3, 5, 10, 20, 40, 80, 120, 160, 200, 240, 300]}
    out["half_life_pivots"] = round(hl_pivots, 2) if hl_pivots else None
    out["half_life_crossed_0p5"] = crossed
    out["half_life_days"] = round(hl_pivots * 4.0, 1) if hl_pivots else None
    out["adf"] = adf_test(val)

    W = int(round(hl_pivots)) if hl_pivots else None
    out["natural_window_pivots"] = W
    out["natural_window_days"] = round(W * 4.0, 1) if W else None

    if W is None or W < 1:
        out["error"] = "half-life no computable"
        return out

    # ---- PASO 3: pendiente en ventana natural -----------------------------
    val_s = pd.Series(val)
    date_s = df["date"]
    # diff en valor sobre W pivotes
    diff_val = val_s - val_s.shift(W)
    # span real en días entre t y t-W
    span_days = (date_s - date_s.shift(W)).dt.days
    slope_per_day = diff_val / span_days.replace(0, np.nan)   # tasa/día
    slope_raw = diff_val                                        # diff total (escala-invariante p/ correl)

    # ---- PASO 4: tendencia SPY en la MISMA ventana ------------------------
    prev_ret = df["prev_leg_return"].values
    # Backward: sum_{k=i-W+1..i} = rolling(W).sum()
    spy_trend_same = pd.Series(prev_ret).rolling(W, min_periods=W).sum().values
    # Forward: sum_{k=i+1..i+W} = rolling[i+W] - rolling[i]
    # (rolling son W elementos; rolling[i+W] cubre [i+1..i+W])
    rolling_sum = pd.Series(prev_ret).rolling(W, min_periods=W).sum()
    rolling_shifted = rolling_sum.shift(-W)
    spy_trend_fwd = (rolling_shifted - rolling_sum).values

    out["slope_stats"] = {
        "slope_per_day_mean": float(np.nanmean(slope_per_day)),
        "slope_per_day_std": float(np.nanstd(slope_per_day)),
        "n_slopes": int(np.sum(~np.isnan(slope_raw))),
    }

    # ---- PASO 5: correlación ----------------------------------------------
    out["contemporanea"] = {
        "spearman": bootstrap_corr(slope_raw, spy_trend_same, "spearman"),
        "pearson": bootstrap_corr(slope_raw, spy_trend_same, "pearson"),
    }
    out["predictiva_lead"] = {
        "spearman": bootstrap_corr(slope_raw, spy_trend_fwd, "spearman"),
        "pearson": bootstrap_corr(slope_raw, spy_trend_fwd, "pearson"),
    }

    # descomposición por pivot_type
    out["por_pivot_type"] = {}
    for ptype in ["MIN", "MAX"]:
        m = (df["pivot_type"] == ptype).values
        out["por_pivot_type"][ptype] = {
            "contemporanea_spearman": bootstrap_corr(slope_raw[m], spy_trend_same[m], "spearman"),
            "predictiva_spearman": bootstrap_corr(slope_raw[m], spy_trend_fwd[m], "spearman"),
        }

    # ---- PASO 6: comparación con ventanas fijas ---------------------------
    fixed = {}
    for fw in FIXED_WINDOWS:
        if fw >= len(val):
            continue
        d_fw = (val_s - val_s.shift(fw)).values
        s_fw = pd.Series(prev_ret).rolling(fw, min_periods=fw).sum().values
        rolling_fw = pd.Series(prev_ret).rolling(fw, min_periods=fw).sum()
        s_fwd = (rolling_fw.shift(-fw) - rolling_fw).values
        fixed[str(fw)] = {
            "dias_equiv": round(fw * 4.0, 1),
            "contemporanea_spearman": bootstrap_corr(d_fw, s_fw, "spearman"),
            "predictiva_spearman": bootstrap_corr(d_fw, s_fwd, "spearman"),
        }
    out["ventanas_fijas"] = fixed

    # ---- VEREDICTO --------------------------------------------------------
    out["veredicto"] = build_verdict(out)

    # Exponer los arrays raw para el análisis de asimetría direccional
    out["_slope_raw"] = slope_raw
    out["_spy_trend_fwd"] = spy_trend_fwd

    return out


def build_verdict(out):
    pred = out["predictiva_lead"]["spearman"]
    cont = out["contemporanea"]["spearman"]
    n = pred.get("n")

    verdict = {"station": out["station"],
               "half_life_pivots": out["half_life_pivots"],
               "half_life_days": out["half_life_days"],
               "natural_window_pivots": out["natural_window_pivots"]}

    if n is None or n < 20:
        verdict["decision"] = "INSUFICIENTE"
        verdict["razon"] = f"N={n} < 20 mínimo"
        verdict["fuerza"] = None
        verdict["direccion"] = None
        return verdict

    rho = pred["rho"]
    ci_lo, ci_hi = pred["ci_lo"], pred["ci_hi"]
    p_leq0, p_ge0 = pred["p_leq0"], pred["p_ge0"]
    abs_rho = abs(rho)

    # fuerza
    if abs_rho >= 0.30:
        fuerza = "FUERTE"
    elif abs_rho >= 0.15:
        fuerza = "MODERADA"
    elif abs_rho >= 0.05:
        fuerza = "DÉBIL"
    else:
        fuerza = "MARGINAL"

    # ¿predictivo? CI95 no cruza cero + fuerza >= MODERADA (|rho| >= 0.15)
    crosses_zero = (ci_lo <= 0 <= ci_hi)

    if crosses_zero:
        verdict["decision"] = "NO_PREDICTIVA"
        verdict["razon"] = (f"CI95 bootstrap [{ci_lo:.3f}, {ci_hi:.3f}] cruza cero "
                            f"(rho={rho:.3f}, N={n})")
        if fuerza == "MARGINAL":
            verdict["razon"] += " — fuerza marginal (|rho|<0.05, ruido)"
    elif fuerza in ("DÉBIL", "MARGINAL"):
        verdict["decision"] = "NO_PREDICTIVA"
        verdict["razon"] = (f"CI95 no cruza cero [{ci_lo:.3f}, {ci_hi:.3f}] pero "
                            f"|rho|={abs_rho:.3f} ({fuerza}) — DÉBIL/MARGINAL, sin "
                            f"utilidad práctica (N={n})")
    else:
        direction = ("pendiente_positiva->SPY_SUBE" if rho > 0
                     else "pendiente_positiva->SPY_BAJA")
        verdict["decision"] = "PREDICTIVA"
        verdict["razon"] = (f"CI95 [{ci_lo:.3f}, {ci_hi:.3f}] no cruza cero, "
                            f"|rho|={abs_rho:.3f} ({fuerza}), N={n}, "
                            f"P(rho<=0)={p_leq0:.4f}")
        verdict["direccion"] = direction
    verdict["rho"] = rho
    verdict["fuerza"] = fuerza
    verdict["ci95"] = [ci_lo, ci_hi]
    verdict["N"] = n
    verdict["P_rho_leq0"] = p_leq0
    verdict["P_rho_ge0"] = p_ge0
    verdict["contemporanea_rho"] = cont.get("rho")

    # ¿la ventana natural es mejor que las fijas?
    fixed_abs = {k: abs(v["predictiva_spearman"]["rho"])
                 for k, v in out["ventanas_fijas"].items()
                 if v["predictiva_spearman"]["rho"] is not None}
    if fixed_abs:
        best_fixed = max(fixed_abs.items(), key=lambda kv: kv[1])
        natural_abs = abs(rho) if rho is not None else -1
        gap = natural_abs - best_fixed[1]
        if gap > 0.05:
            comparison = "natural_gana_sustancial"
        elif gap >= 0:
            comparison = "natural_gana_marginal"
        else:
            comparison = "fija_gana"
        verdict["mejor_ventana_fija"] = best_fixed
        verdict["natural_vs_mejor_fija"] = comparison
        verdict["gap_vs_mejor_fija"] = round(gap, 4)
    return verdict


# ----------------------------------------------------------------------------
# ASIMETRÍA DIRECCIONAL — terciles de pendiente vs forward SPY
# ----------------------------------------------------------------------------
def bootstrap_mean_ci(x, n_boot=N_BOOT, seed=SEED):
    """CI95 bootstrap de la media de un array 1D (ignorando NaN).
    Devuelve {mean, ci_lo, ci_hi, n}."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 2:
        return {"mean": float(np.nanmean(x)) if n > 0 else None,
                "ci_lo": None, "ci_hi": None, "n": n}
    rng_boot = np.random.default_rng(seed)
    idx = rng_boot.integers(0, n, size=(n_boot, n))
    boot_means = x[idx].mean(axis=1)
    return {"mean": float(x.mean()),
            "ci_lo": float(np.percentile(boot_means, 2.5)),
            "ci_hi": float(np.percentile(boot_means, 97.5)),
            "n": n}


def wins_losses(x):
    """Descomposición wins/losses: count, mean, pct, CI95 de cada grupo.
    'win' = x > 0, 'loss' = x < 0. Ignora NaN."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    wins = x[x > 0]
    losses = x[x < 0]
    zeros = int(np.sum(x == 0))
    return {
        "n_total": n,
        "wins": {
            "n": len(wins),
            "pct": round(100 * len(wins) / n, 1) if n > 0 else None,
            "mean": float(wins.mean()) if len(wins) > 0 else None,
            "ci95": [float(np.percentile(
                np.random.default_rng(SEED).choice(wins, size=(N_BOOT, len(wins))).mean(axis=1), 2.5)),
                     float(np.percentile(
                np.random.default_rng(SEED).choice(wins, size=(N_BOOT, len(wins))).mean(axis=1), 97.5))]
            if len(wins) >= 2 else [None, None],
        },
        "losses": {
            "n": len(losses),
            "pct": round(100 * len(losses) / n, 1) if n > 0 else None,
            "mean": float(losses.mean()) if len(losses) > 0 else None,
            "ci95": [float(np.percentile(
                np.random.default_rng(SEED).choice(losses, size=(N_BOOT, len(losses))).mean(axis=1), 2.5)),
                     float(np.percentile(
                np.random.default_rng(SEED).choice(losses, size=(N_BOOT, len(losses))).mean(axis=1), 97.5))]
            if len(losses) >= 2 else [None, None],
        },
        "zeros": zeros,
    }


def asymmetry_verdict(terciles):
    """Veredicto de asimetría: ¿|mean_t3| ≈ |mean_t1|?
    Compara los CI95 de los terciles extremos."""
    t1 = terciles.get("t1_low", {})
    t3 = terciles.get("t3_high", {})
    m1 = t1.get("forward_mean")
    m3 = t3.get("forward_mean")
    ci1_dict = t1.get("ci95", {})
    ci3_dict = t3.get("ci95", {})
    ci1 = [ci1_dict.get("ci_lo"), ci1_dict.get("ci_hi")] if ci1_dict else [None, None]
    ci3 = [ci3_dict.get("ci_lo"), ci3_dict.get("ci_hi")] if ci3_dict else [None, None]

    if m1 is None or m3 is None:
        return {"decision": "INSUFICIENTE", "razon": "N insuficiente en un tercil extremo"}

    abs_m1, abs_m3 = abs(m1), abs(m3)
    ratio = abs_m3 / abs_m1 if abs_m1 > 0 else float("inf")

    # ¿Se solapan los CI95 de los valores absolutos?
    # Si los CI95 de los abs se solapan → simetría no descartable
    # Si no se solapan → asimétrica
    ci1_lo_abs = abs(ci1[0]) if ci1[0] is not None else None
    ci1_hi_abs = abs(ci1[1]) if ci1[1] is not None else None
    ci3_lo_abs = abs(ci3[0]) if ci3[0] is not None else None
    ci3_hi_abs = abs(ci3[1]) if ci3[1] is not None else None

    if ci1_lo_abs is not None and ci3_hi_abs is not None:
        ci_overlap = not (ci1_hi_abs < ci3_lo_abs or ci3_hi_abs < ci1_lo_abs)
    else:
        ci_overlap = None

    if ratio > 3.0:
        decision = "FUERTEMENTE_ASIMETRICA"
        razon = (f"|t3|/|t1| = {ratio:.2f}x — la señal es {ratio:.1f}x más fuerte "
                 f"en una dirección")
    elif ratio > 1.5:
        decision = "ASIMETRICA"
        razon = (f"|t3|/|t1| = {ratio:.2f}x — asimetría sustancial (CI overlap={ci_overlap})")
    elif ratio > 0.67:
        decision = "SIMETRICA"
        razon = (f"|t3|/|t1| = {ratio:.2f}x — magnitudes comparables (CI overlap={ci_overlap})")
    else:
        # ratio < 0.67 → t1 es más fuerte
        decision = "ASIMETRICA_INVERTIDA"
        razon = (f"|t3|/|t1| = {ratio:.2f}x — t1_low {1/ratio:.1f}x más fuerte que t3_high "
                 f"(CI overlap={ci_overlap})")

    return {
        "decision": decision,
        "razon": razon,
        "ratio_abs_t3_t1": round(ratio, 3),
        "ci_overlap_abs": ci_overlap,
        "mean_t1": m1,
        "mean_t3": m3,
    }


def analyze_asimetria_direccional(df, station, W_natural, slope_natural, spy_fwd_natural):
    """Análisis de asimetría direccional por terciles de pendiente.

    Para la estación dada, clasifica la pendiente en terciles y mide el forward
    SPY return en cada uno. También descompone por pivot_type y compara con
    ventana fija de 1 pivote.
    """
    val_col = f"{station}_val"
    val_s = pd.Series(df[val_col].values)
    prev_ret = df["prev_leg_return"].values
    pivot_type = df["pivot_type"].values

    out = {"station": station, "natural_window_pivots": W_natural}

    # ---- Terciles de pendiente natural ------------------------------------
    slope = np.asarray(slope_natural, dtype=float)
    fwd = np.asarray(spy_fwd_natural, dtype=float)
    mask = ~(np.isnan(slope) | np.isnan(fwd))
    slope_valid = slope[mask]
    fwd_valid = fwd[mask]
    pt_valid = pivot_type[mask]

    out["natural_n_total"] = int(mask.sum())

    if len(slope_valid) < 30:
        out["error"] = f"N={len(slope_valid)} < 30 — insuficiente para terciles"
        return out

    # Clasificar en terciles
    tercile_edges = np.percentile(slope_valid, [0, 33.333, 66.667, 100])
    t1_idx = slope_valid <= tercile_edges[1]
    t2_idx = (slope_valid > tercile_edges[1]) & (slope_valid <= tercile_edges[2])
    t3_idx = slope_valid > tercile_edges[2]

    out["tercile_edges"] = [float(e) for e in tercile_edges]

    terciles = {}
    for label, idx_mask in [("t1_low", t1_idx), ("t2_mid", t2_idx), ("t3_high", t3_idx)]:
        fwd_t = fwd_valid[idx_mask]
        pt_t = pt_valid[idx_mask]
        slope_t = slope_valid[idx_mask]
        n_t = int(idx_mask.sum())

        tercile_data = {
            "n": n_t,
            "slope_range": [float(np.min(slope_t)), float(np.max(slope_t))],
            "slope_mean": float(np.mean(slope_t)),
            "forward_mean": float(np.mean(fwd_t)),
            "ci95": bootstrap_mean_ci(fwd_t),
            "wl": wins_losses(fwd_t),
        }

        if n_t < 20:
            tercile_data["warning"] = f"N={n_t} < 20 — INSUFICIENTE para inferencia"

        # Descomposición por pivot_type
        tercile_data["por_pivot_type"] = {}
        for pt_label in ["MIN", "MAX"]:
            pt_mask = pt_t == pt_label
            fwd_pt = fwd_t[pt_mask]
            n_pt = int(pt_mask.sum())
            pt_data = {
                "n": n_pt,
                "forward_mean": float(np.mean(fwd_pt)) if n_pt > 0 else None,
                "ci95": bootstrap_mean_ci(fwd_pt) if n_pt >= 2 else {"mean": None, "ci_lo": None, "ci_hi": None, "n": n_pt},
                "wl": wins_losses(fwd_pt) if n_pt > 0 else None,
            }
            if n_pt < 20:
                pt_data["warning"] = f"N={n_pt} < 20 — INSUFICIENTE"
            tercile_data["por_pivot_type"][pt_label] = pt_data

        terciles[label] = tercile_data

    out["terciles_natural"] = terciles

    # ---- Veredicto de asimetría (ventana natural) -------------------------
    out["veredicto_asimetria_natural"] = asymmetry_verdict(terciles)

    # ---- Bonus: ventana fija de 1 pivote ----------------------------------
    W_fixed = 1
    d_fw = (val_s - val_s.shift(W_fixed)).values
    rolling_fw = pd.Series(prev_ret).rolling(W_fixed, min_periods=W_fixed).sum()
    s_fwd = (rolling_fw.shift(-W_fixed) - rolling_fw).values

    slope_1 = np.asarray(d_fw, dtype=float)
    fwd_1 = np.asarray(s_fwd, dtype=float)
    mask_1 = ~(np.isnan(slope_1) | np.isnan(fwd_1))
    slope_1v = slope_1[mask_1]
    fwd_1v = fwd_1[mask_1]
    pt_1v = pivot_type[mask_1]

    out["fixed_1pivot_n_total"] = int(mask_1.sum())

    if len(slope_1v) >= 30:
        te_1 = np.percentile(slope_1v, [0, 33.333, 66.667, 100])
        t1_1 = slope_1v <= te_1[1]
        t2_1 = (slope_1v > te_1[1]) & (slope_1v <= te_1[2])
        t3_1 = slope_1v > te_1[2]

        terciles_1 = {}
        for label, idx_mask in [("t1_low", t1_1), ("t2_mid", t2_1), ("t3_high", t3_1)]:
            fwd_t = fwd_1v[idx_mask]
            slope_t = slope_1v[idx_mask]
            n_t = int(idx_mask.sum())
            terciles_1[label] = {
                "n": n_t,
                "slope_range": [float(np.min(slope_t)), float(np.max(slope_t))],
                "slope_mean": float(np.mean(slope_t)),
                "forward_mean": float(np.mean(fwd_t)),
                "ci95": bootstrap_mean_ci(fwd_t),
                "wl": wins_losses(fwd_t),
            }

        out["terciles_fixed_1pivot"] = terciles_1
        out["veredicto_asimetria_fixed_1pivot"] = asymmetry_verdict(terciles_1)

        # Comparación natural vs fixed-1pivot
        nat_ratio = out["veredicto_asimetria_natural"].get("ratio_abs_t3_t1")
        fix_ratio = out["veredicto_asimetria_fixed_1pivot"].get("ratio_abs_t3_t1")
        if nat_ratio is not None and fix_ratio is not None:
            delta = nat_ratio - fix_ratio
            if abs(delta) < 0.2:
                comparison = "consistente"
            else:
                comparison = "divergente"
            out["comparacion_natural_vs_fixed"] = {
                "natural_ratio": nat_ratio,
                "fixed_ratio": fix_ratio,
                "delta": round(delta, 3),
                "veredicto": comparison,
            }

    return out


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    df = load_data()

    report = {
        "meta": {
            "descripcion": "Periodo natural (half-life autocorrelación) de estaciones CAT1 "
                          "y poder predictivo de su pendiente en ventana natural sobre la "
                          "tendencia de SPY.",
            "fuente": DATA,
            "n_pivotes": len(df),
            "rango_fechas": [str(df['date'].min().date()), str(df['date'].max().date())],
            "espaciamiento_mediano_dias": float(df['date'].diff().dt.days.median()),
            "espaciamiento_medio_dias": float(df['date'].diff().dt.days.mean()),
            "n_bootstrap": N_BOOT,
            "seed": SEED,
            "max_lag_acf": MAX_LAG,
            "estaciones_cat1": CAT1_STATIONS,
            "unidad_ventana": "pivotes (conversion dias = pivotes x 4.0 mediana espaciamiento)",
            "proxy_spy_tendencia": ("suma acumulada de prev_leg_return sobre W pivotes "
                                    "(retorno exacto SPY en la ventana; no hay serie diaria "
                                    "SPY en quants_obs.pkl)"),
            "nota_prev_leg_return": ("prev_leg_return NO es 100% estructural con pivot_type "
                                     "(81.3% coincidencia de signo): varianza real valida."),
        },
        "resumen": {},
        "estaciones": {},
    }

    for station in CAT1_STATIONS:
        res = analyze_station(df, station)
        report["estaciones"][station] = res
        report["resumen"][station] = {
            "half_life_pivots": res.get("half_life_pivots"),
            "half_life_days": res.get("half_life_days"),
            "natural_window_pivots": res.get("natural_window_pivots"),
            "veredicto": res.get("veredicto"),
        }

    # ---- ASIMETRÍA DIRECCIONAL (solo CREDIT y ROTATION) ------------------
    ASYMMETRY_STATIONS = ["credit", "rotation"]
    report["asimetria_direccional"] = {
        "descripcion": ("Descomposición por TERCILES de pendiente (t1_low/t2_mid/t3_high) "
                        "del forward SPY return. Mide si la señal predictiva es simétrica "
                        "(igual de fuerte en ambas direcciones de pendiente) o asimétrica "
                        "(solo funciona en una dirección)."),
        "metodo": {
            "tercil_clasificacion": "percentiles empíricos [0, 33.3%, 66.7%, 100%] de la pendiente",
            "forward_proxy": "mismo que el script principal: rolling[i+W] - rolling[i] de prev_leg_return",
            "bootstrap": f"N={N_BOOT} iteraciones, seed={SEED}",
            "wins_losses": "wins = forward > 0, losses = forward < 0, separados",
            "n_minimo_tercil": 20,
        },
        "estaciones": {},
    }

    for station in ASYMMETRY_STATIONS:
        res = report["estaciones"][station]
        W = res.get("natural_window_pivots")
        if W is None or "error" in res:
            report["asimetria_direccional"]["estaciones"][station] = {
                "error": f"W={W} — no se puede computar asimetría"
            }
            continue
        slope = res.get("_slope_raw")
        fwd = res.get("_spy_trend_fwd")
        asym = analyze_asimetria_direccional(df, station, W, slope, fwd)
        report["asimetria_direccional"]["estaciones"][station] = asym

    with open(REPORT, "w") as f:
        # Limpiar arrays internos (_slope_raw, _spy_trend_fwd) del JSON
        for st in CAT1_STATIONS:
            report["estaciones"][st].pop("_slope_raw", None)
            report["estaciones"][st].pop("_spy_trend_fwd", None)
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    # ---- salida de consola legible ---------------------------------------
    print("=" * 100)
    print("PERÍODO NATURAL CAT1 — PENDIENTE EN VENTANA NATURAL vs TENDENCIA SPY")
    print("=" * 100)
    for station in CAT1_STATIONS:
        r = report["estaciones"][station]
        v = r.get("veredicto", {})
        print(f"\n### {station.upper()}  (val: {r['n_valid']}/{r['n_total']} válidos, "
              f"{r['n_nan']} NaN)")
        print(f"  half-life: {r['half_life_pivots']} pivotes = {r['half_life_days']} días "
              f"(cruzó 0.5: {r['half_life_crossed_0p5']})  | ventana natural W={r['natural_window_pivots']}")
        if r.get("adf"):
            a = r["adf"]
            print(f"  ADF: stat={a['adf_stat']:.3f} p={a['p_value']:.4f} "
                  f"estacionaria@5%={a['stationary_at_5pct']}")
        for k, label in [("contemporanea", "CONTEMPORÁNEA"), ("predictiva_lead", "PREDICTIVA/LEAD")]:
            sp = r[k]["spearman"]
            pe = r[k]["pearson"]
            if sp["rho"] is not None:
                print(f"  {label:<16} Spearman rho={sp['rho']:+.3f} CI95[{sp['ci_lo']:+.3f},{sp['ci_hi']:+.3f}] "
                      f"N={sp['n']}  |  Pearson rho={pe['rho']:+.3f} CI95[{pe['ci_lo']:+.3f},{pe['ci_hi']:+.3f}]")
            else:
                print(f"  {label:<16} N insuficiente (N={sp['n']})")
        print(f"  POR PIVOT_TYPE:")
        for pt in ["MIN", "MAX"]:
            c = r["por_pivot_type"][pt]["predictiva_spearman"]
            if c["rho"] is not None:
                print(f"    {pt}: predictiva Spearman rho={c['rho']:+.3f} "
                      f"CI95[{c['ci_lo']:+.3f},{c['ci_hi']:+.3f}] N={c['n']}")
        print(f"  VEREDICTO: {v.get('decision')} ({v.get('fuerza','?')})")
        print(f"    {v.get('razon')}")
        if v.get("direccion"):
            print(f"    dirección: {v['direccion']}")
        if v.get("natural_vs_mejor_fija"):
            print(f"    ventana natural vs mejor fija: {v['natural_vs_mejor_fija']} "
                  f"(gap={v.get('gap_vs_mejor_fija', 'N/A')})")
        print(f"  ventanas fijas (predictiva Spearman): " +
              ", ".join(f"{k}pv={vv['predictiva_spearman']['rho']:+.3f}"
                        for k, vv in r["ventanas_fijas"].items()
                        if vv["predictiva_spearman"]["rho"] is not None))

    # ---- salida de asimetría direccional ---------------------------------
    print("\n" + "=" * 100)
    print("ASIMETRÍA DIRECCIONAL — TERCILES DE PENDIENTE vs FORWARD SPY")
    print("=" * 100)
    asym_report = report.get("asimetria_direccional", {}).get("estaciones", {})
    for station in ASYMMETRY_STATIONS:
        a = asym_report.get(station, {})
        if "error" in a:
            print(f"\n### {station.upper()}: ERROR — {a['error']}")
            continue
        print(f"\n### {station.upper()}  (ventana natural W={a.get('natural_window_pivots')}, "
              f"N={a.get('natural_n_total')})")
        print(f"  Terciles de pendiente (edges): {[f'{e:.4f}' for e in a.get('tercile_edges', [])]}")
        for tl in ["t1_low", "t2_mid", "t3_high"]:
            t = a.get("terciles_natural", {}).get(tl, {})
            ci = t.get("ci95", {})
            wl = t.get("wl", {})
            w = wl.get("wins", {})
            l = wl.get("losses", {})
            wn = t.get("warning", "")
            print(f"  {tl}: N={t.get('n')}  slope∈[{t.get('slope_range',[0,0])[0]:.4f}, {t.get('slope_range',[0,0])[1]:.4f}]  "
                  f"μ={t.get('slope_mean', 0):.4f}  "
                  f"fwd_SPY={t.get('forward_mean', 0):+.4f} "
                  f"CI95[{ci.get('ci_lo', '?'):+.4f}, {ci.get('ci_hi', '?'):+.4f}]  "
                  f"Wins={w.get('n',0)}({w.get('pct',0)}% μ={w.get('mean', 0):+.4f})  "
                  f"Losses={l.get('n',0)}({l.get('pct',0)}% μ={l.get('mean', 0):+.4f})"
                  f"{'  ⚠ ' + wn if wn else ''}")
            for pt_label in ["MIN", "MAX"]:
                pt = t.get("por_pivot_type", {}).get(pt_label, {})
                if pt and pt.get("n", 0) > 0:
                    pt_ci = pt.get("ci95", {})
                    pt_wl = pt.get("wl", {})
                    pt_w = pt_wl.get("wins", {}) if pt_wl else {}
                    pt_l = pt_wl.get("losses", {}) if pt_wl else {}
                    print(f"    {pt_label}: N={pt.get('n')}  fwd={pt.get('forward_mean', 0):+.4f} "
                          f"CI95[{pt_ci.get('ci_lo', '?'):+.4f}, {pt_ci.get('ci_hi', '?'):+.4f}]  "
                          f"W={pt_w.get('n',0)}/{pt_w.get('pct',0)}%  L={pt_l.get('n',0)}/{pt_l.get('pct',0)}%")
        # Veredicto
        v_asym = a.get("veredicto_asimetria_natural", {})
        print(f"  VEREDICTO ASIMETRÍA (natural): {v_asym.get('decision')}")
        print(f"    {v_asym.get('razon')}")
        print(f"    |t3|={abs(v_asym.get('mean_t3', 0)):.4f}  |t1|={abs(v_asym.get('mean_t1', 0)):.4f}  "
              f"ratio={v_asym.get('ratio_abs_t3_t1')}  CI_overlap={v_asym.get('ci_overlap_abs')}")
        # Fixed 1-pivot
        v_fix = a.get("veredicto_asimetria_fixed_1pivot", {})
        if v_fix:
            print(f"  VEREDICTO ASIMETRÍA (fixed 1pivot): {v_fix.get('decision')}")
            print(f"    {v_fix.get('razon')}")
        comp = a.get("comparacion_natural_vs_fixed", {})
        if comp:
            print(f"  Natural vs Fixed-1pivot: {comp.get('veredicto')} "
                  f"(natural={comp.get('natural_ratio')}, fixed={comp.get('fixed_ratio')}, "
                  f"Δ={comp.get('delta')})")

    print("\n" + "=" * 100)
    print(f"Reporte JSON escrito en: {REPORT}")
    print("=" * 100)


if __name__ == "__main__":
    main()
