#!/usr/bin/env python3
"""
VIX×S5×SV5 — MATRIZ TRIPLE (3 dimensiones de convicción)
=========================================================
¿SV5 agrega una TERCERA dimensión (convicción del volumen) que discrimina
los casos ambiguos de los 4 regímenes VIX×S5?

EJES (velocidades diff(3), pitfall #37/#56 — cada uno su ticker correcto):
  VIX  = diff(3) de VIX   — "sentir" (miedo acelerando vs resolviendo)
  S5   = diff(3) de S5TW  — "hacer"  (breadth de precio: % stocks > 20-DMA)
  SV5  = diff(3) de SV5TW — "convicción" (breadth de volumen: % stocks volumen en expansión)

4 REGÍMENES VIX×S5 (sentir × hacer):
  1. MIEDO SIN VENTA     = VIX↑ S5↑   (miedo pero breadth OK)
  2. MIEDO CON VENTA      = VIX↑ S5↓   (miedo + venta real)
  3. CALMA CON AMPLITUD   = VIX↓ S5↑   (calma + breadth recuperando)
  4. CALMA SIN CONVICCIÓN = VIX↓ S5↓   (calma + breadth apagado)

PREGUNTA CLAVE (casos ambiguos): ¿SV5↑ vs SV5↓ cambia el pronóstico DENTRO de
cada régimen VIX×S5?
  - MIEDO SIN VENTA + SV5↑  → ¿rebote confirmado (volumen fuerte)?
  - MIEDO SIN VENTA + SV5↓  → ¿rebote falso (sin volumen)?
  - MIEDO CON VENTA + SV5↑  → ¿capitulación (volumen alto, final del miedo)?
  - MIEDO CON VENTA + SV5↓  → ¿deriva bajista (sin volumen, sin urgencia)?

MÉTRICA: 3 escalas zigzag (zz25/zz50/zz75) + horizontes fijos (5/10/20/40d).
Por celda: %bear (dirección próximo leg), %cascade (misma escala→siguiente),
retorno forward SPY, win rate, wins/losses separados, CI95 bootstrap, N.

Dato mata relato — todo medido, nada supuesto. NO etiquetas binarias.
"""

import sys
import json
from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

N_BOOT = 3000
SEED = 42
FW_HORIZONS = [5, 10, 20, 40]

# ── Bootstrap helpers ────────────────────────────────────────────────────────

def _rng():
    return np.random.default_rng(SEED)


def boot_ci(arr, ci=95, n_boot=N_BOOT):
    """CI95 para media (proporción) vía bootstrap."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 5:
        return float(np.nan), float(np.nan), float(np.nan), n
    rng = _rng()
    means = np.empty(n_boot)
    for i in range(n_boot):
        means[i] = rng.choice(arr, size=n, replace=True).mean()
    means.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(means, lo)), float(np.percentile(means, hi)), n


def boot_diff_ci(arr_a, arr_b, ci=95, n_boot=N_BOOT):
    """CI95 para diferencia de medias A - B."""
    arr_a = np.asarray(arr_a, float); arr_a = arr_a[~np.isnan(arr_a)]
    arr_b = np.asarray(arr_b, float); arr_b = arr_b[~np.isnan(arr_b)]
    if len(arr_a) < 5 or len(arr_b) < 5:
        return float(np.nan), float(np.nan), float(np.nan), float(np.nan)
    rng = _rng()
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        sa = rng.choice(arr_a, size=len(arr_a), replace=True).mean()
        sb = rng.choice(arr_b, size=len(arr_b), replace=True).mean()
        diffs[i] = sa - sb
    diffs.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return (float(arr_a.mean() - arr_b.mean()),
            float(np.percentile(diffs, lo)), float(np.percentile(diffs, hi)),
            float(np.mean(diffs > 0)))


def pct(mean, lo, hi):
    if mean is None or (isinstance(mean, float) and np.isnan(mean)):
        return "     n/a"
    return f"{mean:.1%} [{lo:.1%},{hi:.1%}]"


def norm_idx(s):
    s = s.copy()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s


# ── Load data ────────────────────────────────────────────────────────────────

print("═" * 90)
print("  VIX×S5×SV5 MATRIZ TRIPLE — ¿SV5 discrimina los regímenes ambiguos?")
print("═" * 90)

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

# Zigzag legs at 3 scales
legs = {}
for scale in ["zz25", "zz50", "zz75"]:
    legs[scale] = repo.get_confirmed_legs("SPY", scale)

def legs_df(scale):
    return pd.DataFrame([
        {
            "start_timestamp": l.start_timestamp,
            "start_type": l.start_type,
            "start_price": l.start_price,
            "end_price": l.end_price,
        }
        for l in legs[scale]
    ])

# Cascade target: same-type leg of next scale starts within ±3d (authoritative v3_fact_table_engine)
def build_cascade(scale, next_scale):
    """Return dict pivot_date(bool) -> cascade to next_scale."""
    nl = legs[next_scale]
    starts_min = {pd.to_datetime(l.start_timestamp).date() for l in nl if l.start_type == "MIN"}
    starts_max = {pd.to_datetime(l.start_timestamp).date() for l in nl if l.start_type == "MAX"}
    def f(row):
        d = pd.to_datetime(row["start_timestamp"]).date()
        s = starts_max if row["start_type"] == "MAX" else starts_min
        return int(any(d + timedelta(days=i) in s for i in range(-3, 4)))
    return f

dfs = {}
for scale in ["zz25", "zz50", "zz75"]:
    d = legs_df(scale)
    d["pivot_date"] = pd.to_datetime(d["start_timestamp"]).dt.date
    d["leg_bear"] = (d["start_type"] == "MAX").astype(int)
    # leg return (from this pivot to the next opposite pivot = this leg's return)
    d["leg_return"] = (d["end_price"] / d["start_price"] - 1.0)
    dfs[scale] = d

# Cascade to next larger scale
dfs["zz25"]["cascade_next"] = dfs["zz25"].apply(build_cascade("zz25", "zz50"), axis=1)
dfs["zz25"]["cascade_75"] = dfs["zz25"].apply(build_cascade("zz25", "zz75"), axis=1)
dfs["zz50"]["cascade_next"] = dfs["zz50"].apply(build_cascade("zz50", "zz75"), axis=1)
dfs["zz75"]["cascade_next"] = None  # no larger scale

print(f"\nSPY legs: zz25={len(dfs['zz25'])}, zz50={len(dfs['zz50'])}, zz75={len(dfs['zz75'])}")
print(f"  cascade_50 (zz25→zz50 same-type ±3d) unconditional: {dfs['zz25']['cascade_next'].mean():.1%}")
print(f"  cascade_75 (zz25→zz75 same-type ±3d) unconditional: {dfs['zz25']['cascade_75'].mean():.1%}")
print(f"  cascade zz50→zz75 unconditional: {dfs['zz50']['cascade_next'].mean():.1%}")

# Indicators
vix_raw = store.load_bars("VIX", "1d")["close"].copy()
s5_raw = store.load_bars("S5TW", "1d")["close"].copy()
sv5_raw = store.load_bars("SV5TW", "1d")["close"].copy()

vix = norm_idx(vix_raw)
s5 = norm_idx(s5_raw)
sv5 = norm_idx(sv5_raw)

print(f"\nVIX:  {vix.index[0].date()} → {vix.index[-1].date()} ({len(vix)} bars)")
print(f"S5TW: {s5.index[0].date()} → {s5.index[-1].date()} ({len(s5)} bars)")
print(f"SV5TW:{sv5.index[0].date()} → {sv5.index[-1].date()} ({len(sv5)} bars)")

# Velocidades diff(3)
vix_vel = vix.diff(3)
s5_vel = s5.diff(3)
sv5_vel = sv5.diff(3)

# SPY bars for forward returns
spy_raw = store.load_bars("SPY", "1d")["close"].copy()
spy = norm_idx(spy_raw)
store.close()

print(f"SPY:  {spy.index[0].date()} → {spy.index[-1].date()} ({len(spy)} bars)")

# Align all 4 series on common dates
common = sorted(set(vix.index) & set(s5.index) & set(sv5.index) & set(spy.index))
print(f"\nFechas alineadas (VIX ∩ S5TW ∩ SV5TW ∩ SPY): {len(common)}")

vix_a = vix.reindex(common)
s5_a = s5.reindex(common)
sv5_a = sv5.reindex(common)
spy_a = spy.reindex(common)
vix_vel_a = vix_vel.reindex(common)
s5_vel_a = s5_vel.reindex(common)
sv5_vel_a = sv5_vel.reindex(common)

spy_idx = {d: i for i, d in enumerate(common)}
spy_values = spy_a.values

# ── Classification helpers ───────────────────────────────────────────────────

def classify(vix_v, s5_v, sv5_v):
    vix_up = 1 if vix_v > 0 else 0
    s5_up = 1 if s5_v > 0 else 0
    sv5_up = 1 if sv5_v > 0 else 0
    return vix_up, s5_up, sv5_up

def cell_name(vix_up, s5_up, sv5_up):
    return (
        ("VIX↑" if vix_up else "VIX↓") +
        ("S5↑" if s5_up else "S5↓") +
        ("SV5↑" if sv5_up else "SV5↓")
    )

REGIME = {
    (1, 1): "1 MIEDO SIN VENTA    (VIX↑ S5↑)",
    (1, 0): "2 MIEDO CON VENTA     (VIX↑ S5↓)",
    (0, 1): "3 CALMA CON AMPLITUD  (VIX↓ S5↑)",
    (0, 0): "4 CALMA SIN CONVICCIÓN(VIX↓ S5↓)",
}

# Lookup dicts date -> velocity (for pivot classification)
vix_vel_dict = {d.date(): float(v) for d, v in vix_vel_a.items() if not pd.isna(v)}
s5_vel_dict = {d.date(): float(v) for d, v in s5_vel_a.items() if not pd.isna(v)}
sv5_vel_dict = {d.date(): float(v) for d, v in sv5_vel_a.items() if not pd.isna(v)}

def tag_pivot(row):
    d = row["pivot_date"]
    vv = vix_vel_dict.get(d)
    sv = s5_vel_dict.get(d)
    svv = sv5_vel_dict.get(d)
    if vv is None or sv is None or svv is None:
        return None
    vix_up, s5_up, sv5_up = classify(vv, sv, svv)
    return {
        "vix_up": vix_up, "s5_up": s5_up, "sv5_up": sv5_up,
        "cell": cell_name(vix_up, s5_up, sv5_up),
        "regime": REGIME[(vix_up, s5_up)],
    }

# Tag every pivot at each scale
for scale in ["zz25", "zz50", "zz75"]:
    tags = dfs[scale].apply(tag_pivot, axis=1)
    dfs[scale]["cell"] = [t["cell"] if t else None for t in tags]
    dfs[scale]["vix_up"] = [t["vix_up"] if t else None for t in tags]
    dfs[scale]["s5_up"] = [t["s5_up"] if t else None for t in tags]
    dfs[scale]["sv5_up"] = [t["sv5_up"] if t else None for t in tags]
    dfs[scale]["regime"] = [t["regime"] if t else None for t in tags]

CELLS = [
    "VIX↑S5↑SV5↑", "VIX↑S5↑SV5↓",
    "VIX↑S5↓SV5↑", "VIX↑S5↓SV5↓",
    "VIX↓S5↑SV5↑", "VIX↓S5↑SV5↓",
    "VIX↓S5↓SV5↑", "VIX↓S5↓SV5↓",
]

# ═══════════════════════════════════════════════════════════════════════════════
# PARTE A — MATRIZ 8 CELDAS EN CADA ESCALA ZIGZAG (dirección + cascada)
# ═══════════════════════════════════════════════════════════════════════════════

scale_targets = {
    "zz25": ("cascade_next", "cascade_50 (zz25→zz50)"),
    "zz50": ("cascade_next", "cascade (zz50→zz75)"),
    "zz75": (None, None),
}

zigzag_results = {}

for scale in ["zz25", "zz50", "zz75"]:
    d = dfs[scale].dropna(subset=["cell"]).copy()
    d["cell"] = d["cell"].astype(str)
    n_total = len(d)
    if n_total == 0:
        continue

    print(f"\n{'═' * 90}")
    print(f"  ESCALA {scale.upper()} — matriz 8 celdas (N={n_total} pivotes con datos)")
    print(f"{'═' * 90}")

    base_bear = d["leg_bear"].mean()
    _, b_lo, b_hi, _ = boot_ci(d["leg_bear"])
    print(f"  Baseline %bear (MAX pivots): {pct(base_bear, b_lo, b_hi)}")

    casc_col, casc_label = scale_targets[scale]
    if casc_col:
        base_casc = d[casc_col].mean()
        _, c_lo, c_hi, _ = boot_ci(d[casc_col])
        print(f"  Baseline %cascade ({casc_label}): {pct(base_casc, c_lo, c_hi)}")

    print(f"\n  {'Celda':<14} {'N':>5} {'%piv':>6} | {'%bear':>18} | {'%cascade':>20}")
    print("  " + "-" * 72)

    scale_result = {"N_total": n_total, "cells": {}}

    for cell in CELLS:
        sub = d[d["cell"] == cell]
        n = len(sub)
        if n == 0:
            continue
        pct_of = n / n_total

        bm, blo, bhi, bn = boot_ci(sub["leg_bear"])
        row = f"  {cell:<14} {n:>5} {pct_of:>5.1%} | {pct(bm, blo, bhi):>18} |"
        cell_out = {"N": n, "pct": pct_of, "bear": bm, "bear_ci": [blo, bhi]}

        if casc_col:
            cm, clo, chi, cn = boot_ci(sub[casc_col])
            row += f" {pct(cm, clo, chi):>20}"
            cell_out["cascade"] = cm
            cell_out["cascade_ci"] = [clo, chi]
        else:
            row += f" {'—':>20}"

        print(row)
        scale_result["cells"][cell] = cell_out

    zigzag_results[scale] = scale_result

    # Chi-square: do the 8 cells differ on direction and cascade?
    ct_bear = pd.crosstab(d["cell"], d["leg_bear"])
    if ct_bear.shape[0] > 1 and ct_bear.shape[1] > 1:
        chi2, pv, dof, _ = chi2_contingency(ct_bear)
        print(f"\n  χ² 8 celdas × %bear: {chi2:.1f}, p={pv:.4f} {'(SIG)' if pv < 0.05 else '(no sig)'}")
    if casc_col:
        ct_c = pd.crosstab(d["cell"], d[casc_col])
        if ct_c.shape[0] > 1 and ct_c.shape[1] > 1:
            chi2, pv, dof, _ = chi2_contingency(ct_c)
            print(f"  χ² 8 celdas × %cascade: {chi2:.1f}, p={pv:.4f} {'(SIG)' if pv < 0.05 else '(no sig)'}")

# ═══════════════════════════════════════════════════════════════════════════════
# PARTE B — LA PREGUNTA CENTRAL: ¿SV5 discrimina dentro de cada régimen VIX×S5?
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n\n{'═' * 90}")
print("  PARTE B — ¿SV5 DISCRIMINA DENTRO DE CADA RÉGIMEN VIX×S5?")
print("  (SV5↑ vs SV5↓ en la misma celda VIX×S5, por escala)")
print(f"{'═' * 90}")

discrimination = {}

for scale in ["zz25", "zz50", "zz75"]:
    d = dfs[scale].dropna(subset=["cell"]).copy()
    if len(d) == 0:
        continue
    casc_col, _ = scale_targets[scale]

    print(f"\n  ── {scale.upper()} ──")
    print(f"  {'Régimen VIX×S5':<30} {'SV5':>4} {'N':>5} | {'%bear':>18} | {'%cascade':>20}")

    disc_scale = {}
    for (vix_up, s5_up), regime_label in REGIME.items():
        reg = d[(d["vix_up"] == vix_up) & (d["s5_up"] == s5_up)]
        if len(reg) < 10:
            continue
        sv5u = reg[reg["sv5_up"] == 1]
        sv5d = reg[reg["sv5_up"] == 0]

        bm_u, blo_u, bhi_u, _ = boot_ci(sv5u["leg_bear"]) if len(sv5u) >= 5 else (np.nan, np.nan, np.nan, np.nan)
        bm_d, blo_d, bhi_d, _ = boot_ci(sv5d["leg_bear"]) if len(sv5d) >= 5 else (np.nan, np.nan, np.nan, np.nan)
        cm_u = cm_d = None

        diff_bear, dblo, dbhi, p_pos = boot_diff_ci(sv5u["leg_bear"], sv5d["leg_bear"])

        print(f"  {regime_label:<30} {'↑':>4} {len(sv5u):>5} | {pct(bm_u, blo_u, bhi_u):>18} |", end="")
        if casc_col:
            cm_u, clo_u, chi_u, _ = boot_ci(sv5u[casc_col]) if len(sv5u) >= 5 else (np.nan, np.nan, np.nan, np.nan)
            print(f" {pct(cm_u, clo_u, chi_u):>20}")
        else:
            print()

        print(f"  {'':<30} {'↓':>4} {len(sv5d):>5} | {pct(bm_d, blo_d, bhi_d):>18} |", end="")
        if casc_col:
            cm_d, clo_d, chi_d, _ = boot_ci(sv5d[casc_col]) if len(sv5d) >= 5 else (np.nan, np.nan, np.nan, np.nan)
            print(f" {pct(cm_d, clo_d, chi_d):>20}")
        else:
            print()

        diff_casc, dclo, dchi = None, None, None
        if casc_col and len(sv5u) >= 5 and len(sv5d) >= 5:
            diff_casc, dclo, dchi, _ = boot_diff_ci(sv5u[casc_col], sv5d[casc_col])

        # SIGNIFICANCE of SV5 split
        sig = ""
        if not np.isnan(diff_bear):
            sig = f"  Δbear(SV5↑−SV5↓)={diff_bear:+.1%} CI95=[{dblo:+.1%},{dbhi:+.1%}] p(SV5↑>SV5↓)={p_pos:.0%}"
            if dblo > 0 or dbhi < 0:
                sig += "  ← CI excluye 0 (SIG)"
            else:
                sig += "  (CI cruza 0)"
        print(f"  {sig}")
        if diff_casc is not None and dclo is not None and dchi is not None:
            print(f"  {'':<34} Δcascade(SV5↑−SV5↓)={diff_casc:+.1%} CI95=[{dclo:+.1%},{dchi:+.1%}]")

        disc_scale[regime_label] = {
            "N_sv5_up": len(sv5u), "N_sv5_down": len(sv5d),
            "bear_up": bm_u, "bear_down": bm_d,
            "diff_bear": diff_bear, "diff_bear_ci": [dblo, dbhi], "p_sv5up_gt": p_pos,
            "cascade_up": cm_u if casc_col and len(sv5u) >= 5 else None,
            "cascade_down": cm_d if casc_col and len(sv5d) >= 5 else None,
            "diff_cascade": diff_casc,
        }

    discrimination[scale] = disc_scale

# ═══════════════════════════════════════════════════════════════════════════════
# PARTE C — HORIZONTES FIJOS (forward SPY, barra a barra, NO zigzag)
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n\n{'═' * 90}")
print("  PARTE C — HORIZONTES FIJOS (forward SPY 5/10/20/40d, todas las barras)")
print("  Regímenes VIX×S5×SV5 → retorno forward + wins/losses separados")
print(f"{'═' * 90}")

# Build bar-level classification
bar_cells = []
for i, d in enumerate(common):
    vv = vix_vel_a.iloc[i]
    sv = s5_vel_a.iloc[i]
    svv = sv5_vel_a.iloc[i]
    if pd.isna(vv) or pd.isna(sv) or pd.isna(svv):
        continue
    vix_up, s5_up, sv5_up = classify(vv, sv, svv)
    bar_cells.append({
        "idx": i,
        "date": d,
        "cell": cell_name(vix_up, s5_up, sv5_up),
        "regime": REGIME[(vix_up, s5_up)],
        "vix_up": vix_up, "s5_up": s5_up, "sv5_up": sv5_up,
    })

bars = pd.DataFrame(bar_cells)
n_bars = len(bars)
print(f"\n  Barras clasificadas (con 3 indicadores): {n_bars}")
print(f"  Rango: {bars['date'].min().date()} → {bars['date'].max().date()}")

# Forward returns per bar
def fwd_returns(idx, h):
    fi = idx + h
    if fi >= len(spy_values):
        return None
    return spy_values[fi] / spy_values[idx] - 1.0

# Dedup signals (≥10 bars spacing) per cell for a cleaner signal-level stat
MIN_SPACING = 10

def build_cell_signals(cell_mask_df, horizon):
    """Deduped signals within a cell mask, with forward returns at horizon."""
    idxs = bars.index[cell_mask_df].tolist()
    out = []
    last = -MIN_SPACING - 1
    for bi in idxs:
        si = int(bars.loc[bi, "idx"])
        if si - last >= MIN_SPACING:
            r = fwd_returns(si, horizon)
            if r is not None:
                out.append(r)
            last = si
    return out

def winloss_stats(returns):
    """Returns dict with win rate, mean, wins/losses distributions, PF, Kelly."""
    r = np.asarray(returns, float)
    r = r[~np.isnan(r)]
    n = len(r)
    if n < 5:
        return None
    wins = r[r > 0]
    losses = r[r <= 0]
    wr = len(wins) / n
    avg_win = wins.mean() if len(wins) else 0.0
    avg_loss = losses.mean() if len(losses) else 0.0
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else float('inf')
    wl = avg_win / abs(avg_loss) if avg_loss != 0 else float('inf')
    kelly = max(0.0, wr - (1 - wr) / wl) if wl != float('inf') and wl > 0 else float('nan')
    return {
        "N": n, "win_rate": wr, "mean": r.mean(),
        "median": float(np.median(r)),
        "wins": {"P25": float(np.percentile(wins, 25)), "P50": float(np.percentile(wins, 50)),
                 "P75": float(np.percentile(wins, 75)), "P90": float(np.percentile(wins, 90)),
                 "max": float(wins.max())} if len(wins) else {},
        "losses": {"P25": float(np.percentile(losses, 25)), "P50": float(np.percentile(losses, 50)),
                   "P75": float(np.percentile(losses, 75)), "P90": float(np.percentile(losses, 90)),
                   "min": float(losses.min())} if len(losses) else {},
        "n_wins": int(len(wins)), "n_losses": int(len(losses)),
        "profit_factor": float(pf), "kelly": float(kelly),
    }

fixed_results = {}
H = 20  # headline horizon

for regime_label in REGIME.values():
    reg = bars[bars["regime"] == regime_label]
    fixed_results[regime_label] = {}
    print(f"\n  ── {regime_label} ──")
    for sv5_up in [1, 0]:
        sub = reg[reg["sv5_up"] == sv5_up]
        lab = "SV5↑" if sv5_up else "SV5↓"
        sig = build_cell_signals(bars.index.isin(sub.index), H)
        if not sig:
            print(f"    {lab}: N=0")
            continue
        wl = winloss_stats(sig)
        if wl is None:
            print(f"    {lab}: N={len(sig)} (N<5, sin CI)")
            continue
        wrm, wrlo, wrhi, _ = boot_ci([1.0 if x > 0 else 0.0 for x in sig])
        mm, mlo, mhi, _ = boot_ci(sig)
        print(f"    {lab}: N={wl['N']:>4}  WR20d={wrm:.1%} [{wrlo:.1%},{wrhi:.1%}]  "
              f"ret20d={mm:+.2%} [{mlo:+.2%},{mhi:+.2%}]  PF={wl['profit_factor']:.2f}  "
              f"Kelly={wl['kelly']:.2f}")
        print(f"          wins  P25/P50/P75/P90/max = {wl['wins'].get('P25',0):+.2%}/{wl['wins'].get('P50',0):+.2%}/{wl['wins'].get('P75',0):+.2%}/{wl['wins'].get('P90',0):+.2%}/{wl['wins'].get('max',0):+.2%}")
        print(f"          losses P25/P50/P75/P90/min = {wl['losses'].get('P25',0):+.2%}/{wl['losses'].get('P50',0):+.2%}/{wl['losses'].get('P75',0):+.2%}/{wl['losses'].get('P90',0):+.2%}/{wl['losses'].get('min',0):+.2%}")
        fixed_results[regime_label][lab] = {
            "N": wl["N"], "win_rate_20d": wrm, "win_rate_ci": [wrlo, wrhi],
            "ret_20d": mm, "ret_ci": [mlo, mhi],
            "profit_factor": wl["profit_factor"], "kelly": wl["kelly"],
            "wins": wl["wins"], "losses": wl["losses"],
            "n_wins": wl["n_wins"], "n_losses": wl["n_losses"],
        }

    # SV5 split significance at 20d
    sig_u = build_cell_signals(bars.index.isin(reg[reg["sv5_up"] == 1].index), H)
    sig_d = build_cell_signals(bars.index.isin(reg[reg["sv5_up"] == 0].index), H)
    if len(sig_u) >= 5 and len(sig_d) >= 5:
        diff, dlo, dhi, p_pos = boot_diff_ci(sig_u, sig_d)
        print(f"    Δret20d(SV5↑−SV5↓) = {diff:+.2%} CI95=[{dlo:+.2%},{dhi:+.2%}] p(SV5↑>SV5↓)={p_pos:.0%} "
              f"{'← SIG' if (dlo>0 or dhi<0) else '(CI cruza 0)'}")

# ═══════════════════════════════════════════════════════════════════════════════
# Guardar JSON
# ═══════════════════════════════════════════════════════════════════════════════

output = {
    "meta": {
        "script": "research/04_conjuncion_multi_estacion/s5_vix_sv5_triple.py",
        "description": "VIX×S5×SV5 triple matrix — does SV5 (volume breadth) add a 3rd discriminative dimension?",
        "axes": {
            "VIX": "diff(3) of VIX (fear velocity)",
            "S5": "diff(3) of S5TW (price breadth velocity)",
            "SV5": "diff(3) of SV5TW (volume breadth velocity)",
        },
        "scales": ["zz25", "zz50", "zz75"],
        "fixed_horizons_days": FW_HORIZONS,
        "bootstrap": f"{N_BOOT} iters, CI95",
        "n_aligned_bars": n_bars,
    },
    "zigzag_matrix": zigzag_results,
    "sv5_discrimination_within_regime": discrimination,
    "fixed_horizon_20d": fixed_results,
}

def _json_safe(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, float) and (np.isnan(o) or np.isinf(o)):
        return None
    return str(o)

json_path = Path("/root/botero-trade/data/research/s5_vix_sv5_triple_results.json")
with open(json_path, "w") as f:
    json.dump(output, f, indent=2, default=_json_safe)

print(f"\n\nResultados guardados: {json_path}")
print("═" * 90)
print("  FIN")
print("═" * 90)
