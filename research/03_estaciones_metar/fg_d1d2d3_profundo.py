#!/usr/bin/env python3
"""
ESTUDIO PROFUNDO FG — D1×D2×D3 completo.
===========================================
Botero Trade — FG (Fear & Greed) station.
Analiza los 82 estados poblados D1×D2×D3 (de 150 teóricos).

SECCIONES:
  0. Listar estados D1×D2×D3 con N≥10 (bar count)
  1. Por cada D1 (6 niveles): split D2 (velocidad) y D3 (volatilidad)
  2. Matriz D2×D3 dentro de EXTREME_FEAR y EXTREME_GREED:
     - dirección del próximo leg (3 escalas zigzag)
     - forward fijo 5/10/20/40d (bar-level)
     - wins/losses separados, CI95, N por celda
  3. D2 flip en FG: ¿funciona como timing (como en VIX)?
  4. D3 en FG: ¿discrimina cascade (FG −15pp del pitfall #55)?

Metodología: carga barras SPY+FG de TimescaleDB, clasifica cada día con
FGLookupAdapter (adapters del proyecto), calcula retornos forward y cascade.
"""
import sys, json, warnings
from pathlib import Path
from datetime import timedelta
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ttest_1samp, ttest_ind

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.rules.fg_lookup import FGLookupAdapter

# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def boot_ci(arr, ci=95, n_boot=3000, random_state=42):
    """Bootstrap CI for mean. Returns (mean, lo, hi)."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(random_state)
    means = [rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(n_boot)]
    means = np.sort(means)
    lo_p = (100 - ci) / 2
    hi_p = 100 - lo_p
    return float(arr.mean()), float(np.percentile(means, lo_p)), float(np.percentile(means, hi_p))

def wins_losses(arr):
    """Separate wins/losses from array. Returns dict with N_win, N_loss, win_dist, loss_dist, wr, PF, EV."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return {"N": 0, "N_win": 0, "N_loss": 0, "WR": np.nan, "PF": np.nan, "EV": np.nan}
    w = arr[arr > 0]
    l = arr[arr < 0]
    n_win, n_loss = len(w), len(l)
    wr = n_win / len(arr) if len(arr) > 0 else np.nan
    pf = w.sum() / abs(l.sum()) if len(l) > 0 and abs(l.sum()) > 1e-10 else (np.inf if len(w) > 0 else np.nan)
    ev = arr.mean()
    return {
        "N": len(arr), "N_win": n_win, "N_loss": n_loss,
        "WR": wr,
        "PF": pf,
        "EV": ev,
        "avg_win": w.mean() if len(w) > 0 else np.nan,
        "avg_loss": l.mean() if len(l) > 0 else np.nan,
        "p25_win": np.percentile(w, 25) if len(w) >= 4 else np.nan,
        "p50_win": np.median(w) if len(w) > 0 else np.nan,
        "p75_win": np.percentile(w, 75) if len(w) >= 4 else np.nan,
        "p10_loss": np.percentile(l, 10) if len(l) >= 10 else np.nan,
        "p50_loss": np.median(l) if len(l) > 0 else np.nan,
        "p90_loss": np.percentile(l, 90) if len(l) >= 10 else np.nan,
        "min_loss": l.min() if len(l) > 0 else np.nan,
        "max_win": w.max() if len(w) > 0 else np.nan,
        "mean": arr.mean(),
        "median": np.median(arr),
        "std": arr.std(),
    }

def ic(a, b):
    """Spearman IC."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = ~np.isnan(a) & ~np.isnan(b)
    if m.sum() < 5 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
        return np.nan, np.nan, int(m.sum())
    r, p = spearmanr(a[m], b[m])
    return float(r), float(p), int(m.sum())

# ═══════════════════════════════════════════════════════════════════════════════
# 0. LOAD DATA
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 100)
print("  ESTUDIO PROFUNDO FG — D1×D2×D3")
print("  Botero Trade · dato mata relato")
print("=" * 100)

# ── Fact store ───────────────────────────────────────────────────────────────
adapt = FGLookupAdapter()
fact = adapt._data
states = fact["states"]
doc = fact["_documentation"]
dd = doc["dimension_thresholds_definition"]

d1_labels = dd["fg_labels_d1"]
d2_labels = dd["fg_labels_d2"]
d3_labels = dd["fg_labels_d3"]

print(f"\n  FG fact store: {len(states)} states populated (150 teóricos)")
print(f"  D1 edges: {[round(e,2) for e in dd['fg_edges_d1']]}")
print(f"  D1 labels: {d1_labels}")
print(f"  D2 edges: {[round(e,2) for e in dd['fg_edges_d2']]}")
print(f"  D2 labels: {d2_labels}")
print(f"  D3 edges: {[round(e,2) for e in dd['fg_edges_d3']]}")
print(f"  D3 labels: {d3_labels}")

# ── DB: bars + zigzag legs ───────────────────────────────────────────────────
store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

spy_raw = store.load_bars("SPY", "1d")["close"].copy()
fg_raw = store.load_bars("FG", "1d")["close"].copy()

# Normalize indices
def _naive(s):
    s = s.copy()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()

spy = _naive(spy_raw)
fg = _naive(fg_raw)

print(f"\n  SPY: {spy.index[0].date()} → {spy.index[-1].date()} ({len(spy)} bars)")
print(f"  FG:  {fg.index[0].date()}  → {fg.index[-1].date()}  ({len(fg)} bars)")

# Zigzag legs
legs25 = sorted(repo.get_confirmed_legs("SPY", "zz25"), key=lambda l: l.start_timestamp)
legs50 = sorted(repo.get_confirmed_legs("SPY", "zz50"), key=lambda l: l.start_timestamp)
legs75 = sorted(repo.get_confirmed_legs("SPY", "zz75"), key=lambda l: l.start_timestamp)

starts50 = {(pd.to_datetime(l.start_timestamp).date(), l.start_type) for l in legs50}
starts75 = {(pd.to_datetime(l.start_timestamp).date(), l.start_type) for l in legs75}

print(f"  zigzag legs: zz25={len(legs25)}  zz50={len(legs50)}  zz75={len(legs75)}")

store.close()

# ── Compute FG D2/D3 on bars ────────────────────────────────────────────────
fg_d2 = fg.diff(3).copy()
s2, s10 = fg.rolling(2).std(), fg.rolling(10).std()
fg_d3 = (s2 / s10).replace([np.inf, -np.inf], np.nan).fillna(1.0).copy()

# ── Classify each bar ────────────────────────────────────────────────────────
common = sorted(set(fg.index) & set(spy.index))
print(f"\n  Common dates (FG ∩ SPY): {len(common)}")

records = []
for dt in common:
    fg_val = float(fg.loc[dt])
    fg_vel = float(fg_d2.loc[dt]) if dt in fg_d2.index and not pd.isna(fg_d2.loc[dt]) else 0.0
    fg_vol = float(fg_d3.loc[dt]) if dt in fg_d3.index and not pd.isna(fg_d3.loc[dt]) else 1.0

    g = adapt.lookup_fg_guidance(val=fg_val, d3_speed=fg_vel, vol_norm=fg_vol, vol_d3=0.0)
    records.append({
        "date": dt,
        "fg_val": fg_val, "fg_vel": fg_vel, "fg_vol": fg_vol,
        "d1": g.fg_bin if g else "UNCLASSIFIED",
        "d2": g.velocity_vector if g else "UNCLASSIFIED",
        "d3": g.pivot_vector if g else "UNCLASSIFIED",
        "state_key": g.state_key if g else "",
        "n_bar": g.n if g else 0,
    })

df_bar = pd.DataFrame(records).set_index("date")
print(f"  Bars classified: {len(df_bar)}")
print(f"  D1 distribution:\n{df_bar['d1'].value_counts().to_string()}")

# ── SPY forward returns (bar-level) ─────────────────────────────────────────
for k in [5, 10, 20, 40]:
    df_bar[f"spy_fwd{k}"] = spy.pct_change(k).shift(-k)
    df_bar[f"spy_fwd{k}_win"] = (df_bar[f"spy_fwd{k}"] > 0).astype(float)

# ── Pivot-level: FG state at each zz25 pivot ────────────────────────────────
pivot_records = []
for leg in legs25:
    pd_dt = pd.to_datetime(leg.start_timestamp).tz_localize(None).normalize()
    if pd_dt not in df_bar.index:
        continue
    row = df_bar.loc[pd_dt]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]

    # Cascade (same-type ±3d)
    cascade_50 = int(any(
        (pd_dt.date() + timedelta(days=i), leg.start_type) in starts50
        for i in range(-3, 4)
    ))
    cascade_75 = int(any(
        (pd_dt.date() + timedelta(days=i), leg.start_type) in starts75
        for i in range(-3, 4)
    ))

    pivot_records.append({
        "pivot_date": pd_dt.date(),
        "start_type": leg.start_type,
        "next_is_bull": int(leg.start_type == "MIN"),
        "prev_leg_return": leg.prev_leg_return,
        "prev_leg_duration": leg.prev_leg_duration,
        "cascade_50": cascade_50,
        "cascade_75": cascade_75,
        "d1": row["d1"],
        "d2": row["d2"],
        "d3": row["d3"],
        "state_key": row["state_key"],
        "n_bar": row["n_bar"],
        "fg_val": row["fg_val"],
        "fg_vel": row["fg_vel"],
        "fg_vol": row["fg_vol"],
    })

df_piv = pd.DataFrame(pivot_records)
print(f"\n  Pivots zz25 with FG classification: {len(df_piv)}")
print(f"  Cascade_50 rate (same-type ±3d): {df_piv['cascade_50'].mean()*100:.1f}%")
print(f"  Cascade_75 rate (same-type ±3d): {df_piv['cascade_75'].mean()*100:.1f}%")
print(f"  Next leg DIRECTION: BULL={df_piv['next_is_bull'].mean()*100:.1f}% (MIN→UP={df_piv['start_type'].value_counts().get('MIN',0)})")

# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 0: LISTAR ESTADOS D1×D2×D3 CON N≥10 (bar count)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("  SECCIÓN 0: ESTADOS D1×D2×D3 CON N≥10 (bar count)")
print("=" * 100)

print(f"\n  D1 labels: {d1_labels}")
print(f"  D2 labels: {d2_labels}")
print(f"  D3 labels: {d3_labels}")
print(f"\n  Total states in fact store: {len(states)}")

# Build a table: D1 × D2 × D3 → n_bar, n_zigzag (total zigzag legs across zz25/zz50/zz75)
print(f"\n  States with bar count N≥10:\n")
print(f"  {'D1':<22} {'D2':<28} {'D3':<30} {'N_bar':>6} {'N_zigzag25':>10} {'p_bull25':>8} {'ev_net25':>9}")
print(f"  {'-'*22} {'-'*28} {'-'*30} {'-'*6} {'-'*10} {'-'*8} {'-'*9}")

n_ge_10 = 0
n_total_zigzag = 0
for d1 in d1_labels:
    for d2 in d2_labels:
        for d3 in d3_labels:
            sk = f"{d1}__{d2}__{d3}"
            st = states.get(sk)
            if st is None:
                continue
            n_bar = st.get("n", 0)
            zk25 = st.get("zigzag_kinematic", {}).get("zz25", {})
            n_zig = zk25.get("n_pos", 0) + zk25.get("n_neg", 0)
            p_bull = zk25.get("p_bull", np.nan)
            ev_net = zk25.get("ev_net", np.nan)

            if n_bar >= 10:
                n_ge_10 += 1
                n_total_zigzag += n_zig
                p_str = f"{p_bull*100:6.1f}%" if not np.isnan(p_bull) else "    n/a"
                ev_str = f"{ev_net:+7.2f}%" if not np.isnan(ev_net) else "     n/a"
                print(f"  {d1:<22} {d2:<28} {d3:<30} {n_bar:>6} {n_zig:>10} {p_str:>8} {ev_str:>9}")

print(f"\n  Estados con N_bar≥10: {n_ge_10} / {len(states)}")
print(f"  Total zigzag legs en esos estados: {n_total_zigzag}")

# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 1: POR CADA D1 — SPLIT POR D2 Y D3
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("  SECCIÓN 1: POR CADA D1 — D2 (dirección) y D3 (confianza/cascade)")
print("=" * 100)

# 1A: Split por D2 (velocidad) → ¿discrimina dirección?
print("\n  ── 1A: D1×D2 → ¿D2 discrimina DIRECCIÓN del próximo leg? ──")
for d1l in d1_labels:
    sub = df_piv[df_piv["d1"] == d1l]
    if len(sub) < 5:
        continue
    print(f"\n    D1 = {d1l}  (N_piv={len(sub)}):")
    print(f"    {'D2 bin':<28} {'N':>5} {'%BULL':>7} {'c50_rate':>9} {'c75_rate':>9} {'p_bull zk25':>10}")
    print(f"    {'-'*28} {'-'*5} {'-'*7} {'-'*9} {'-'*9} {'-'*10}")

    overall_bull = sub["next_is_bull"].mean()
    overall_c50 = sub["cascade_50"].mean()
    for d2l in d2_labels:
        cell_p = sub[sub["d2"] == d2l]
        if len(cell_p) < 3:
            continue
        # Also get zigzag_kinematic p_bull from fact store for this state
        # Aggregate zk25 p_bull per D2 bin across D3
        pb_bull = cell_p["next_is_bull"].mean()
        c50 = cell_p["cascade_50"].mean()
        c75 = cell_p["cascade_75"].mean()
        print(f"    {d2l:<28} {len(cell_p):>5} {pb_bull*100:>6.1f}% {c50*100:>8.1f}% {c75*100:>8.1f}%")

    print(f"    {'ALL D2':<28} {len(sub):>5} {overall_bull*100:>6.1f}% {overall_c50*100:>8.1f}%")

    # Test: does D2 discriminate direction? (chi2-like: max-min gap)
    bulls = {}
    for d2l in sub["d2"].unique():
        cell = sub[sub["d2"] == d2l]
        if len(cell) >= 3:
            bulls[d2l] = cell["next_is_bull"].mean()
    if len(bulls) >= 2:
        gap = max(bulls.values()) - min(bulls.values())
        # Bootstrap the gap
        rng = np.random.default_rng(42)
        gaps_boot = []
        labels = sub["d2"].values
        target = sub["next_is_bull"].values
        for _ in range(2000):
            shuffled = rng.choice(target, size=len(target), replace=False)
            b_ = {}
            for lb in set(labels):
                mask = labels == lb
                if mask.sum() >= 3:
                    b_[lb] = shuffled[mask].mean()
            if len(b_) >= 2:
                gaps_boot.append(max(b_.values()) - min(b_.values()))
        if gaps_boot:
            p_val = (np.array(gaps_boot) >= gap).mean()
            print(f"    Δmax−min = {gap*100:.1f}pp (bootstrap p={p_val:.4f})")

# 1B: Split por D3 (volatilidad) → ¿discrimina cascade?
print("\n  ── 1B: D1×D3 → ¿D3 discrimina CASCADE? ──")
for d1l in d1_labels:
    sub = df_piv[df_piv["d1"] == d1l]
    if len(sub) < 5:
        continue
    print(f"\n    D1 = {d1l}  (N_piv={len(sub)}):")
    print(f"    {'D3 bin':<30} {'N':>5} {'c50_rate':>9} {'c75_rate':>9} {'Δc50 vs baseline':>15}")
    print(f"    {'-'*30} {'-'*5} {'-'*9} {'-'*9} {'-'*15}")

    baseline_c50 = sub["cascade_50"].mean()
    for d3l in d3_labels:
        cell_p = sub[sub["d3"] == d3l]
        if len(cell_p) < 3:
            continue
        c50 = cell_p["cascade_50"].mean()
        c75 = cell_p["cascade_75"].mean()
        dc50 = (c50 - baseline_c50) * 100
        print(f"    {d3l:<30} {len(cell_p):>5} {c50*100:>8.1f}% {c75*100:>8.1f}% {dc50:>+13.1f}pp")

    print(f"    {'BASELINE (ALL D3)':<30} {len(sub):>5} {baseline_c50*100:>8.1f}%")

# Global D3→cascade (all D1)
print(f"\n  ── 1B GLOBAL: D3→CASCADE (todos los D1) ──")
print(f"  N_pivots={len(df_piv)}")
baseline_all = df_piv["cascade_50"].mean()
print(f"  {'D3 bin':<30} {'N':>5} {'c50':>8} {'Δpp':>8} {'BULL%':>7}")
for d3l in d3_labels:
    cell = df_piv[df_piv["d3"] == d3l]
    if len(cell) < 5:
        continue
    c50 = cell["cascade_50"].mean()
    dc = (c50 - baseline_all) * 100
    bull = cell["next_is_bull"].mean()
    print(f"  {d3l:<30} {len(cell):>5} {c50*100:>7.1f}% {dc:>+7.1f}pp {bull*100:>6.1f}%")

# Higher resolution: D3 terciles within each D1
print(f"\n  ── 1B FINE: D3 global terciles → cascade (all D1) ──")
d3_vals = df_piv["fg_vol"].dropna().values
p33, p67 = np.percentile(d3_vals, [33, 67])
print(f"  D3 (vol_norm) percentiles: P33={p33:.3f}  P67={p67:.3f}")
df_piv["d3_tercil"] = "MID"
df_piv.loc[df_piv["fg_vol"] < p33, "d3_tercil"] = "LOW (comprimido)"
df_piv.loc[df_piv["fg_vol"] > p67, "d3_tercil"] = "HIGH (caos)"

for t in ["LOW (comprimido)", "MID", "HIGH (caos)"]:
    cell = df_piv[df_piv["d3_tercil"] == t]
    if len(cell) < 5:
        continue
    c50 = cell["cascade_50"].mean()
    dc = (c50 - baseline_all) * 100
    print(f"  {t:<20} N={len(cell):>4}  c50={c50*100:.1f}%  Δ={dc:+.1f}pp  bull={cell['next_is_bull'].mean()*100:.1f}%")

# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2: MATRIZ D2×D3 DENTRO DE EXTREME_FEAR Y EXTREME_GREED
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("  SECCIÓN 2: MATRIZ D2×D3 — EXTREME_FEAR y EXTREME_GREED")
print("=" * 100)

D2_ORDER = [
    "FAST_SPIKE_3D",
    "ACCELERATING_UP_3D",
    "STABLE_CONTINUATION_3D",
    "DECELERATING_DOWN_3D",
    "FAST_CRUSH_3D",
]
D3_ORDER = d3_labels  # already ordered from fact store

def matrix_cell_report(sub, d1_label, what="pivots"):
    """Print a full D2×D3 matrix for a given D1 subset."""
    print(f"\n  ╔══ D1 = {d1_label} ({what}) ══")

    # 2a: Zigzag direction (next_is_bull)
    print(f"  ║══ 2a: Dirección del próximo leg (p_bull zz25) ───────────────")
    for d2l in D2_ORDER:
        print(f"  ║  {d2l}")
        for d3l in D3_ORDER:
            cell = sub[(sub["d2"] == d2l) & (sub["d3"] == d3l)]
            n = len(cell)
            if n < 3:
                print(f"  ║    {d3l:<30} N={n:<4} (insuficiente)")
                continue
            bull_rate = cell["next_is_bull"].mean()
            mean_boot, lo, hi = boot_ci(cell["next_is_bull"].values)
            print(f"  ║    {d3l:<30} N={n:<4} p_bull={bull_rate*100:.0f}%  CI95=[{lo*100:.0f}%,{hi*100:.0f}%]")

    # 2b: Cascade 50
    print(f"  ║══ 2b: Cascade_50 (zz25→zz50 same-type ±3d) ──────────────────")
    for d2l in D2_ORDER:
        print(f"  ║  {d2l}")
        for d3l in D3_ORDER:
            cell = sub[(sub["d2"] == d2l) & (sub["d3"] == d3l)]
            n = len(cell)
            if n < 3:
                print(f"  ║    {d3l:<30} N={n:<4} (insuficiente)")
                continue
            c50 = cell["cascade_50"].mean()
            print(f"  ║    {d3l:<30} N={n:<4} c50={c50*100:.0f}%")

    # 2c: Cascade 75
    print(f"  ║══ 2c: Cascade_75 (zz25→zz75 same-type ±3d) ──────────────────")
    for d2l in D2_ORDER:
        print(f"  ║  {d2l}")
        for d3l in D3_ORDER:
            cell = sub[(sub["d2"] == d2l) & (sub["d3"] == d3l)]
            n = len(cell)
            if n < 3:
                print(f"  ║    {d3l:<30} N={n:<4} (insuficiente)")
                continue
            c75 = cell["cascade_75"].mean()
            print(f"  ║    {d3l:<30} N={n:<4} c75={c75*100:.0f}%")

    # 2d: Forward fixed 5/10/20/40d — bar-level wins/losses
    # Need to map from bar-level data. Use df_bar filtered by d1+d2+d3.
    for horizon in [5, 10, 20, 40]:
        col = f"spy_fwd{horizon}"
        print(f"  ║══ 2d: SPY forward {horizon}d (bar-level, wins/losses separados) ══")
        for d2l in D2_ORDER:
            print(f"  ║  {d2l}")
            for d3l in D3_ORDER:
                cell_bar = df_bar[(df_bar["d1"] == d1_label) & (df_bar["d2"] == d2l) & (df_bar["d3"] == d3l)]
                cell_bar = cell_bar.dropna(subset=[col])
                n_bar = len(cell_bar)
                if n_bar < 3:
                    print(f"  ║    {d3l:<30} N={n_bar:<4} (insuficiente)")
                    continue
                wl = wins_losses(cell_bar[col].values)
                m_boot, lo, hi = boot_ci(cell_bar[col].values)
                print(f"  ║    {d3l:<30} N={n_bar} WR={wl['WR']*100:.0f}% EV={wl['EV']*100:+.2f}% "
                      f"PF={wl['PF']:.2f} avgW={wl['avg_win']*100:+.2f}% avgL={wl['avg_loss']*100:+.2f}%")
                print(f"  ║      CI95=[{lo*100:+.2f}%, {hi*100:+.2f}%] "
                      f"Wins: P50={wl['p50_win']*100:+.2f}% P75={wl.get('p75_win',np.nan)*100:+.2f}% "
                      f"Losses: P50={wl['p50_loss']*100:+.2f}% min={wl['min_loss']*100:+.2f}%")

# EXTREME_FEAR
mask_ef = df_piv["d1"] == "EXTREME_FEAR"
sub_ef = df_piv[mask_ef]
print(f"\n  EXTREME_FEAR: {len(sub_ef)} pivots (zz25)")
matrix_cell_report(sub_ef, "EXTREME_FEAR", f"pivots zz25 N={len(sub_ef)}")

# EXTREME_GREED
mask_eg = df_piv["d1"] == "EXTREME_GREED"
sub_eg = df_piv[mask_eg]
print(f"\n  EXTREME_GREED: {len(sub_eg)} pivots (zz25)")
matrix_cell_report(sub_eg, "EXTREME_GREED", f"pivots zz25 N={len(sub_eg)}")

# EUPHORIA (if populated)
mask_eu = df_piv["d1"] == "EUPHORIA"
sub_eu = df_piv[mask_eu]
if len(sub_eu) >= 5:
    print(f"\n  EUPHORIA: {len(sub_eu)} pivots (zz25)")
    matrix_cell_report(sub_eu, "EUPHORIA", f"pivots zz25 N={len(sub_eu)}")

# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3: D2 FLIP — ¿funciona como timing?
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("  SECCIÓN 3: D2 FLIP EN FG — ¿funciona como timing?")
print("=" * 100)

# D2 flip: sign of fg_vel changes from one day to next
d2_sign = df_bar["fg_vel"].map(np.sign).astype(float)
d2_sign_prev = d2_sign.shift(1)
df_bar["d2_sign"] = d2_sign
df_bar["d2_sign_prev"] = d2_sign_prev
df_bar["d2_flip"] = ((d2_sign != d2_sign_prev) & (d2_sign != 0.0) & (d2_sign_prev != 0.0)).astype(bool)

# Classify flip types
df_bar["d2_flip_type"] = "NONE"
df_bar.loc[df_bar["d2_flip"] & (df_bar["d2_sign"] > 0), "d2_flip_type"] = "FLIP_UP (velocity↑)"
df_bar.loc[df_bar["d2_flip"] & (df_bar["d2_sign"] < 0), "d2_flip_type"] = "FLIP_DOWN (velocity↓)"

print(f"\n  Total bars: {len(df_bar)}")
n_d2_flip = df_bar["d2_flip"].sum()
print(f"  D2 flip days: {n_d2_flip} ({n_d2_flip/len(df_bar)*100:.1f}%)")
print(f"    FLIP_UP:   {(df_bar['d2_flip_type']=='FLIP_UP (velocity↑)').sum()}")
print(f"    FLIP_DOWN: {(df_bar['d2_flip_type']=='FLIP_DOWN (velocity↓)').sum()}")

# Split by D1 context: flip within extreme vs neutral
for d1l in d1_labels:
    sub = df_bar[df_bar["d1"] == d1l]
    if len(sub) < 10:
        continue
    n_flip = sub["d2_flip"].sum()
    if n_flip < 3:
        continue
    print(f"\n  ── D2 flip dentro de D1 = {d1l} (N={len(sub)} bars, {n_flip} flips) ──")

    for horizon in [5, 10, 20, 40]:
        col = f"spy_fwd{horizon}"
        for flip_type in ["FLIP_UP (velocity↑)", "FLIP_DOWN (velocity↓)"]:
            cell = sub[sub["d2_flip_type"] == flip_type].dropna(subset=[col])
            non = sub[(sub["d2_flip_type"] == "NONE") & sub.index.isin(cell.index.to_list() + [])].dropna(subset=[col])
            if len(cell) < 3:
                continue
            # Compare flip vs non-flip days in same D1
            cell_all = sub.dropna(subset=[col])
            wl = wins_losses(cell[col].values)
            m_ci = boot_ci(cell[col].values)
            print(f"    {horizon}d {flip_type:<24} N={len(cell):>3} WR={wl['WR']*100:.0f}% EV={wl['EV']*100:+.2f}% "
                  f"PF={wl['PF']:.2f} CI95=[{m_ci[1]*100:+.2f}%,{m_ci[2]*100:+.2f}%]  "
                  f"avgW={wl['avg_win']*100:+.2f}% avgL={wl['avg_loss']*100:+.2f}%")

# Flip within EXTREME_FEAR and EXTREME_GREED specifically
print("\n  ── D2 flip timing in EXTREME_FEAR and EXTREME_GREED ──")
for d1l in ["EXTREME_FEAR", "EXTREME_GREED"]:
    sub = df_bar[df_bar["d1"] == d1l]
    if len(sub) < 10:
        continue
    print(f"\n    D1 = {d1l} ({len(sub)} bars):")

    # FLIP_UP vs FLIP_DOWN in this D1
    for flip_type in ["FLIP_UP (velocity↑)", "FLIP_DOWN (velocity↓)"]:
        cell_ff = sub[sub["d2_flip_type"] == flip_type]
        if len(cell_ff) < 3:
            print(f"    {flip_type}: N<3 (insufficient)")
            continue
        for horizon in [5, 10, 20, 40]:
            col = f"spy_fwd{horizon}"
            c = cell_ff.dropna(subset=[col])
            if len(c) < 3:
                continue
            wl = wins_losses(c[col].values)
            m_ci = boot_ci(c[col].values)
            print(f"      {horizon}d {flip_type:<24} N={len(c):>3} WR={wl['WR']*100:.0f}% EV={wl['EV']*100:+.2f}% "
                  f"CI95=[{m_ci[1]*100:+.2f}%,{m_ci[2]*100:+.2f}%]")

    # Non-flip baseline for comparison
    no_flip = sub[sub["d2_flip_type"] == "NONE"]
    for horizon in [5, 10, 20, 40]:
        col = f"spy_fwd{horizon}"
        c = no_flip.dropna(subset=[col])
        if len(c) < 3:
            continue
        wl = wins_losses(c[col].values)
        m_ci = boot_ci(c[col].values)
        print(f"      {horizon}d {'NO FLIP (baseline)':<24} N={len(c):>3} WR={wl['WR']*100:.0f}% EV={wl['EV']*100:+.2f}% "
              f"CI95=[{m_ci[1]*100:+.2f}%,{m_ci[2]*100:+.2f}%]")

# Directional flip: velocity changing sign within EXTREME_FEAR
print(f"\n  ── D2 flip DIRECTIONAL: EXTREME_FEAR → ¿D2 flip resuelve timing? ──")
sub_ef_b = df_bar[df_bar["d1"] == "EXTREME_FEAR"]
# Compare: FLIP_DOWN (velocity turning negative = fear worsening → wait) vs FLIP_UP (velocity turning positive = fear resolving → enter?)
for flip_type in ["FLIP_UP (velocity↑)", "FLIP_DOWN (velocity↓)"]:
    for horizon in [5, 10, 20, 40]:
        col = f"spy_fwd{horizon}"
        c = sub_ef_b[sub_ef_b["d2_flip_type"] == flip_type].dropna(subset=[col])
        if len(c) < 3:
            continue
        wl = wins_losses(c[col].values)
        m_ci = boot_ci(c[col].values)
        print(f"  {horizon}d {flip_type:<24} N={len(c):>3} WR={wl['WR']*100:.0f}% EV={wl['EV']*100:+.2f}% "
              f"CI95=[{m_ci[1]*100:+.2f}%,{m_ci[2]*100:+.2f}%]  avgW={wl['avg_win']*100:+.2f}% avgL={wl['avg_loss']*100:+.2f}%")

# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 4: D3 DISCRIMINA CASCADE (FG −15pp del pitfall #55)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("  SECCIÓN 4: D3 EN FG — ¿discrimina cascade (FG −15pp)?")
print("=" * 100)

# Measure: split by D3 terciles → cascade_50 rate
d3_vals_all = df_piv["fg_vol"].dropna().values
p33_val, p67_val = np.percentile(d3_vals_all, [33, 67])
print(f"\n  D3 (vol_norm) global: P33={p33_val:.4f}  P67={p67_val:.4f}")

df_piv["d3_tercil"] = "MID"
df_piv.loc[df_piv["fg_vol"] < p33_val, "d3_tercil"] = "LOW (comprimido/calma)"
df_piv.loc[df_piv["fg_vol"] > p67_val, "d3_tercil"] = "HIGH (caos/expansión)"

print(f"\n  ── Cascade rate por D3 tercil (all D1) ──")
baseline_c50_all = df_piv["cascade_50"].mean()
baseline_c75_all = df_piv["cascade_75"].mean()
print(f"  Baseline cascade_50: {baseline_c50_all*100:.1f}%")
print(f"  Baseline cascade_75: {baseline_c75_all*100:.1f}%")
print(f"\n  {'D3 tercil':<28} {'N_piv':>6} {'c50':>8} {'c75':>8} {'Δc50':>8} {'Δc75':>8} {'%BULL':>7}")
print(f"  {'-'*28} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*7}")

for t in ["LOW (comprimido/calma)", "MID", "HIGH (caos/expansión)"]:
    cell = df_piv[df_piv["d3_tercil"] == t]
    if len(cell) < 5:
        continue
    c50 = cell["cascade_50"].mean()
    c75 = cell["cascade_75"].mean()
    dc50 = (c50 - baseline_c50_all) * 100
    dc75 = (c75 - baseline_c75_all) * 100
    print(f"  {t:<28} {len(cell):>6} {c50*100:>7.1f}% {c75*100:>7.1f}% {dc50:>+7.1f}pp {dc75:>+7.1f}pp {cell['next_is_bull'].mean()*100:>6.1f}%")

# Bootstrap CI on the gap LOW-HIGH
low_c50 = df_piv.loc[df_piv["d3_tercil"] == "LOW (comprimido/calma)", "cascade_50"].values
high_c50 = df_piv.loc[df_piv["d3_tercil"] == "HIGH (caos/expansión)", "cascade_50"].values
if len(low_c50) >= 10 and len(high_c50) >= 10:
    gap = low_c50.mean() - high_c50.mean()
    rng = np.random.default_rng(42)
    gaps_boot = []
    for _ in range(3000):
        ls = rng.choice(low_c50, size=len(low_c50), replace=True)
        hs = rng.choice(high_c50, size=len(high_c50), replace=True)
        gaps_boot.append(ls.mean() - hs.mean())
    gaps_boot = np.sort(gaps_boot)
    lo_g = np.percentile(gaps_boot, 2.5)
    hi_g = np.percentile(gaps_boot, 97.5)
    p_zero = (gaps_boot < 0).mean()
    print(f"\n  Gap LOW−HIGH cascade_50: {gap*100:+.1f}pp  CI95=[{lo_g*100:+.1f}, {hi_g*100:+.1f}] pp  P(gap≤0)={p_zero:.4f}")

# Split by D1: D3 effect within EXTREME_FEAR, EXTREME_GREED, NEUTRAL
print(f"\n  ── D3→Cascade por D1 (los 6 niveles) ──")
for d1l in d1_labels:
    sub = df_piv[df_piv["d1"] == d1l]
    if len(sub) < 5:
        continue
    bl = sub["cascade_50"].mean()
    print(f"\n    D1 = {d1l} (N={len(sub)}, baseline c50={bl*100:.1f}%):")
    # Split by D3 tercile within this D1
    d3v = sub["fg_vol"].dropna()
    if len(d3v) < 10:
        print(f"      (insufficient D3 values)")
        continue
    p33d, p67d = np.percentile(d3v, [33, 67])
    sub = sub.copy()
    sub.loc[:, "d3t"] = "MID"
    sub.loc[sub["fg_vol"] < p33d, "d3t"] = "LOW"
    sub.loc[sub["fg_vol"] > p67d, "d3t"] = "HIGH"
    for t in ["LOW", "MID", "HIGH"]:
        cell = sub[sub["d3t"] == t]
        if len(cell) < 3:
            continue
        c50 = cell["cascade_50"].mean()
        dc = (c50 - bl) * 100
        print(f"      D3_tercil={t:<5} N={len(cell):>4} c50={c50*100:.1f}% Δ={dc:+.1f}pp  BULL%={cell['next_is_bull'].mean()*100:.0f}%")

# D3→cascade within EXTREME_FEAR and EXTREME_GREED only (the two extremes)
print(f"\n  ── D3→Cascade en EXTREME_FEAR y EXTREME_GREED (los 2 extremos) ──")
for d1l in ["EXTREME_FEAR", "EXTREME_GREED"]:
    sub = df_piv[df_piv["d1"] == d1l]
    bl = sub["cascade_50"].mean()
    print(f"\n    D1 = {d1l} (N={len(sub)}, baseline c50={bl*100:.1f}%):")
    for d3l in ["VOL_EXTREME_SQUEEZE", "VOL_MODERATE_COMPRESSION", "VOL_NEUTRAL_BASELINE",
                "VOL_ACCELERATING_EXPANSION", "VOL_PEAK_DECELERATION"]:
        cell = sub[sub["d3"] == d3l]
        if len(cell) < 2:
            continue
        c50 = cell["cascade_50"].mean()
        dc = (c50 - bl) * 100
        c75 = cell["cascade_75"].mean()
        print(f"      {d3l:<32} N={len(cell):>3} c50={c50*100:.0f}% Δ={dc:+.1f}pp  c75={c75*100:.0f}%  BULL%={cell['next_is_bull'].mean()*100:.0f}%")

# Direction test: D3 does NOT discriminate direction (pitfall #55)
print(f"\n  ── D3→DIRECCIÓN (next_is_bull) — ¿D3 discrimina dirección? ──")
for t in ["LOW (comprimido/calma)", "MID", "HIGH (caos/expansión)"]:
    cell = df_piv[df_piv["d3_tercil"] == t]
    if len(cell) < 5:
        continue
    bull = cell["next_is_bull"].mean()
    m, lo, hi = boot_ci(cell["next_is_bull"].values)
    print(f"  {t:<28} N={len(cell):>4} p_bull={bull*100:.1f}% CI95=[{lo*100:.0f}%,{hi*100:.0f}%]")

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 100)
print("  RESUMEN DEL HALLAZGO")
print("=" * 100)

print(f"\n  Datos: {len(df_bar)} barras FG∩SPY, {len(df_piv)} pivotes zz25 con FG")
print(f"  Estados D1×D2×D3 poblados: {len(states)} en fact store")
print(f"  Estados con N_bar≥10: {n_ge_10}")

print(f"\n  ── Hallazgos clave ──")
print(f"  1. D2 (velocidad) → ¿discrimina DIRECCIÓN? [ver sección 1A]")
print(f"  2. D3 (volatilidad) → ¿discrimina CASCADE? [ver sección 1B, sección 4]")
print(f"  3. Matriz D2×D3 en EXTREME_FEAR/GREED [ver sección 2]")
print(f"  4. D2 flip timing [ver sección 3]")
print(f"  5. D3 cascade FG −15pp [ver sección 4]")

print("\n  ESTUDIO COMPLETO.")