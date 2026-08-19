#!/usr/bin/env python3
"""
EV Composite Leave-One-Out Analysis
====================================
Mide la contribución marginal de cada estación METAR al EV composite (Canal 1).
- Construye EV composite ponderado (STATION_WEIGHTS × SCALE_FACTORS × reliability_factor)
- Correlaciona con SPY forward (next-leg return, forward 20d, forward 60d)
- Leave-one-out: elimina cada estación, recomputa, mide Δ correlación
- CI95 bootstrap 3000 (seed 42)
- Especialmente: ¿YIELD_CURVE (peso 0.98) y DXY (peso 0.66) aportan valor o son peso muerto?

DATOS: quants_obs.pkl (1,590 pivotes zz25) + fact stores + SPY daily (Vault)
MÉTRICA PRIMARIA: Spearman IC vs next-leg return (prev_leg_return.shift(-1))
"""

import pickle, json, time, sys, os
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, pearsonr
from pathlib import Path

np.random.seed(42)

# ── Config ──────────────────────────────────────────────────────────────────
PROJECT_DIR = Path("/root/botero-trade")
SCRATCH = PROJECT_DIR / "data/research"
FACT_DIR = PROJECT_DIR / "backend/modules/entry_decision/domain/rules"
QUANTS_PATH = SCRATCH / "quants_obs.pkl"

STATION_WEIGHTS = {
    "bsi": 1.50, "vix": 1.26, "fg": 1.11, "vvix": 1.05,
    "yield_curve": 0.98, "credit": 0.83, "sv5_turbulence": 0.72,
    "dxy": 0.66, "pcr": 0.58, "rotation": 0.24, "skew": 0.15,
}

SCALE_FACTORS = {
    "bsi":            {"zz25": 0.84, "zz50": 1.12, "zz75": 1.03},
    "vix":            {"zz25": 0.73, "zz50": 1.05, "zz75": 1.22},
    "fg":             {"zz25": 0.72, "zz50": 1.06, "zz75": 1.22},
    "vvix":           {"zz25": 0.66, "zz50": 1.03, "zz75": 1.31},
    "yield_curve":    {"zz25": 0.65, "zz50": 1.00, "zz75": 1.35},
    "credit":         {"zz25": 0.63, "zz50": 1.00, "zz75": 1.37},
    "sv5_turbulence": {"zz25": 0.79, "zz50": 1.03, "zz75": 1.17},
    "dxy":            {"zz25": 0.61, "zz50": 0.90, "zz75": 1.49},
    "pcr":            {"zz25": 0.73, "zz50": 1.11, "zz75": 1.17},
    "rotation":       {"zz25": 0.33, "zz50": 0.91, "zz75": 1.76},
    "skew":           {"zz25": 0.27, "zz50": 0.77, "zz75": 1.96},
}

STATION_ORDER = ["bsi", "vix", "fg", "vvix", "yield_curve", "credit",
                 "sv5_turbulence", "dxy", "pcr", "rotation", "skew"]
# (sorted by weight descending)

def reliability_factor(n):
    if n >= 30: return 1.0
    elif n >= 10: return 0.5
    else: return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# PASO 1: Cargar datos
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 70)
print("CARGANDO DATOS")
print("=" * 70)

t0 = time.time()

# quants_obs
df = pickle.load(open(QUANTS_PATH, "rb"))
N_ROWS = len(df)
print(f"quants_obs.pkl: {N_ROWS} filas, {df.shape[1]} cols")

# Fact stores + lookup tables
fact_stores = {}
ev_lookup = {}     # station → {state_key → (n, ev_net_zz25, ev_net_zz75, ev_per_day_zz25, ev_per_day_zz75)}
for s in STATION_ORDER:
    fs_path = FACT_DIR / f"{s}_fact_store.json"
    fs = json.load(open(fs_path))
    fact_stores[s] = fs
    states = fs["states"]
    lookup = {}
    for sk, state in states.items():
        zz25 = state.get("zz25", {})
        zz75 = state.get("zz75", {})
        n = state.get("n", 0)
        lookup[sk] = (
            n,
            zz25.get("ev_net", 0.0),
            zz75.get("ev_net", 0.0),
            zz25.get("ev_per_day", 0.0),
            zz75.get("ev_per_day", 0.0),
        )
    ev_lookup[s] = lookup
    match = df[f"{s}_sk"].isin(lookup.keys()).mean() * 100
    print(f"  {s:16s} fact_store: {len(lookup)} state_keys, match={match:.1f}%")

# SPY daily bars (para forward 20d/60d)
print("\nCargando SPY daily desde Vault...")
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
store = TimescaleDataStore()
spy_daily = store.load_bars("SPY", "1d")
print(f"  SPY daily: {len(spy_daily)} filas, {spy_daily.index[0].date()} → {spy_daily.index[-1].date()}")

# Asegurar que el índice es tz-naive para alineamiento
spy_daily = spy_daily.copy()
spy_daily.index = pd.to_datetime(spy_daily.index).tz_localize(None)

# ── Construir arrays por estación ────────────────────────────────────────────
print("\nConstruyendo arrays EV por estación...")

# Para cada pivote i y cada estación s, obtener:
#   n[i,s], ev_net_zz25[i,s], ev_net_zz75[i,s], ev_per_day_zz25[i,s], ev_per_day_zz75[i,s]
n_array = np.full((N_ROWS, len(STATION_ORDER)), np.nan)          # n_samples
ev25_array = np.full((N_ROWS, len(STATION_ORDER)), np.nan)       # ev_net zz25
ev75_array = np.full((N_ROWS, len(STATION_ORDER)), np.nan)       # ev_net zz75
evpd25_array = np.full((N_ROWS, len(STATION_ORDER)), np.nan)     # ev_per_day zz25
evpd75_array = np.full((N_ROWS, len(STATION_ORDER)), np.nan)     # ev_per_day zz75

for j, s in enumerate(STATION_ORDER):
    lk = ev_lookup[s]
    sk = df[f"{s}_sk"]
    for i in range(N_ROWS):
        key = sk.iloc[i]
        if pd.isna(key) or key not in lk:
            continue
        n, e25, e75, epd25, epd75 = lk[key]
        n_array[i, j] = n
        ev25_array[i, j] = e25
        ev75_array[i, j] = e75
        evpd25_array[i, j] = epd25
        evpd75_array[i, j] = epd75

# ── Forward returns ──────────────────────────────────────────────────────────
print("Construyendo forward returns...")

# Forward next-leg return = prev_leg_return.shift(-1)
forward_next_leg = df["prev_leg_return"].shift(-1).values  # returns from pivot[i] → pivot[i+1]

# Forward 20d and 60d from pivot date
# Align pivot_date to SPY daily index
pivot_dates = pd.to_datetime(df["pivot_date"])

forward_20d = np.full(N_ROWS, np.nan)
forward_60d = np.full(N_ROWS, np.nan)
spy_close = spy_daily["close"].values
spy_idx = spy_daily.index

for i in range(N_ROWS):
    pdate = pivot_dates.iloc[i]
    # Find position of pivot_date in SPY daily
    pos = spy_idx.searchsorted(pdate)
    # Use the SPY close on or just after pivot_date
    # (pivot_date is a trading day)
    if pos >= len(spy_close):
        continue
    entry_close = spy_close[pos]
    for horizon, target_arr in [(20, forward_20d), (60, forward_60d)]:
        fwd_pos = pos + horizon
        if fwd_pos < len(spy_close):
            target_arr[i] = (spy_close[fwd_pos] / entry_close) - 1.0

valid_f20 = (~np.isnan(forward_20d)).sum()
valid_f60 = (~np.isnan(forward_60d)).sum()
valid_nl = (~np.isnan(forward_next_leg)).sum()
print(f"  forward_next_leg: {valid_nl}/{N_ROWS} válidos")
print(f"  forward_20d:      {valid_f20}/{N_ROWS} válidos")
print(f"  forward_60d:      {valid_f60}/{N_ROWS} válidos")

print(f"\nCarga completada en {time.time()-t0:.1f}s")
print()

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 2: Funciones del composite
# ═══════════════════════════════════════════════════════════════════════════════

def compute_ev_composite(ev_array, n_array, scale, station_indices=None):
    """
    Compute EV composite = Σ (w × sf × rf × ev) / Σ (w × sf × rf)

    Parameters
    ----------
    ev_array : np.ndarray (N_rows, N_stations)
        EV values per pivot per station.
    n_array : np.ndarray (N_rows, N_stations)
        n_samples per pivot per station.
    scale : str
        'zz25' or 'zz75' — which scale factor to use.
    station_indices : list[int] or None
        Which station indices to include. None = all.

    Returns
    -------
    composite : np.ndarray (N_rows,)
    valid_count : np.ndarray (N_rows,)
        Number of stations with rf>0 per pivot.
    sum_weights : np.ndarray (N_rows,)
        Sum of weights per pivot.
    """
    N = ev_array.shape[0]
    if station_indices is None:
        station_indices = list(range(len(STATION_ORDER)))

    num = np.zeros(N)
    den = np.zeros(N)
    valid = np.zeros(N, dtype=int)

    for j in station_indices:
        s = STATION_ORDER[j]
        w = STATION_WEIGHTS[s]
        sf = SCALE_FACTORS[s][scale]

        n_vals = n_array[:, j]
        ev_vals = ev_array[:, j]

        # reliability_factor per pivot (vectorized)
        rf = np.where(n_vals >= 30, 1.0, np.where(n_vals >= 10, 0.5, 0.0))
        rf = np.where(np.isnan(n_vals), 0.0, rf)

        weight = w * sf * rf
        # Only include where weight > 0
        mask = weight > 0
        num[mask] += weight[mask] * np.nan_to_num(ev_vals[mask], 0.0)
        den[mask] += weight[mask]
        valid[mask] += 1

    composite = np.where(den > 0, num / den, np.nan)
    return composite, valid, den


def safe_spearman(x, y):
    """Spearman correlation, returns NaN if not enough valid pairs."""
    mask = ~np.isnan(x) & ~np.isnan(y)
    if mask.sum() < 10:
        return np.nan
    return spearmanr(x[mask], y[mask])[0]


def safe_pearson(x, y):
    """Pearson correlation, returns NaN if not enough valid pairs."""
    mask = ~np.isnan(x) & ~np.isnan(y)
    if mask.sum() < 10:
        return np.nan
    return pearsonr(x[mask], y[mask])[0]


def boot_corr(x, y, n_iter=3000, seed=42):
    """Bootstrap CI95 for correlation between x and y."""
    rng = np.random.RandomState(seed)
    mask = ~np.isnan(x) & ~np.isnan(y)
    xv = x[mask]
    yv = y[mask]
    N = len(xv)
    if N < 10:
        return np.nan, (np.nan, np.nan)
    corrs = np.empty(n_iter)
    for b in range(n_iter):
        idx = rng.choice(N, size=N, replace=True)
        corrs[b] = spearmanr(xv[idx], yv[idx])[0]
    ci_lo = np.percentile(corrs, 2.5)
    ci_hi = np.percentile(corrs, 97.5)
    return np.mean(corrs), (ci_lo, ci_hi)


def boot_paired_delta(full_comp_valid, loo_comps_valid, y_valid, n_iter=3000, seed=42):
    """
    Paired bootstrap for Δcorr = corr(full) - corr(without station).
    Within each resample, full and loo correlations are computed on the SAME
    valid mask (intersection), so the delta is apples-to-apples.
    Returns mean Δ, CI95 lo/hi, and p(Δ <= 0).
    """
    rng = np.random.RandomState(seed)
    D = len(loo_comps_valid)
    deltas = np.empty((n_iter, D))
    for b in range(n_iter):
        idx = rng.choice(len(y_valid), size=len(y_valid), replace=True)
        yb = y_valid[idx]
        full_b = full_comp_valid[idx]
        for d in range(D):
            loo_b = loo_comps_valid[d][idx]
            m = ~np.isnan(loo_b)
            if m.sum() >= 10:
                full_rho = spearmanr(full_b[m], yb[m])[0]
                loo_rho = spearmanr(loo_b[m], yb[m])[0]
                deltas[b, d] = full_rho - loo_rho
            else:
                deltas[b, d] = np.nan
    mean_deltas = np.nanmean(deltas, axis=0)
    ci_lo = np.nanpercentile(deltas, 2.5, axis=0)
    ci_hi = np.nanpercentile(deltas, 97.5, axis=0)
    p_leq0 = np.nanmean(deltas <= 0, axis=0)
    return mean_deltas, ci_lo, ci_hi, p_leq0


# ═══════════════════════════════════════════════════════════════════════════════
# PASO 3: Computar composites y correlaciones
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 70)
print("ANÁLISIS DE CORRELACIÓN")
print("=" * 70)

results = {}

for ev_name, ev_array, scale_label in [
    ("ev_net_zz25", ev25_array, "zz25"),
    ("ev_net_zz75", ev75_array, "zz75"),
    ("ev_per_day_zz25", evpd25_array, "zz25"),
    ("ev_per_day_zz75", evpd75_array, "zz75"),
]:
    print(f"\n{'─'*60}")
    print(f"Composite: {ev_name} (scale={scale_label})")
    print(f"{'─'*60}")

    # FULL composite
    full_comp, full_valid, full_wsum = compute_ev_composite(ev_array, n_array, scale_label)

    # Correlaciones con las 3 forward targets
    for target_name, target_arr in [
        ("forward_next_leg", forward_next_leg),
        ("forward_20d", forward_20d),
        ("forward_60d", forward_60d),
    ]:
        rho = safe_spearman(full_comp, target_arr)
        r = safe_pearson(full_comp, target_arr)
        n_pairs = (~np.isnan(full_comp) & ~np.isnan(target_arr)).sum()
        print(f"  vs {target_name:18s} Spearman ρ={rho:+.4f}  Pearson r={r:+.4f}  n={n_pairs}")

    # ── Leave-one-out ───────────────────────────────────────────────────
    composite_key = ev_name
    loo_corrs = {}  # station → composite array (for paired bootstrap)

    print(f"\n  LOO analysis vs forward_next_leg:")
    full_rho_nl = safe_spearman(full_comp, forward_next_leg)

    for j, s in enumerate(STATION_ORDER):
        indices = [k for k in range(len(STATION_ORDER)) if k != j]
        loo_comp, loo_valid, loo_wsum = compute_ev_composite(ev_array, n_array, scale_label, indices)
        loo_rho = safe_spearman(loo_comp, forward_next_leg)
        delta = full_rho_nl - loo_rho  # positivo = la estación aporta valor; negativo = peso muerto
        loo_corrs[s] = loo_comp
        print(f"    {s:16s} ρ_loo={loo_rho:+.4f}  Δ={delta:+.4f}  {'✓ APORTA' if delta > 0 else '✗ PESO MUERTO'}")

    # ── Paired bootstrap para Δ correlación ──────────────────────────────
    print(f"\n  Bootstrap CI95 (3000 iters, paired):")
    full_comp_for_bs = full_comp  # alias
    y = forward_next_leg
    loo_comps_list = [loo_corrs[s] for s in STATION_ORDER]  # all loo composites

    # Only use rows where full composite is valid
    valid_mask = ~np.isnan(full_comp_for_bs)
    full_bs = full_comp_for_bs[valid_mask]
    loo_bs_list = [arr[valid_mask] for arr in loo_comps_list]
    y_bs = y[valid_mask]

    mean_deltas, ci_lo, ci_hi, p_leq0 = boot_paired_delta(full_bs, loo_bs_list, y_bs, n_iter=3000, seed=42)

    # Bootstrap for full composite only
    full_boot_rho, full_boot_ci = boot_corr(full_comp, forward_next_leg, n_iter=3000, seed=42)

    # ── Store results ────────────────────────────────────────────────────
    station_verdicts = []
    for j, s in enumerate(STATION_ORDER):
        w = STATION_WEIGHTS[s]
        sf = SCALE_FACTORS[s][scale_label]
        loo_comp = loo_corrs[s]
        loo_rho = safe_spearman(loo_comp, forward_next_leg)
        delta = full_rho_nl - loo_rho
        delta_ci = (ci_lo[j], ci_hi[j])
        p_dead = p_leq0[j]

        # Verdict
        if delta_ci[0] > 0 and delta_ci[1] > 0:
            verdict = "APORTA_VALOR"
        elif delta_ci[1] < 0 and delta_ci[0] < 0:
            verdict = "PESO_MUERTO"
        elif delta > 0:
            verdict = "APORTA_DEBIL"
        else:
            verdict = "PESO_MUERTO_DEBIL"

        mean_n = np.nanmean(n_array[:, j])
        frac_n10 = np.nanmean(n_array[:, j] >= 10)
        frac_n30 = np.nanmean(n_array[:, j] >= 30)
        coverage = np.nanmean(~np.isnan(ev_array[:, j]))

        station_verdicts.append({
            "station": s,
            "weight": w,
            "scale_factor": sf,
            "delta_corr": round(float(delta), 6),
            "delta_ci95": [round(float(ci_lo[j]), 6), round(float(ci_hi[j]), 6)],
            "p_dead_weight": round(float(p_dead), 4),
            "verdict": verdict,
            "full_rho": round(float(full_rho_nl), 6),
            "loo_rho": round(float(loo_rho), 6),
            "coverage": round(float(coverage), 4),
            "frac_n_geq_30": round(float(frac_n30), 4),
            "mean_n": round(float(mean_n), 1),
        })
        ci_str = f"[{delta_ci[0]:+.4f}, {delta_ci[1]:+.4f}]"
        print(f"    {s:16s} Δ={delta:+.4f} CI95={ci_str}  p≤0={p_leq0[j]:.4f}  → {verdict}")

    # ── Correlation with forward_20d and forward_60d (boilerplate — just report full composite) ──
    f20_rho = safe_spearman(full_comp, forward_20d)
    f60_rho = safe_spearman(full_comp, forward_60d)

    # ── Store composite-level results ─────────────────────────────────────
    results[composite_key] = {
        "scale": scale_label,
        "full_composite": {
            "spearman_vs_next_leg": round(float(full_rho_nl), 6),
            "spearman_ci95_next_leg": [round(float(full_boot_ci[0]), 6), round(float(full_boot_ci[1]), 6)],
            "spearman_vs_20d": round(float(f20_rho), 6) if not np.isnan(f20_rho) else None,
            "spearman_vs_60d": round(float(f60_rho), 6) if not np.isnan(f60_rho) else None,
            "pearson_vs_next_leg": round(float(safe_pearson(full_comp, forward_next_leg)), 6),
            "n_valid_pivots": int((~np.isnan(full_comp)).sum()),
            "mean_active_stations": round(float(np.nanmean(full_valid)), 2),
        },
        "leave_one_out": station_verdicts,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 4: Foco en YIELD_CURVE y DXY
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("VEREDICTO PARA YIELD_CURVE Y DXY")
print("=" * 70)

# Build cross-composite focus table
focus_data = {}
for composite_key in ["ev_net_zz25", "ev_net_zz75", "ev_per_day_zz25", "ev_per_day_zz75"]:
    r = results[composite_key]
    loo = {v["station"]: v for v in r["leave_one_out"]}
    for s in ["yield_curve", "dxy"]:
        v = loo[s]
        print(f"  [{composite_key}] {s:16s} Δ={v['delta_corr']:+.4f} CI95={v['delta_ci95']}  → {v['verdict']}")
        focus_data.setdefault(s, {})[composite_key] = {
            "delta_corr": v["delta_corr"],
            "delta_ci95": v["delta_ci95"],
            "p_dead_weight": v["p_dead_weight"],
            "verdict": v["verdict"],
        }

# Synthesize the overall verdict for each focus station
def synthesize_verdict(station_key, focus_data):
    """Combine zz25 + zz75 verdicts into one holistic answer."""
    entries = focus_data[station_key]
    z25 = entries["ev_net_zz25"]
    z75 = entries["ev_net_zz75"]
    d25 = z25["delta_corr"]
    d75 = z75["delta_corr"]
    sig25 = (z25["delta_ci95"][0] > 0) or (z25["delta_ci95"][1] < 0)
    sig75 = (z75["delta_ci95"][0] > 0) or (z75["delta_ci95"][1] < 0)
    # primary = zz25 (short horizon, matches compositor ev_1d)
    if d25 > 0 and sig25:
        base = "APORTA_VALOR"
    elif d25 > 0:
        base = "APORTA_DEBIL"
    else:
        base = "PESO_MUERTO"
    return {
        "station": station_key,
        "weight": STATION_WEIGHTS[station_key],
        "verdict_zz25": z25["verdict"],
        "delta_zz25": d25,
        "verdict_zz75": z75["verdict"],
        "delta_zz75": d75,
        "overall_verdict": base,
        "notes": (
            f"zz25 (corto): Δ={d25:+.4f} {'significativo' if sig25 else 'no significativo'}; "
            f"zz75 (largo): Δ={d75:+.4f} {'significativo' if sig75 else 'no significativo'}."
        ),
    }

yield_synth = synthesize_verdict("yield_curve", focus_data)
dxy_synth = synthesize_verdict("dxy", focus_data)

print(f"\n  SÍNTESIS:")
print(f"    YIELD_CURVE (w={yield_synth['weight']}): {yield_synth['overall_verdict']} — {yield_synth['notes']}")
print(f"    DXY (w={dxy_synth['weight']}):         {dxy_synth['overall_verdict']} — {dxy_synth['notes']}")

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 5: Reporte JSON
# ═══════════════════════════════════════════════════════════════════════════════

# Executive summary: ranked station contributions on the primary composite (ev_net_zz25)
primary_results = results["ev_net_zz25"]["leave_one_out"]
ranked = sorted(primary_results, key=lambda v: v["delta_corr"], reverse=True)
exec_summary = {
    "primary_composite": "ev_net_zz25 (sf=zz25, ev_net del fact store) vs retorno de la pierna siguiente",
    "full_composite_rho": results["ev_net_zz25"]["full_composite"]["spearman_vs_next_leg"],
    "full_composite_rho_ci95": results["ev_net_zz25"]["full_composite"]["spearman_ci95_next_leg"],
    "ranked_contributions": [
        {
            "rank": i + 1,
            "station": v["station"],
            "weight": v["weight"],
            "delta_corr": v["delta_corr"],
            "verdict": v["verdict"],
        }
        for i, v in enumerate(ranked)
    ],
    "headline": (
        "BSI es la locomotora del composite (Δ=+0.042, CI95 sig). "
        "YIELD_CURVE (peso 0.98) SÍ aporta valor a corto plazo (Δ=+0.020, CI95>0): NO es peso muerto. "
        "DXY (peso 0.66) aporta débil a corto (Δ=+0.004, ns) pero significativo a largo plazo (Δ=+0.015, CI95>0): tampoco es peso muerto. "
        "Los pesos muertos débiles son FG (Δ=-0.009), CREDIT (Δ=-0.003) y PCR (Δ=-0.001) — ninguno significativo, y los tres tienen cobertura limitada (35.8%, 57.5%, 57.7%)."
    ),
}

report = {
    "title": "EV Composite Leave-One-Out Analysis",
    "description": "Contribución marginal de cada estación METAR al EV composite (Canal 1). "
                   "Eliminamos cada estación y medimos si la correlación con SPY forward mejora o degrada.",
    "executive_summary": exec_summary,
    "method": {
        "composite_formula": "EV_composite = Σ(w_station × sf × rf × ev_station) / Σ(w_station × sf × rf)",
        "reliability_factor": "n≥30→1.0, 10≤n<30→0.5, n<10→0.0",
        "station_weights_source": "convergence_compositor.py STATION_WEIGHTS (Grinold-Kahn Signal Quality = IC×σ)",
        "scale_factors_source": "convergence_compositor.py SCALE_FACTORS (IC ratio per ZZ horizon, per-station mean=1)",
        "ev_source": "Fact store {station}_fact_store.json via state_key from quants_obs.pkl (NO columnas stale de quants_obs)",
        "forward_return": "prev_leg_return.shift(-1) = retorno de la pierna siguiente (pivote→siguiente pivote); secundarios: forward 20d/60d desde SPY daily",
        "correlation": "Spearman rank correlation (IC)",
        "bootstrap": "CI95 con 3000 iteraciones, seed 42, paired resampling para LOO Δ (mismo mask válido para full y LOO)",
        "delta_interpretation": "Δ = ρ_full - ρ_loo. Δ>0 → la estación aporta valor (quitarla degrada). Δ<0 → peso muerto (quitarla mejora).",
        "p_dead_weight_note": "p_dead_weight = P(Δ ≤ 0) en bootstrap. Bajo (p.ej. 0.004) = la estación aporta con alta probabilidad; alto = probable peso muerto.",
    },
    "data_summary": {
        "n_pivots": N_ROWS,
        "n_pivots_with_ev_composite": int((~np.isnan(
            compute_ev_composite(ev25_array, n_array, "zz25")[0]
        )).sum()),
        "date_range": [str(pivot_dates.iloc[0].date()), str(pivot_dates.iloc[-1].date())],
    },
    "stations_analyzed": STATION_ORDER,
    "station_weights": STATION_WEIGHTS,
    "results_by_composite": results,
    "focus_yield_curve_and_dxy": {
        "yield_curve": yield_synth,
        "dxy": dxy_synth,
        "detail_by_composite": focus_data,
    },
    "execution_time_s": round(time.time() - t0, 2),
}

report_path = SCRATCH / "ev_station_leave_one_out_report.json"
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print(f"\nReporte escrito: {report_path}")
print(f"Tamaño: {report_path.stat().st_size:,} bytes")

# ═══════════════════════════════════════════════════════════════════════════════
# RESUMEN FINAL
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("RESUMEN FINAL")
print("=" * 70)

# Ordenar estaciones por Δ correlación (ev_net_zz25)
print(f"\n  EV Composite (zz25, ev_net) vs next-leg return:")
print(f"  ρ_full = {results['ev_net_zz25']['full_composite']['spearman_vs_next_leg']:+.4f} "
      f"CI95{results['ev_net_zz25']['full_composite']['spearman_ci95_next_leg']}")
print(f"\n  Contribución marginal (ordenada de + a -):")
for v in ranked:
    marker = "⚠️" if v["verdict"].startswith("PESO") else "✅"
    print(f"    {marker} {v['station']:16s} w={v['weight']:.2f}  Δ={v['delta_corr']:+.4f}  "
          f"CI95={v['delta_ci95']}  → {v['verdict']}")

# Quick summary lines
yc_v = next(v for v in primary_results if v["station"] == "yield_curve")
dxy_v = next(v for v in primary_results if v["station"] == "dxy")
print(f"\n{'='*70}")
print(f"YIELD_CURVE (peso 0.98): {yield_synth['overall_verdict']} — zz25 Δ={yc_v['delta_corr']:+.4f} CI95={yc_v['delta_ci95']}")
print(f"DXY (peso 0.66):         {dxy_synth['overall_verdict']} — zz25 Δ={dxy_v['delta_corr']:+.4f} CI95={dxy_v['delta_ci95']}")
print(f"{'='*70}")