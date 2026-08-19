#!/usr/bin/env python3
"""
S5×SV5 MATRIX VALIDATION — Botero Trade
========================================
VALIDA EMPÍRICAMENTE la matriz S5×SV5 documentada en volume_breadth_calculator.py.

S5  = S5TW  diff(3)  — velocidad del breadth de PRECIO (% stocks > 20-DMA)
SV5 = SV5TW diff(3)  — velocidad del breadth de VOLUMEN (% stocks vol expanding)

4 CUADRANTES (documentados como reglas binarias, NUNCA medidos):
  S5↑ + SV5↑ = "Rally con convicción" (compradores agresivos)
  S5↑ + SV5↓ = "Rally sin convicción" (vulnerable)
  S5↓ + SV5↑ = "Venta con convicción" (vendedores agresivos)
  S5↓ + SV5↓ = "Deriva apática" (sin urgencia)

Métrica: SPY zz25 pivotes. Por cuadrante: %bear (próximo leg), %cascade_50, N, CI95 bootstrap.
NO etiquetas binarias — solo probabilidades + CI95 + N.

Dato mata relato — todo validado con datos reales.
"""

import sys
import json
from pathlib import Path
from datetime import timedelta, datetime

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository

# ── Helpers ──────────────────────────────────────────────────────────────────

def boot_ci(arr, ci=95, n_boot=3000, rng_seed=42):
    """Bootstrap CI para media de array."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)
    if n < 5:
        return float(np.nan), float(np.nan), float(np.nan), n
    rng = np.random.default_rng(rng_seed)
    means = np.zeros(n_boot)
    for i in range(n_boot):
        sample = rng.choice(arr, size=n, replace=True)
        means[i] = sample.mean()
    means.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(means, lo)), float(np.percentile(means, hi)), n


def boot_diff_ci(arr_a, arr_b, ci=95, n_boot=3000, rng_seed=42):
    """Bootstrap CI para diferencia de medias A - B."""
    arr_a = np.asarray(arr_a, float)
    arr_b = np.asarray(arr_b, float)
    arr_a = arr_a[~np.isnan(arr_a)]
    arr_b = arr_b[~np.isnan(arr_b)]
    if len(arr_a) < 5 or len(arr_b) < 5:
        return float(np.nan), float(np.nan), float(np.nan)
    rng = np.random.default_rng(rng_seed)
    diffs = np.zeros(n_boot)
    for i in range(n_boot):
        sa = rng.choice(arr_a, size=len(arr_a), replace=True)
        sb = rng.choice(arr_b, size=len(arr_b), replace=True)
        diffs[i] = sa.mean() - sb.mean()
    diffs.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr_a.mean() - arr_b.mean()), float(np.percentile(diffs, lo)), float(np.percentile(diffs, hi))


def norm_idx(s):
    """Normalize OHLCV bar index to date objects."""
    s = s.copy()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s


def pct_fmt(mean, lo, hi):
    """Format as percentage with CI."""
    if any(np.isnan(v) for v in [mean, lo, hi]):
        return "  n/a"
    return f"{mean:.1%}  CI95=[{lo:.1%}, {hi:.1%}]"


# ── Load Data ────────────────────────────────────────────────────────────────

print("=" * 80)
print("  S5×SV5 MATRIX VALIDATION — SPY zz25 Pivotes")
print("  S5 = diff(3) de S5TW, SV5 = diff(3) de SV5TW")
print("=" * 80)
print()

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

# ── Pivots & Targets ─────────────────────────────────────────────────────────

legs25 = repo.get_confirmed_legs("SPY", "zz25")
legs50 = repo.get_confirmed_legs("SPY", "zz50")

# Cascade = SAME-TYPE leg of next scale starts within ±3 days
# (authoritative: v3_fact_table_engine.py `diffs <= 3d & next_types == s_type`)
starts50_min = set(pd.to_datetime(l.start_timestamp).date() for l in legs50 if l.start_type == "MIN")
starts50_max = set(pd.to_datetime(l.start_timestamp).date() for l in legs50 if l.start_type == "MAX")

df = pd.DataFrame([
    {
        "start_timestamp": l.start_timestamp,
        "start_type": l.start_type,
        "prev_leg_return": l.prev_leg_return,
    }
    for l in legs25
])
df["pivot_date"] = pd.to_datetime(df["start_timestamp"]).dt.date

# Targets
df["leg_bear"] = (df["start_type"] == "MAX").astype(int)  # MAX→bear (down leg)
df["cascade_50"] = df.apply(
    lambda r: int(any(
        r["pivot_date"] + timedelta(days=i) in (starts50_max if r["start_type"] == "MAX" else starts50_min)
        for i in range(-3, 4)
    )),
    axis=1,
)

print(f"SPY zz25 legs: {len(df)}")
print(f"SPY zz50 legs: {len(legs50)}")
print(f"Cascade_50 unconditional (same-type ±3d): {df['cascade_50'].mean():.2%}")
print(f"%bear unconditional (MAX pivots): {df['leg_bear'].mean():.2%}")
print()

# ── Breadth Indicators ──────────────────────────────────────────────────────

s5_raw = store.load_bars("S5TW", "1d")["close"].copy()
sv5_raw = store.load_bars("SV5TW", "1d")["close"].copy()

s5 = norm_idx(s5_raw)
sv5 = norm_idx(sv5_raw)

# Velocity = diff(3): current minus 3 days ago
s5_vel = s5.diff(3)   # positive = breadth accelerating up
sv5_vel = sv5.diff(3)  # positive = volume breadth accelerating up

# Build lookup dicts (date → velocity)
s5_vel_dict = {d.date() if hasattr(d, "date") else d: float(v) for d, v in s5_vel.items() if not pd.isna(v)}
sv5_vel_dict = {d.date() if hasattr(d, "date") else d: float(v) for d, v in sv5_vel.items() if not pd.isna(v)}

# ── Build Observations ──────────────────────────────────────────────────────

obs = []
for _, row in df.iterrows():
    pd_ = row["pivot_date"]

    # Normalize pivot_date to match indicator index
    if isinstance(pd_, pd.Timestamp):
        pd_ = pd_.date()

    s5v = s5_vel_dict.get(pd_)
    sv5v = sv5_vel_dict.get(pd_)

    if s5v is None or sv5v is None:
        continue  # missing indicator data at this pivot

    s5_up = 1 if s5v > 0 else 0
    sv5_up = 1 if sv5v > 0 else 0
    quadrant = (
        "S5↑SV5↑" if (s5_up and sv5_up) else
        "S5↑SV5↓" if (s5_up and not sv5_up) else
        "S5↓SV5↑" if (not s5_up and sv5_up) else
        "S5↓SV5↓"
    )

    obs.append({
        "pivot_date": pd_,
        "start_type": row["start_type"],
        "leg_bear": int(row["leg_bear"]),
        "cascade_50": int(row["cascade_50"]),
        "s5_vel": s5v,
        "sv5_vel": sv5v,
        "s5_up": s5_up,
        "sv5_up": sv5_up,
        "quadrant": quadrant,
    })

df_obs = pd.DataFrame(obs)

# Check for zero-velocity edge case
n_zero_s5 = (df_obs["s5_vel"] == 0).sum()
n_zero_sv5 = (df_obs["sv5_vel"] == 0).sum()
if n_zero_s5 > 0 or n_zero_sv5 > 0:
    print(f"⚠  Zero-velocity pivots: S5={n_zero_s5}, SV5={n_zero_sv5} (classified as ↓)")
    print()

print(f"Pivots with S5TW+SV5TW data: {len(df_obs)} / {len(df)} total ({len(df_obs)/len(df)*100:.1f}%)")
print(f"Date range: {df_obs['pivot_date'].min()} → {df_obs['pivot_date'].max()}")
print(f"SV5TW data starts ~1999 → pre-1999 pivots excluded")
print()

# ═══════════════════════════════════════════════════════════════════════════════
#  UNCONDITIONAL BASELINES
# ═══════════════════════════════════════════════════════════════════════════════

bear_mean, bear_lo, bear_hi, bear_n = boot_ci(df_obs["leg_bear"])
c50_mean, c50_lo, c50_hi, c50_n = boot_ci(df_obs["cascade_50"])

print("UNCONDITIONAL BASELINES (todos los pivotes):")
print(f"  %bear (próximo leg):    {pct_fmt(bear_mean, bear_lo, bear_hi)}  N={bear_n}")
print(f"  %cascade_50 (→ zz50):   {pct_fmt(c50_mean, c50_lo, c50_hi)}  N={c50_n}")
print()

# ═══════════════════════════════════════════════════════════════════════════════
#  S5×SV5 MATRIX — 4 CUADRANTES
# ═══════════════════════════════════════════════════════════════════════════════

quadrants = ["S5↑SV5↑", "S5↑SV5↓", "S5↓SV5↑", "S5↓SV5↓"]
quadrant_labels = {
    "S5↑SV5↑": "Rally con convicción (documentado: compradores agresivos → continuación alcista)",
    "S5↑SV5↓": "Rally sin convicción (documentado: rally vulnerable)",
    "S5↓SV5↑": "Venta con convicción (documentado: vendedores agresivos → continuación bajista)",
    "S5↓SV5↓": "Deriva apática (documentado: sin urgencia, baja cascada)",
}

print("═" * 80)
print("  4 CUADRANTES S5×SV5 — %bear + %cascade_50 + CI95 bootstrap 3000")
print("═" * 80)

results = {}
for q in quadrants:
    sub = df_obs[df_obs["quadrant"] == q]
    n = len(sub)
    pct = n / len(df_obs)

    b_mean, b_lo, b_hi, b_n = boot_ci(sub["leg_bear"])
    c_mean, c_lo, c_hi, c_n = boot_ci(sub["cascade_50"])

    # Difference from unconditional
    b_diff, b_diff_lo, b_diff_hi = boot_diff_ci(sub["leg_bear"], df_obs["leg_bear"])
    c_diff, c_diff_lo, c_diff_hi = boot_diff_ci(sub["cascade_50"], df_obs["cascade_50"])

    results[q] = {
        "N": n, "pct": pct,
        "bear_mean": b_mean, "bear_lo": b_lo, "bear_hi": b_hi,
        "c50_mean": c_mean, "c50_lo": c_lo, "c50_hi": c_hi,
        "bear_diff": b_diff, "bear_diff_lo": b_diff_lo, "bear_diff_hi": b_diff_hi,
        "c50_diff": c_diff, "c50_diff_lo": c_diff_lo, "c50_diff_hi": c_diff_hi,
    }

    print(f"\n  {q}  —  {quadrant_labels[q]}")
    print(f"  {'─' * 70}")
    print(f"  N = {n}  ({pct:.1%} de todos los pivotes)")
    print(f"  %bear:        {pct_fmt(b_mean, b_lo, b_hi)}")
    if not np.isnan(b_diff):
        print(f"    vs baseline: {b_diff:+.1%}  CI95=[{b_diff_lo:+.1%}, {b_diff_hi:+.1%}]")
    print(f"  %cascade_50:  {pct_fmt(c_mean, c_lo, c_hi)}")
    if not np.isnan(c_diff):
        print(f"    vs baseline: {c_diff:+.1%}  CI95=[{c_diff_lo:+.1%}, {c_diff_hi:+.1%}]")

# Chi-square test: are the quadrants different?
print(f"\n{'─' * 80}")
print("  CHI-SQUARE: independencia cuadrante × cascade_50")
ct = pd.crosstab(df_obs["quadrant"], df_obs["cascade_50"])
chi2, p_chi2, dof, expected = chi2_contingency(ct)
print(f"  χ² = {chi2:.2f}, p = {p_chi2:.4f}, dof = {dof}")
if p_chi2 < 0.05:
    print(f"  → SIGNIFICATIVO: las tasas de cascada difieren por cuadrante")
else:
    print(f"  → NO significativo: los cuadrantes no difieren en cascada")

ct_bear = pd.crosstab(df_obs["quadrant"], df_obs["leg_bear"])
chi2_bear, p_bear, dof_bear, _ = chi2_contingency(ct_bear)
print(f"\n  CHI-SQUARE: independencia cuadrante × %bear")
print(f"  χ² = {chi2_bear:.2f}, p = {p_bear:.4f}, dof = {dof_bear}")
if p_bear < 0.05:
    print(f"  → SIGNIFICATIVO: el %bear difiere por cuadrante")
else:
    print(f"  → NO significativo: los cuadrantes no difieren en %bear")

# ═══════════════════════════════════════════════════════════════════════════════
#  BSI (S5TW) SOLO — ¿agrega SV5 valor?
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 80}")
print("  BSI (S5TW) SOLO — por dirección S5 (sin desglosar por SV5)")
print("═" * 80)

s5_up_all = df_obs[df_obs["s5_up"] == 1]
s5_down_all = df_obs[df_obs["s5_up"] == 0]

b_s5u, b_s5u_lo, b_s5u_hi, _ = boot_ci(s5_up_all["leg_bear"])
c_s5u, c_s5u_lo, c_s5u_hi, _ = boot_ci(s5_up_all["cascade_50"])
b_s5d, b_s5d_lo, b_s5d_hi, _ = boot_ci(s5_down_all["leg_bear"])
c_s5d, c_s5d_lo, c_s5d_hi, _ = boot_ci(s5_down_all["cascade_50"])

print(f"  S5↑ (breadth subiendo): N={len(s5_up_all)}")
print(f"    %bear:       {pct_fmt(b_s5u, b_s5u_lo, b_s5u_hi)}")
print(f"    %cascade_50: {pct_fmt(c_s5u, c_s5u_lo, c_s5u_hi)}")
print(f"  S5↓ (breadth bajando): N={len(s5_down_all)}")
print(f"    %bear:       {pct_fmt(b_s5d, b_s5d_lo, b_s5d_hi)}")
print(f"    %cascade_50: {pct_fmt(c_s5d, c_s5d_lo, c_s5d_hi)}")

# Gap S5↑ vs S5↓
bear_gap, bear_gap_lo, bear_gap_hi = boot_diff_ci(
    s5_down_all["leg_bear"], s5_up_all["leg_bear"]
)
c50_gap, c50_gap_lo, c50_gap_hi = boot_diff_ci(
    s5_up_all["cascade_50"], s5_down_all["cascade_50"]
)
print(f"\n  GAP S5↓ − S5↑ en %bear:       {bear_gap:+.1%} CI95=[{bear_gap_lo:+.1%}, {bear_gap_hi:+.1%}]")
print(f"  GAP S5↑ − S5↓ en %cascade_50: {c50_gap:+.1%} CI95=[{c50_gap_lo:+.1%}, {c50_gap_hi:+.1%}]")

# ═══════════════════════════════════════════════════════════════════════════════
#  VALOR AGREGADO DE SV5 — desglose dentro de S5↑ y S5↓
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 80}")
print("  VALOR AGREGADO DE SV5 — desglose por SV5 dentro de cada dirección S5")
print("═" * 80)

for s5_label, s5_mask, s5_group in [
    ("S5↑", df_obs["s5_up"] == 1, s5_up_all),
    ("S5↓", df_obs["s5_up"] == 0, s5_down_all),
]:
    print(f"\n  ── {s5_label} (breadth de precio {('subiendo','bajando')[s5_label=='S5↓']}) ──")
    for sv_label, sv_mask in [("SV5↑", s5_group["sv5_up"] == 1), ("SV5↓", s5_group["sv5_up"] == 0)]:
        sub = s5_group[sv_mask]
        n = len(sub)
        if n < 5:
            print(f"    {s5_label}{sv_label}: N={n}  (N<5, no CI)")
            continue
        b_mean, b_lo, b_hi, _ = boot_ci(sub["leg_bear"])
        c_mean, c_lo, c_hi, _ = boot_ci(sub["cascade_50"])

        # Difference within S5 group (SV5↑ vs SV5↓)
        if sv_label == "SV5↑":
            other = s5_group[s5_group["sv5_up"] == 0]
            b_diff, b_diff_lo, b_diff_hi = boot_diff_ci(sub["leg_bear"], other["leg_bear"])
            c_diff, c_diff_lo, c_diff_hi = boot_diff_ci(sub["cascade_50"], other["cascade_50"])
        else:
            other = s5_group[s5_group["sv5_up"] == 1]
            b_diff, b_diff_lo, b_diff_hi = boot_diff_ci(sub["leg_bear"], other["leg_bear"])
            c_diff, c_diff_lo, c_diff_hi = boot_diff_ci(sub["cascade_50"], other["cascade_50"])

        print(f"    {s5_label}{sv_label}: N={n:4d}  %bear={pct_fmt(b_mean, b_lo, b_hi)}  %cascade={pct_fmt(c_mean, c_lo, c_hi)}")
        if not np.isnan(b_diff):
            print(f"      {sv_label} vs opuesto: Δ%bear={b_diff:+.1%} CI95=[{b_diff_lo:+.1%}, {b_diff_hi:+.1%}]  Δ%cascade={c_diff:+.1%} CI95=[{c_diff_lo:+.1%}, {c_diff_hi:+.1%}]")

# ═══════════════════════════════════════════════════════════════════════════════
#  TABLA RESUMEN (JSON)
# ═══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 80}")
print("  TABLA RESUMEN (probabilidades + CI95 + N)")
print("═" * 80)

def safe_pct(v):
    return f"{v:.3f}" if not np.isnan(v) else "n/a"

table = []
# Unconditional
table.append({
    "signal": "UNCONDITIONAL", "N": int(bear_n),
    "p_bear": safe_pct(bear_mean), "p_bear_ci": f"[{safe_pct(bear_lo)}, {safe_pct(bear_hi)}]",
    "p_cascade_50": safe_pct(c50_mean), "p_c50_ci": f"[{safe_pct(c50_lo)}, {safe_pct(c50_hi)}]",
})
# S5 solo
table.append({
    "signal": "S5↑", "N": len(s5_up_all),
    "p_bear": safe_pct(b_s5u), "p_bear_ci": f"[{safe_pct(b_s5u_lo)}, {safe_pct(b_s5u_hi)}]",
    "p_cascade_50": safe_pct(c_s5u), "p_c50_ci": f"[{safe_pct(c_s5u_lo)}, {safe_pct(c_s5u_hi)}]",
})
table.append({
    "signal": "S5↓", "N": len(s5_down_all),
    "p_bear": safe_pct(b_s5d), "p_bear_ci": f"[{safe_pct(b_s5d_lo)}, {safe_pct(b_s5d_hi)}]",
    "p_cascade_50": safe_pct(c_s5d), "p_c50_ci": f"[{safe_pct(c_s5d_lo)}, {safe_pct(c_s5d_hi)}]",
})
# 4 quadrantes
for q in quadrants:
    r = results[q]
    table.append({
        "signal": q,
        "label": quadrant_labels[q],
        "N": r["N"],
        "p_bear": safe_pct(r["bear_mean"]), "p_bear_ci": f"[{safe_pct(r['bear_lo'])}, {safe_pct(r['bear_hi'])}]",
        "Δbear": safe_pct(r["bear_diff"]), "Δbear_ci": f"[{safe_pct(r['bear_diff_lo'])}, {safe_pct(r['bear_diff_hi'])}]",
        "p_cascade_50": safe_pct(r["c50_mean"]), "p_c50_ci": f"[{safe_pct(r['c50_lo'])}, {safe_pct(r['c50_hi'])}]",
        "Δcascade": safe_pct(r["c50_diff"]), "Δc50_ci": f"[{safe_pct(r['c50_diff_lo'])}, {safe_pct(r['c50_diff_hi'])}]",
    })

# Print table
header = f"{'Señal':<14} {'N':>5} {'p(bear)':>8} {'CI95 bear':>24} {'Δbear':>8} {'p(c50)':>8} {'CI95 c50':>24} {'Δc50':>8}"
print(header)
print("-" * len(header))
for row in table:
    d_bear = row.get("Δbear", "        ")
    d_c50 = row.get("Δcascade", "        ")
    print(f"{row['signal']:<14} {row['N']:>5} {row['p_bear']:>8} {row['p_bear_ci']:>24} {d_bear:>8} {row['p_cascade_50']:>8} {row['p_c50_ci']:>24} {d_c50:>8}")

# Save JSON
output = {
    "meta": {
        "script": "research/04_conjuncion_multi_estacion/s5_sv5_matrix.py",
        "description": "S5×SV5 matrix validation — SPY zz25 pivots",
        "S5_definition": "diff(3) of S5TW (% stocks above 20-DMA)",
        "SV5_definition": "diff(3) of SV5TW (% stocks with expanding volume)",
        "targets": ["leg_bear (próximo leg bajista si start_type=MAX)", "cascade_50 (±3d zz50 leg start)"],
        "bootstrap": "3000 iterations, CI95",
        "total_pivots": int(len(df)),
        "pivots_with_data": int(len(df_obs)),
        "date_range": f"{df_obs['pivot_date'].min()} → {df_obs['pivot_date'].max()}",
        "sv5tw_data_starts": "1999-01-04",
    },
    "baseline": {
        "p_bear": bear_mean, "p_bear_ci95": [bear_lo, bear_hi], "N": bear_n,
        "p_cascade_50": c50_mean, "p_c50_ci95": [c50_lo, c50_hi], "N": c50_n,
    },
    "s5_solo": {
        "S5_up": {"N": len(s5_up_all), "p_bear": b_s5u, "p_bear_ci95": [b_s5u_lo, b_s5u_hi], "p_cascade_50": c_s5u, "p_c50_ci95": [c_s5u_lo, c_s5u_hi]},
        "S5_down": {"N": len(s5_down_all), "p_bear": b_s5d, "p_bear_ci95": [b_s5d_lo, b_s5d_hi], "p_cascade_50": c_s5d, "p_c50_ci95": [c_s5d_lo, c_s5d_hi]},
        "gap_bear_S5down_S5up": bear_gap, "gap_bear_ci95": [bear_gap_lo, bear_gap_hi],
        "gap_c50_S5up_S5down": c50_gap, "gap_c50_ci95": [c50_gap_lo, c50_gap_hi],
    },
    "matrix_s5_sv5": {},
    "chi_square": {
        "cascade_50_vs_quadrant": {"chi2": chi2, "p": p_chi2, "dof": dof, "significant_05": p_chi2 < 0.05},
        "bear_vs_quadrant": {"chi2": chi2_bear, "p": p_bear, "dof": dof_bear, "significant_05": p_bear < 0.05},
    },
    "quadrant_probabilities": {},
}
for q in quadrants:
    r = results[q]
    output["matrix_s5_sv5"][q] = {
        "label": quadrant_labels[q],
        "N": r["N"], "pct": r["pct"],
        "p_bear": r["bear_mean"], "p_bear_ci95": [r["bear_lo"], r["bear_hi"]],
        "Δbear_vs_baseline": r["bear_diff"], "Δbear_ci95": [r["bear_diff_lo"], r["bear_diff_hi"]],
        "p_cascade_50": r["c50_mean"], "p_c50_ci95": [r["c50_lo"], r["c50_hi"]],
        "Δc50_vs_baseline": r["c50_diff"], "Δc50_ci95": [r["c50_diff_lo"], r["c50_diff_hi"]],
    }
    output["quadrant_probabilities"][q] = r["pct"]

json_path = Path("/root/botero-trade/data/research/s5_sv5_matrix_results.json")
with open(json_path, "w") as f:
    json.dump(output, f, indent=2, default=lambda x: float(x) if isinstance(x, (np.floating,)) else str(x))

print(f"\nResultados guardados: {json_path}")
print("═" * 80)
print("  FIN")
print("═" * 80)