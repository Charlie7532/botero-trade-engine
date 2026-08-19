#!/usr/bin/env python3
"""
CONJUNCIÓN MACRO: CREDIT + YIELD + DXY
=======================================
Cluster FLUJO/MACRO. Mide la conjunción de señales de estrés macro
(1 vs 2 vs 3 señales simultáneas) y su impacto en SPY forward 20d.

Estaciones y D1 estrés:
  - CREDIT: CREDIT_CRISIS, CREDIT_STRESS
  - YIELD:  EXTREME_STEEPNING, DEEP_INVERSION
  - DXY:    DOLLAR_SPIKE_CRISIS

Métricas: CI95 bootstrap (2000 iter), wins/losses, Kelly criterion,
profit factor, EV por nivel de conjunción.

Output: reporte tabular + JSON para trazabilidad.
"""

import sys
import os
import json
import math
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════

FORWARD = 20                    # forward horizon (trading days)
N_BOOT = 2000                   # bootstrap iterations
SEED = 42
CI = 95

# D1 bins considerados como ESTRÉS MACRO
STRESS_BINS = {
    "CREDIT": ["CREDIT_CRISIS", "CREDIT_STRESS"],
    "YIELD":  ["EXTREME_STEEPNING", "DEEP_INVERSION"],
    "DXY":    ["DOLLAR_SPIKE_CRISIS"],
}

# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def bootstrap_ci(arr, ci=95, n_boot=N_BOOT, seed=SEED):
    """CI95 for mean via bootstrap."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    means = np.array([rng.choice(arr, size=len(arr), replace=True).mean()
                       for _ in range(n_boot)])
    means.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(means, lo)), float(np.percentile(means, hi))


def bootstrap_ci_winrate(events, ci=95, n_boot=N_BOOT, seed=SEED):
    """CI95 for win rate (proportion) via bootstrap."""
    events = np.asarray(events, bool)
    if len(events) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    wrs = np.array([rng.choice(events, size=len(events), replace=True).mean()
                     for _ in range(n_boot)])
    wrs.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(events.mean()), float(np.percentile(wrs, lo)), float(np.percentile(wrs, hi))


def compute_d1(values, edges, labels):
    """Classify D1 using percentile-rank edges (zero look-ahead)."""
    n = len(values)
    d1 = np.full(n, "NODATA", dtype=object)
    for i in range(n):
        v = values[i]
        if np.isnan(v):
            continue
        classified = False
        for idx, e in enumerate(edges):
            if v < e:
                d1[i] = labels[idx]
                classified = True
                break
        if not classified:
            d1[i] = labels[-1]
    return d1


def kelly_fraction(win_rate, avg_win, avg_loss):
    """Kelly criterion: f* = p - (1-p)/(W/L)."""
    if avg_loss == 0:
        return win_rate if win_rate > 0 else 0.0
    wl = avg_win / avg_loss
    if wl <= 0:
        return 0.0
    f = win_rate - (1 - win_rate) / wl
    return max(0.0, min(f, 1.0))  # cap at 1.0


def load_fact_store_edges(store_path):
    """Extract D1 edges and labels from a fact store JSON."""
    with open(store_path, "r") as f:
        data = json.load(f)
    doc = data.get("_documentation", {})
    thresh = doc.get("dimension_thresholds_definition", {})
    # Find the edges/labels keys dynamically
    edges_key = None
    labels_key = None
    for k in thresh:
        if k.endswith("_edges_d1"):
            edges_key = k
        if k.endswith("_labels_d1"):
            labels_key = k
    if edges_key is None or labels_key is None:
        raise KeyError(f"Could not find edges_d1/labels_d1 in {store_path}. Keys: {list(thresh.keys())}")
    return thresh[edges_key], thresh[labels_key]


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

print("═" * 80)
print("  CONJUNCIÓN MACRO: CREDIT + YIELD + DXY")
print("  Cluster FLUJO/MACRO — Estrés macro → SPY forward 20d")
print("═" * 80)

store = TimescaleDataStore()

# ── Load SPY ──
print("\n📡 Cargando SPY...")
spy_raw = store.load_bars("SPY", "1d")["close"].copy()
spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()
spy_rets = spy.pct_change().shift(-1)  # next-day return

print(f"   SPY: {spy.index[0].date()} → {spy.index[-1].date()} ({len(spy)} bars)")

# ── Load CREDIT (CREDIT_RATIO = HYG/LQD) ──
print("\n📡 Cargando CREDIT (CREDIT_RATIO)...")
credit_raw = store.load_bars("CREDIT_RATIO", "1d")["close"].copy()
credit_raw.index = pd.to_datetime(credit_raw.index).normalize()
credit = credit_raw[~credit_raw.index.duplicated(keep="last")].sort_index()

# CREDIT edges from fact store
credit_edges, credit_labels = load_fact_store_edges(
    "/root/botero-trade/backend/modules/entry_decision/domain/rules/credit_fact_store.json"
)
print(f"   CREDIT edges: {[f'{e:.4f}' for e in credit_edges]}")
print(f"   CREDIT labels: {credit_labels}")
print(f"   CREDIT bars: {len(credit)}")

# ── Load YIELD (TNX - IRX spread) ──
print("\n📡 Cargando YIELD (TNX - IRX)...")
tnx = store.load_bars("TNX", "1d")["close"].copy()
irx = store.load_bars("IRX", "1d")["close"].copy()
tnx.index = pd.to_datetime(tnx.index).normalize()
irx.index = pd.to_datetime(irx.index).normalize()
tnx = tnx[~tnx.index.duplicated(keep="last")].sort_index()
irx = irx[~irx.index.duplicated(keep="last")].sort_index()

# Align and compute spread
common_tnx_irx = sorted(set(tnx.index) & set(irx.index))
spread = tnx.loc[common_tnx_irx] - irx.loc[common_tnx_irx]

# YIELD edges from fact store
yield_edges, yield_labels = load_fact_store_edges(
    "/root/botero-trade/backend/modules/entry_decision/domain/rules/yield_curve_fact_store.json"
)
print(f"   YIELD edges: {[f'{e:.4f}' for e in yield_edges]}")
print(f"   YIELD labels: {yield_labels}")
print(f"   YIELD spread bars: {len(spread)}")

# ── Load DXY ──
print("\n📡 Cargando DXY...")
dxy_raw = store.load_bars("DXY", "1d")["close"].copy()
dxy_raw.index = pd.to_datetime(dxy_raw.index).normalize()
dxy = dxy_raw[~dxy_raw.index.duplicated(keep="last")].sort_index()

# DXY edges from fact store
dxy_edges, dxy_labels = load_fact_store_edges(
    "/root/botero-trade/backend/modules/entry_decision/domain/rules/dxy_fact_store.json"
)
print(f"   DXY edges: {[f'{e:.4f}' for e in dxy_edges]}")
print(f"   DXY labels: {dxy_labels}")
print(f"   DXY bars: {len(dxy)}")

# ── ALIGN ALL to common dates ──
print("\n🔗 Alineando fechas comunes...")
common_dates = sorted(
    set(spy.index) &
    set(credit.index) &
    set(spread.index) &
    set(dxy.index)
)
print(f"   Fechas comunes: {len(common_dates)} ({common_dates[0].date()} → {common_dates[-1].date()})")

# Align all series
spy_aligned = spy.loc[common_dates]
credit_aligned = credit.loc[common_dates]
spread_aligned = spread.loc[common_dates]
dxy_aligned = dxy.loc[common_dates]

# ── CLASSIFY D1 for each station ──
print("\n🏷️  Clasificando D1 para cada estación...")

credit_d1 = compute_d1(credit_aligned.values, credit_edges, credit_labels)
yield_d1  = compute_d1(spread_aligned.values, yield_edges, yield_labels)
dxy_d1    = compute_d1(dxy_aligned.values, dxy_edges, dxy_labels)

# ── BUILD CONJUNCTION MASK ──
print("\n🔀 Construyendo máscara de conjunción...")

credit_stress_mask = np.isin(credit_d1, STRESS_BINS["CREDIT"])
yield_stress_mask  = np.isin(yield_d1, STRESS_BINS["YIELD"])
dxy_stress_mask    = np.isin(dxy_d1, STRESS_BINS["DXY"])

# Count how many stress signals are active
conjunction_count = (
    credit_stress_mask.astype(int) +
    yield_stress_mask.astype(int) +
    dxy_stress_mask.astype(int)
)

# ── FORWARD 20d RETURNS ──
print(f"\n📊 Calculando SPY forward {FORWARD}d returns...")

n = len(common_dates)
forward_rets = np.full(n, np.nan)
for i in range(n):
    end_i = i + FORWARD
    if end_i < n:
        start_px = spy_aligned.iloc[i]
        end_px = spy_aligned.iloc[end_i]
        forward_rets[i] = (end_px / start_px - 1) * 100
    # else: leave NaN (insufficient forward data)

# ── ANALYZE BY CONJUNCTION LEVEL ──
print("\n" + "═" * 80)
print("  RESULTADOS POR NIVEL DE CONJUNCIÓN")
print("═" * 80)

results = {}
baseline_all = forward_rets[~np.isnan(forward_rets)]

for level in range(4):  # 0, 1, 2, 3
    mask = (conjunction_count == level) & (~np.isnan(forward_rets))
    n_signals = mask.sum()
    rets = forward_rets[mask]

    label = f"CONJUNCION_{level}"
    if n_signals == 0:
        print(f"\n  {label}: 0 observaciones — sin datos")
        results[label] = {"n": 0}
        continue

    # Win rate
    win_mask = rets > 0
    n_wins = win_mask.sum()
    n_losses = (~win_mask).sum()
    wr, wr_lo, wr_hi = bootstrap_ci_winrate(win_mask)

    # Return distribution
    mean_ret, mean_lo, mean_hi = bootstrap_ci(rets)
    median_ret = float(np.median(rets))
    std_ret = float(np.std(rets))
    min_ret = float(np.min(rets))
    max_ret = float(np.max(rets))
    p5 = float(np.percentile(rets, 5))
    p95 = float(np.percentile(rets, 95))
    skew_ret = float(pd.Series(rets).skew()) if len(rets) >= 3 else np.nan

    # Wins/Losses breakdown
    wins_rets = rets[win_mask]
    losses_rets = rets[~win_mask]
    avg_win = float(wins_rets.mean()) if len(wins_rets) > 0 else 0.0
    avg_loss = float(abs(losses_rets.mean())) if len(losses_rets) > 0 else 0.0
    max_win = float(wins_rets.max()) if len(wins_rets) > 0 else 0.0
    max_loss = float(losses_rets.min()) if len(losses_rets) > 0 else 0.0

    # Profit factor
    total_gain = float(wins_rets.sum()) if len(wins_rets) > 0 else 0.0
    total_loss = float(abs(losses_rets.sum())) if len(losses_rets) > 0 else 1e-10
    profit_factor = total_gain / total_loss if total_loss > 0 else float("inf")

    # Kelly
    kelly = kelly_fraction(wr, avg_win, avg_loss)

    # Expected value (CI95 already computed)
    ev = mean_ret

    # Intra-period max drawdown
    # For each signal bar, compute max DD within forward window
    intradds = []
    for i in np.where(mask)[0]:
        end_i = i + FORWARD
        if end_i < n:
            window = spy_aligned.iloc[i:end_i+1]
            entry_px = window.iloc[0]
            worst_px = window.min()
            dd = (worst_px / entry_px - 1) * 100
            intradds.append(dd)
    intradds = np.array(intradds)
    mean_intradd = float(np.mean(intradds)) if len(intradds) > 0 else np.nan
    max_intradd = float(np.min(intradds)) if len(intradds) > 0 else np.nan
    p5_intradd = float(np.percentile(intradds, 5)) if len(intradds) > 0 else np.nan

    # Loss streaks
    streaks = []
    current = 0
    for r in rets:
        if r <= 0:
            current += 1
        else:
            if current > 0:
                streaks.append(current)
            current = 0
    if current > 0:
        streaks.append(current)
    max_streak = max(streaks) if streaks else 0
    mean_streak = float(np.mean(streaks)) if streaks else 0.0

    # ── Print ──
    print(f"\n{'─' * 80}")
    print(f"  {label} — N = {n_signals}")
    print(f"  {'─' * 80}")
    print(f"  Win Rate:          {wr:.1%}  CI95 [{wr_lo:.1%}, {wr_hi:.1%}]")
    print(f"  Wins/Losses:       {n_wins}W / {n_losses}L")
    print(f"  Return 20d:        μ = {mean_ret:+.2f}%  CI95 [{mean_lo:+.2f}%, {mean_hi:+.2f}%]")
    print(f"                     med = {median_ret:+.2f}%  σ = {std_ret:.2f}%")
    print(f"                     P5 = {p5:+.2f}%  P95 = {p95:+.2f}%")
    print(f"                     min = {min_ret:+.2f}%  max = {max_ret:+.2f}%  skew = {skew_ret:+.2f}")
    print(f"  Avg Win/Loss:      +{avg_win:.2f}% / -{avg_loss:.2f}%")
    print(f"  Max Win/Loss:      +{max_win:.2f}% / {max_loss:+.2f}%")
    print(f"  Profit Factor:     {profit_factor:.3f}")
    print(f"  Kelly:             {kelly:.4f}")
    print(f"  EV (μ):            {ev:+.2f}%")
    print(f"  Intra DD 20d:      μ = {mean_intradd:+.2f}%  max = {max_intradd:+.2f}%  P5 = {p5_intradd:+.2f}%")
    print(f"  Loss Streaks:      max = {max_streak}  μ = {mean_streak:.1f}")

    # Per-signal-combination breakdown (for levels 1 and 2)
    if level == 1:
        print(f"\n  ── Desglose por estación individual ──")
        station_masks_list = [
            ("CREDIT", credit_stress_mask),
            ("YIELD",  yield_stress_mask),
            ("DXY",    dxy_stress_mask),
        ]
        for station, station_mask in station_masks_list:
            # Build mask for "only THIS station, none of the other two"
            other_masks = [m for name, m in station_masks_list if name != station]
            solo_mask = station_mask & (~other_masks[0]) & (~other_masks[1]) & (~np.isnan(forward_rets))
            sn = solo_mask.sum()
            if sn >= 3:
                s_rets = forward_rets[solo_mask]
                s_wr = (s_rets > 0).mean()
                s_mean, s_lo, s_hi = bootstrap_ci(s_rets)
                print(f"     {station:10s}: N={sn:4d}  WR={s_wr:.1%}  μ={s_mean:+.2f}%  CI95[{s_lo:+.2f}%,{s_hi:+.2f}%]")

    if level == 2:
        print(f"\n  ── Desglose por par ──")
        pairs = [
            ("CREDIT+YIELD", credit_stress_mask & yield_stress_mask),
            ("CREDIT+DXY",   credit_stress_mask & dxy_stress_mask),
            ("YIELD+DXY",    yield_stress_mask & dxy_stress_mask),
        ]
        for pname, pair_mask in pairs:
            # only this pair, third station not active
            third_mask = ~(
                (credit_stress_mask & yield_stress_mask) |
                (credit_stress_mask & dxy_stress_mask) |
                (yield_stress_mask & dxy_stress_mask)
            )
            # Better: exact pair mask = pair_mask AND NOT the third
            if pname == "CREDIT+YIELD":
                exact_mask = pair_mask & (~dxy_stress_mask) & (~np.isnan(forward_rets))
            elif pname == "CREDIT+DXY":
                exact_mask = pair_mask & (~yield_stress_mask) & (~np.isnan(forward_rets))
            else:  # YIELD+DXY
                exact_mask = pair_mask & (~credit_stress_mask) & (~np.isnan(forward_rets))

            pn = exact_mask.sum()
            if pn >= 3:
                p_rets = forward_rets[exact_mask]
                p_wr = (p_rets > 0).mean()
                p_mean, p_lo, p_hi = bootstrap_ci(p_rets)
                print(f"     {pname:15s}: N={pn:4d}  WR={p_wr:.1%}  μ={p_mean:+.2f}%  CI95[{p_lo:+.2f}%,{p_hi:+.2f}%]")

    # Store results
    results[label] = {
        "n": int(n_signals),
        "n_wins": int(n_wins),
        "n_losses": int(n_losses),
        "win_rate": round(wr, 4),
        "win_rate_ci95": [round(wr_lo, 4), round(wr_hi, 4)],
        "return_mean": round(mean_ret, 3),
        "return_ci95": [round(mean_lo, 3), round(mean_hi, 3)],
        "return_median": round(median_ret, 3),
        "return_std": round(std_ret, 3),
        "return_min": round(min_ret, 3),
        "return_max": round(max_ret, 3),
        "return_p5": round(p5, 3),
        "return_p95": round(p95, 3),
        "return_skew": round(skew_ret, 3) if not np.isnan(skew_ret) else None,
        "avg_win": round(avg_win, 3),
        "avg_loss": round(avg_loss, 3),
        "max_win": round(max_win, 3),
        "max_loss": round(max_loss, 3),
        "profit_factor": round(profit_factor, 3),
        "kelly": round(kelly, 4),
        "ev_pct": round(ev, 3),
        "intra_dd_mean": round(mean_intradd, 3),
        "intra_dd_max": round(max_intradd, 3),
        "intra_dd_p5": round(p5_intradd, 3),
        "max_loss_streak": max_streak,
        "mean_loss_streak": round(mean_streak, 2),
    }

# ── BASELINE (ALL days) ──
print(f"\n{'═' * 80}")
print(f"  BASELINE (todos los días)")
print(f"{'═' * 80}")
base_n = len(baseline_all)
base_wr = (baseline_all > 0).mean()
base_mean, base_lo, base_hi = bootstrap_ci(baseline_all)
print(f"  N = {base_n}")
print(f"  WR = {base_wr:.1%}  μ = {base_mean:+.2f}%  CI95 [{base_lo:+.2f}%, {base_hi:+.2f}%]")
print(f"  σ = {np.std(baseline_all):.2f}%  med = {np.median(baseline_all):+.2f}%")

# ── RELATIVE vs BASELINE ──
print(f"\n{'═' * 80}")
print(f"  DELTA vs BASELINE (μ = {base_mean:+.2f}%)")
print(f"{'═' * 80}")
for level in range(1, 4):
    label = f"CONJUNCION_{level}"
    r = results.get(label, {})
    if r.get("n", 0) > 0:
        delta = r["return_mean"] - base_mean
        delta_pct = (r["return_mean"] / base_mean - 1) * 100 if base_mean != 0 else float("inf")
        sig = "⚠️  BAJISTA" if delta < -base_hi - base_lo else ("🟢 ALCISTA" if delta > base_hi - base_lo else "≈ NEUTRAL")
        print(f"  {label}: Δμ = {delta:+.2f}%  ({delta_pct:+.1f}% rel)  {sig}  N={r['n']}")

# ── SAVE JSON ──
output_path = "/root/botero-trade/data/research/conjuncion_macro_results.json"
output = {
    "metadata": {
        "script": "conjuncion_macro.py",
        "generated": datetime.now().isoformat(),
        "forward_days": FORWARD,
        "n_boot": N_BOOT,
        "ci": CI,
        "date_range": f"{common_dates[0].date()} → {common_dates[-1].date()}",
        "n_common_days": len(common_dates),
        "stress_bins": STRESS_BINS,
        "credit_edges": [round(e, 4) for e in credit_edges],
        "yield_edges": [round(e, 4) for e in yield_edges],
        "dxy_edges": [round(e, 4) for e in dxy_edges],
    },
    "baseline": {
        "n": base_n,
        "mean_return_20d_pct": round(base_mean, 3),
        "ci95": [round(base_lo, 3), round(base_hi, 3)],
        "win_rate": round(base_wr, 4),
    },
    "conjunctions": results,
    "counts": {
        f"conjuncion_{i}": int((conjunction_count == i).sum())
        for i in range(4)
    },
}

with open(output_path, "w") as f:
    json.dump(output, f, indent=2)

store.close()

print(f"\n{'═' * 80}")
print(f"  ✅ Resultados guardados en: {output_path}")
print(f"{'═' * 80}")
print("\nDONE.")