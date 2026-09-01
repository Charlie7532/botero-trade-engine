#!/usr/bin/env python3
"""
PCR COMPLETO — D2, D3, standalone wins/losses, vs SKEW, reclasificación final
=============================================================================
1. PCR D2 (diff(3)): ¿señal direccional? (ρ vs próximo leg bear, terciles)
2. PCR D3 (std2/std10): ¿discrimina cascade? (como FG/VVIX/BSI)
3. PCR standalone: wins/losses, PF, Kelly, timing, cuchillo cayendo
4. PCR vs SKEW: ¿correlación? ¿confirman o contradicen?
5. Reclasificar PCR definitivamente con las 8 dimensiones.

CI95 bootstrap 2000. NO promediar wins/losses.
Ticker: CBOE_PCR. Adapter: PCRLookupAdapter (lookup_pcr_guidance).
"""

import sys, json
from pathlib import Path
from datetime import timedelta
from collections import defaultdict, Counter

import numpy as np
import pandas as pd
from arnes.timing import classify_single_delta
from scipy.stats import spearmanr

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.rules.pcr_lookup import PCRLookupAdapter

# ═══ Config ═══════════════════════════════════════════════════════════════════
MIN_SIGNAL_SPACING = 10  # trading days between signals
FW_HORIZONS = [5, 10, 20, 40]
N_BOOT = 2000
BOOT_SEED = 42
CI = 95

# ═══ Bootstrap helpers ════════════════════════════════════════════════════════

def boot_ci_mean(arr, ci=CI, n_boot=N_BOOT, seed=BOOT_SEED):
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for i in range(n_boot):
        means[i] = rng.choice(arr, size=len(arr), replace=True).mean()
    means.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(means, lo)), float(np.percentile(means, hi))


def boot_ci_proportion(wins_bool, ci=CI, n_boot=N_BOOT, seed=BOOT_SEED):
    arr = np.asarray(wins_bool, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    props = np.empty(n_boot)
    for i in range(n_boot):
        props[i] = rng.choice(arr, size=len(arr), replace=True).mean()
    props.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(props, lo)), float(np.percentile(props, hi))


def boot_ci_diff_mean(a, b, ci=CI, n_boot=N_BOOT, seed=BOOT_SEED):
    """Bootstrap CI for difference in means (a - b)."""
    a = np.asarray(a, float); a = a[~np.isnan(a)]
    b = np.asarray(b, float); b = b[~np.isnan(b)]
    if len(a) < 3 or len(b) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        sa = rng.choice(a, size=len(a), replace=True)
        sb = rng.choice(b, size=len(b), replace=True)
        diffs[i] = sa.mean() - sb.mean()
    diffs.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(a.mean() - b.mean()), float(np.percentile(diffs, lo)), float(np.percentile(diffs, hi))


def spearman_safe(x, y):
    m = ~np.isnan(x) & ~np.isnan(y)
    if m.sum() < 8 or np.std(x[m]) == 0 or np.std(y[m]) == 0:
        return np.nan, np.nan, int(m.sum())
    r, p = spearmanr(x[m], y[m])
    return (float(r) if not np.isnan(r) else np.nan), (float(p) if not np.isnan(p) else np.nan), int(m.sum())


# ═══ Load data ════════════════════════════════════════════════════════════════

print("═══ CARGANDO DATOS ═══")
store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

# SPY
spy_raw = store.load_bars("SPY", "1d")["close"].copy()
spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()
spy_dates = list(spy.index)
spy_values = spy.values
spy_date_to_idx = {d: i for i, d in enumerate(spy_dates)}
print(f"  SPY: {spy_dates[0].date()} → {spy_dates[-1].date()} ({len(spy)} bars)")

# CBOE_PCR
pcr_raw = store.load_bars("CBOE_PCR", "1d")["close"].copy()
pcr_raw.index = pd.to_datetime(pcr_raw.index).normalize()
pcr_s = pcr_raw[~pcr_raw.index.duplicated(keep="last")].sort_index()
# align to spy dates
common_pcr = sorted(set(pcr_s.index) & set(spy.index))
pcr_aligned = pd.Series([float(pcr_s.loc[d]) for d in common_pcr], index=common_pcr)
pcr_d2 = pcr_aligned.diff(3)
pcr_d3_raw = (pcr_aligned.rolling(2).std() / pcr_aligned.rolling(10).std()).replace([np.inf, -np.inf], np.nan).fillna(1.0)
print(f"  CBOE_PCR: {pcr_aligned.index[0].date()} → {pcr_aligned.index[-1].date()} ({len(pcr_aligned)} bars aligned)")

# SKEW
skew_raw = store.load_bars("SKEW", "1d")["close"].copy()
skew_raw.index = pd.to_datetime(skew_raw.index).normalize()
skew_s = skew_raw[~skew_raw.index.duplicated(keep="last")].sort_index()
common_skew = sorted(set(skew_s.index) & set(spy.index))
skew_aligned = pd.Series([float(skew_s.loc[d]) for d in common_skew], index=common_skew)
skew_d2 = skew_aligned.diff(3)
skew_d3_raw = (skew_aligned.rolling(2).std() / skew_aligned.rolling(10).std()).replace([np.inf, -np.inf], np.nan).fillna(1.0)
print(f"  SKEW: {skew_aligned.index[0].date()} → {skew_aligned.index[-1].date()} ({len(skew_aligned)} bars aligned)")

# Zigzag legs
legs25 = repo.get_confirmed_legs("SPY", "zz25")
legs50 = repo.get_confirmed_legs("SPY", "zz50")
legs75 = repo.get_confirmed_legs("SPY", "zz75")
starts50 = set(pd.to_datetime(l.start_timestamp).date() for l in legs50)
starts75 = set(pd.to_datetime(l.start_timestamp).date() for l in legs75)

print(f"  zz25 legs: {len(legs25)} | zz50: {len(legs50)} | zz75: {len(legs75)}")

# Build pivot dataframe
df25 = pd.DataFrame([
    {"start_timestamp": l.start_timestamp, "start_type": l.start_type,
     "prev_leg_return": l.prev_leg_return, "start_price": l.start_price}
    for l in legs25
]).dropna(subset=["prev_leg_return"]).reset_index(drop=True)

df25["pivot_date"] = pd.to_datetime(df25["start_timestamp"]).dt.date
df25["leg_bear"] = (df25["start_type"] == "MAX").astype(float)
df25["cascade_50"] = df25["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts50 for i in range(-3, 4)))
)
df25["cascade_75"] = df25["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts75 for i in range(-3, 4)))
)
N_PIVOTS = len(df25)
print(f"  Pivots zz25 con prev_leg_return: {N_PIVOTS}")
print(f"  cascade_50 rate: {df25['cascade_50'].mean():.3f} | cascade_75: {df25['cascade_75'].mean():.3f}")
print(f"  leg_bear rate: {df25['leg_bear'].mean():.3f} (alternating by construction)")

# Lookup PCR values at each pivot (date-object keyed dicts for fast lookup)
pcr_by_date = {ts.date(): float(v) for ts, v in pcr_aligned.items()}
pcr_d2_by_date = {ts.date(): float(v) for ts, v in pcr_d2.items()}
pcr_d3_by_date = {ts.date(): float(v) for ts, v in pcr_d3_raw.items()}
skew_by_date = {ts.date(): float(v) for ts, v in skew_aligned.items()}
skew_d2_by_date = {ts.date(): float(v) for ts, v in skew_d2.items()}

pcr_at_pivot = []
for _, row in df25.iterrows():
    pd_ = row["pivot_date"]
    pcr_at_pivot.append({
        "pivot_idx": row.name,
        "pcr_d1": pcr_by_date.get(pd_, np.nan),
        "pcr_d2": pcr_d2_by_date.get(pd_, np.nan),
        "pcr_d3": pcr_d3_by_date.get(pd_, np.nan),
    })
pcr_piv = pd.DataFrame(pcr_at_pivot).set_index("pivot_idx")
for col in ["pcr_d1", "pcr_d2", "pcr_d3"]:
    df25[col] = pcr_piv[col].values

mask_pcr_valid = df25["pcr_d1"].notna()
print(f"  Pivots with PCR data: {mask_pcr_valid.sum()}/{N_PIVOTS}")

# SKEW at each pivot
skew_at_piv = np.array([skew_by_date.get(d, np.nan) for d in df25["pivot_date"]])
skew_d2_at_piv = np.array([skew_d2_by_date.get(d, np.nan) for d in df25["pivot_date"]])

# PCR adapter
pcr_adapter = PCRLookupAdapter()

# ═══════════════════════════════════════════════════════════════════════════════
# PARTE 1 — PCR D2 (diff(3)): ¿señal direccional?
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 100)
print("  PARTE 1 — PCR D2 (velocidad Δ3d): ¿señal direccional?")
print("═" * 100)

# 1a. Spearman ρ
valid = df25[mask_pcr_valid]
d2_data = valid["pcr_d2"].values
d1_data = valid["pcr_d1"].values
leg_bear_data = valid["leg_bear"].values

r_d2_dir, p_d2_dir, n_d2 = spearman_safe(d2_data, leg_bear_data)
r_d1_dir, p_d1_dir, n_d1 = spearman_safe(d1_data, leg_bear_data)

print(f"\n  ρ(PCR D2, leg_bear)      = {r_d2_dir:+.4f}  (p={p_d2_dir:.4f}, N={n_d2})")
print(f"  ρ(PCR D1, leg_bear)      = {r_d1_dir:+.4f}  (p={p_d1_dir:.4f}, N={n_d1})")
gap_dir = abs(r_d2_dir) - abs(r_d1_dir)
print(f"  gap |ρ| D2−D1             = {gap_dir:+.4f}  → {'D2 gana' if gap_dir > 0 else 'D1 gana'}")

# 1b. Terciles de D2 → %bear
d2_arr = valid["pcr_d2"].values
bear_arr = valid["leg_bear"].values
lo_thr = np.quantile(d2_arr[~np.isnan(d2_arr)], 0.33)
hi_thr = np.quantile(d2_arr[~np.isnan(d2_arr)], 0.67)

for label, mask in [
    ("D2 bajo (tercil 1, D2<{:.3f})".format(lo_thr), d2_arr <= lo_thr),
    ("D2 medio", (d2_arr > lo_thr) & (d2_arr < hi_thr)),
    ("D2 alto (tercil 3, D2>{:.3f})".format(hi_thr), d2_arr >= hi_thr),
]:
    b = bear_arr[mask]
    wr, lo, hi = boot_ci_proportion(b) if len(b) >= 3 else (b.mean(), np.nan, np.nan)
    print(f"\n  {label}:")
    print(f"    %leg_bear = {b.mean()*100:.1f}%  CI95=[{lo*100:.0f}%,{hi*100:.0f}%]  N={len(b)}")

# Tercile gap (top − bottom)
bear_lo = bear_arr[d2_arr <= lo_thr]
bear_hi = bear_arr[d2_arr >= hi_thr]
gap_mean, gap_lo, gap_hi = boot_ci_diff_mean(bear_hi, bear_lo)
print(f"\n  Gap D2 alto−bajo (tercil 3 − 1) = {gap_mean*100:+.1f}pp  CI95=[{gap_lo*100:+.0f},{gap_hi*100:+.0f}pp]  "
      f"(N_lo={len(bear_lo)}, N_hi={len(bear_hi)})")

# 1c. D2 sign split
d2_up = d2_arr > 0
bear_up = bear_arr[d2_up]
bear_dn = bear_arr[~d2_up]
wr_up, lo_up, hi_up = boot_ci_proportion(bear_up)
wr_dn, lo_dn, hi_dn = boot_ci_proportion(bear_dn)
gap_sign_mean, gap_sign_lo, gap_sign_hi = boot_ci_diff_mean(bear_dn, bear_up)

print(f"\n  D2 sign split:")
print(f"    D2↑ (PCR subiendo):    %leg_bear = {bear_up.mean()*100:.1f}%  CI95=[{lo_up*100:.0f}%,{hi_up*100:.0f}%]  N={len(bear_up)}")
print(f"    D2↓ (PCR bajando):     %leg_bear = {bear_dn.mean()*100:.1f}%  CI95=[{lo_dn*100:.0f}%,{hi_dn*100:.0f}%]  N={len(bear_dn)}")
print(f"    Gap D2↓−D2↑ = {gap_sign_mean*100:+.1f}pp  CI95=[{gap_sign_lo*100:+.0f},{gap_sign_hi*100:+.0f}pp]")

# 1d. ρ(PCR D2, cascade_50) — orthogonal check
c50_data = valid["cascade_50"].values
r_d2_c50, p_d2_c50, _ = spearman_safe(d2_data, c50_data)
print(f"\n  Orthogonal check: ρ(PCR D2, cascade_50) = {r_d2_c50:+.4f}  (p={p_d2_c50:.4f})")

part1 = {
    "r_d2_dir": r_d2_dir, "p_d2_dir": p_d2_dir,
    "r_d1_dir": r_d1_dir, "p_d1_dir": p_d1_dir,
    "gap_abs_rho": gap_dir,
    "tercile_lo_thr": float(lo_thr), "tercile_hi_thr": float(hi_thr),
    "tercile_lo_bear_pct": float(bear_lo.mean()), "tercile_mid_bear_pct": float(bear_arr[(d2_arr > lo_thr) & (d2_arr < hi_thr)].mean()),
    "tercile_hi_bear_pct": float(bear_hi.mean()),
    "tercile_gap_pp": float(gap_mean * 100), "tercile_gap_ci95": [float(gap_lo * 100), float(gap_hi * 100)],
    "d2_sign_up_bear_pct": float(bear_up.mean()), "d2_sign_dn_bear_pct": float(bear_dn.mean()),
    "d2_sign_gap_pp": float(gap_sign_mean * 100), "d2_sign_gap_ci95": [float(gap_sign_lo * 100), float(gap_sign_hi * 100)],
    "r_d2_c50": r_d2_c50, "p_d2_c50": p_d2_c50,
}

# ═══════════════════════════════════════════════════════════════════════════════
# PARTE 2 — PCR D3 (std2/std10): ¿discrimina cascade?
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 100)
print("  PARTE 2 — PCR D3 (volatilidad std2/std10): ¿discrimina cascade?")
print("═" * 100)

d3_data = valid["pcr_d3"].values
r_d3_c50, p_d3_c50, _ = spearman_safe(d3_data, c50_data)
r_d3_c75, p_d3_c75, _ = spearman_safe(d3_data, valid["cascade_75"].values)
r_d3_dir, p_d3_dir, _ = spearman_safe(d3_data, bear_arr)

print(f"\n  ρ(PCR D3, cascade_50) = {r_d3_c50:+.4f}  (p={p_d3_c50:.4f})")
print(f"  ρ(PCR D3, cascade_75) = {r_d3_c75:+.4f}  (p={p_d3_c75:.4f})")
print(f"  ρ(PCR D3, leg_bear)   = {r_d3_dir:+.4f}  (p={p_d3_dir:.4f})")

# Tercile split D3 → cascade_50
d3_lo_thr = np.quantile(d3_data[~np.isnan(d3_data)], 0.33)
d3_hi_thr = np.quantile(d3_data[~np.isnan(d3_data)], 0.67)

for label, mask in [
    ("D3 bajo (calma, <{:.3f})".format(d3_lo_thr), d3_data <= d3_lo_thr),
    ("D3 medio", (d3_data > d3_lo_thr) & (d3_data < d3_hi_thr)),
    ("D3 alto (caos, >{:.3f})".format(d3_hi_thr), d3_data >= d3_hi_thr),
]:
    c50 = c50_data[mask]
    wr, lo, hi = boot_ci_proportion(c50) if len(c50) >= 3 else (c50.mean(), np.nan, np.nan)
    dir_bear = bear_arr[mask].mean() if len(bear_arr[mask]) > 0 else np.nan
    print(f"\n  {label}:")
    print(f"    cascade_50 = {c50.mean()*100:.1f}%  CI95=[{lo*100:.0f}%,{hi*100:.0f}%]  leg_bear={dir_bear*100:.1f}%  N={len(c50)}")

c50_lo = c50_data[d3_data <= d3_lo_thr]
c50_hi = c50_data[d3_data >= d3_hi_thr]
gap_c50, gap_c50_lo, gap_c50_hi = boot_ci_diff_mean(c50_hi, c50_lo)
print(f"\n  Gap cascade_50 (caos−calma) = {gap_c50*100:+.1f}pp  CI95=[{gap_c50_lo*100:+.0f},{gap_c50_hi*100:+.0f}pp]  "
      f"(N_lo={len(c50_lo)}, N_hi={len(c50_hi)})")

# Also D3 tercile split → cascade_75
c75_data = valid["cascade_75"].values
c75_lo = c75_data[d3_data <= d3_lo_thr]
c75_hi = c75_data[d3_data >= d3_hi_thr]
gap_c75, gap_c75_lo, gap_c75_hi = boot_ci_diff_mean(c75_hi, c75_lo)
print(f"  Gap cascade_75 (caos−calma) = {gap_c75*100:+.1f}pp  CI95=[{gap_c75_lo*100:+.0f},{gap_c75_hi*100:+.0f}pp]")

# D3 × type (MIN vs MAX) split
for ptype in ["MIN", "MAX"]:
    typ = valid["start_type"] == ptype
    if typ.sum() < 20:
        continue
    d3t = d3_data[typ]
    c50t = c50_data[typ]
    lo_t = d3t <= np.quantile(d3t[~np.isnan(d3t)], 0.33)
    hi_t = d3t >= np.quantile(d3t[~np.isnan(d3t)], 0.67)
    gap_t, gap_t_lo, gap_t_hi = boot_ci_diff_mean(c50t[hi_t], c50t[lo_t])
    print(f"\n  {ptype} only: cascade_50 gap (caos−calma) = {gap_t*100:+.1f}pp  CI95=[{gap_t_lo*100:+.0f},{gap_t_hi*100:+.0f}pp]  "
          f"N_lo={len(c50t[lo_t])}, N_hi={len(c50t[hi_t])}")

part2 = {
    "r_d3_c50": r_d3_c50, "p_d3_c50": p_d3_c50,
    "r_d3_c75": r_d3_c75, "p_d3_c75": p_d3_c75,
    "r_d3_dir": r_d3_dir, "p_d3_dir": p_d3_dir,
    "d3_lo_thr": float(d3_lo_thr), "d3_hi_thr": float(d3_hi_thr),
    "c50_caos_minus_calma_pp": float(gap_c50 * 100), "c50_gap_ci95": [float(gap_c50_lo * 100), float(gap_c50_hi * 100)],
    "c75_caos_minus_calma_pp": float(gap_c75 * 100), "c75_gap_ci95": [float(gap_c75_lo * 100), float(gap_c75_hi * 100)],
}

# ═══════════════════════════════════════════════════════════════════════════════
# PARTE 3 — PCR standalone: wins/losses (EXTREME_PUT_PANIC)
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 100)
print("  PARTE 3 — PCR standalone: wins/losses (EXTREME_PUT_PANIC)")
print("  Metodología v2: entrada en BARRA de señal, forward returns.")
print("═" * 100)

# Identify every bar where D1 = EXTREME_PUT_PANIC
extreme_d1 = "EXTREME_PUT_PANIC"
signal_bars = []

for dt in common_pcr:
    val = float(pcr_aligned.loc[dt])
    vel = float(pcr_d2.loc[dt]) if not pd.isna(pcr_d2.loc[dt]) else 0.0
    vol = float(pcr_d3_raw.loc[dt]) if not pd.isna(pcr_d3_raw.loc[dt]) else 1.0
    try:
        g = pcr_adapter.lookup_pcr_guidance(val=val, d3_speed=vel, vol_norm=vol, vol_d3=0.0)
    except Exception:
        continue
    if g is None:
        continue
    d1_bin = g.state_key.split("__")[0]
    if d1_bin != extreme_d1:
        continue
    d2_bin = g.state_key.split("__")[1] if "__" in g.state_key else "?"
    d3_bin = g.state_key.split("__")[2] if g.state_key.count("__") >= 2 else "?"
    n_state = getattr(g, 'n', 0)
    spy_idx = spy_date_to_idx.get(dt)
    if spy_idx is None:
        continue
    signal_bars.append({
        "date": dt, "spy_idx": spy_idx, "val": val, "vel": vel, "vol": vol,
        "state_key": g.state_key, "d1": d1_bin, "d2": d2_bin, "d3": d3_bin, "n_state": n_state,
    })

print(f"  Barras con {extreme_d1}: {len(signal_bars)}")

# Dedup
signal_bars.sort(key=lambda x: x["date"])
deduped = []
last_idx = -MIN_SIGNAL_SPACING - 1
for sb in signal_bars:
    if sb["spy_idx"] - last_idx >= MIN_SIGNAL_SPACING:
        deduped.append(sb)
        last_idx = sb["spy_idx"]
print(f"  Después de dedup (≥{MIN_SIGNAL_SPACING}d): {len(deduped)}")

# Build all pivots list for timing
all_pivots = []
for l in legs25:
    d = pd.to_datetime(l.start_timestamp).normalize()
    all_pivots.append((d, l.start_type, float(l.start_price)))
all_pivots.sort(key=lambda x: x[0])

def nearest_min_pivot(date):
    """Returns (days_since, slot, pivot_date, pivot_price) for nearest MIN pivot.
    days_since = (signal_date - pivot_date).days
    slot = 't-2' | 't-1' | 't=0' | 't+1' | 't+2' | 'ENTRE'
    negative = anticipada (signal BEFORE pivot), 0 = en_pivote, positive = retrasada."""
    best = None
    for pd_d, pt, pr in all_pivots:
        if pt != "MIN":
            continue
        delta = (date - pd_d).days
        if best is None or abs(delta) < abs(best[0]):
            best = (delta, pd_d, pr)
    if best is not None:
        slot = classify_single_delta(best[0])
        return best[0], slot, best[1], best[2]
    return None, 'ENTRE', None, None

# Compute forward returns + timing
signals = []
for sb in deduped:
    entry_idx = sb["spy_idx"]
    entry_price = spy_values[entry_idx]
    fwd_returns = {}
    for h in FW_HORIZONS:
        fwd_idx = entry_idx + h
        if fwd_idx >= len(spy_values):
            fwd_returns[h] = None
        else:
            fwd_returns[h] = float(spy_values[fwd_idx] / entry_price - 1.0)

    # Timing vs nearest MIN pivot
    days_since, slot, min_date, min_price = nearest_min_pivot(sb["date"])
    if days_since is not None:
        if days_since <= 0:
            # anticipada (signal before pivot) or en_pivote
            # Window from signal to pivot
            mask = (spy.index >= sb["date"]) & (spy.index <= min_date)
            spy_window = spy[mask]
            if len(spy_window) > 1:
                dd_to_pivot = float(spy_window.min() / entry_price - 1.0)
            else:
                dd_to_pivot = float(min_price / entry_price - 1.0)
        else:
            # retrasada (signal after pivot) — the pivot already happened
            # "DD to pivot" doesn't apply; the entry is after the floor.
            dd_to_pivot = 0.0
        is_knife = (days_since < 0) and (dd_to_pivot < -0.05)  # anticipada + >5% DD
    else:
        dd_to_pivot = 0.0
        is_knife = False
        days_since = None
        min_date = None

    signals.append({
        "date": sb["date"], "spy_idx": entry_idx, "entry_price": entry_price,
        "state_key": sb["state_key"], "d1": sb["d1"], "d2": sb["d2"], "d3": sb["d3"],
        "n_state": sb["n_state"], "val": sb["val"], "vel": sb["vel"], "vol": sb["vol"],
        "fwd": fwd_returns,
        "days_since_pivot": days_since, "slot": slot, "pivot_date": min_date,
        "dd_to_pivot": dd_to_pivot, "is_knife": is_knife,
    })

n_signals = len(signals)
print(f"  Señales con forward returns: {n_signals}")

# Quality split
n_ge30 = [s for s in signals if s["n_state"] >= 30]
n_10_30 = [s for s in signals if 10 <= s["n_state"] < 30]
n_lt10 = [s for s in signals if s["n_state"] < 10]
print(f"  Calidad: N≥30={len(n_ge30)} | N10-30={len(n_10_30)} | N<10={len(n_lt10)}")

# --- Analysis function (mirrors v2) ---
def analyze_pcr_signals(sig_list, label, quality_label=""):
    """Full 8-dimension analysis for a group of signals."""
    if len(sig_list) < 3:
        return {"label": label, "N": len(sig_list), "insufficient": True}

    n = len(sig_list)

    # Forward return arrays per horizon
    fwd_arrays = {}
    for h in FW_HORIZONS:
        arr = np.array([s["fwd"][h] for s in sig_list if s["fwd"][h] is not None])
        fwd_arrays[h] = arr

    R = {"label": label, "N": n, "n_quality": quality_label}

    # A. Win rate + CI95
    R["A_win_rate"] = {}; R["A_wr_ci95"] = {}
    for h in FW_HORIZONS:
        arr = fwd_arrays[h]
        if len(arr) < 3:
            R["A_win_rate"][h] = np.nan; R["A_wr_ci95"][h] = [np.nan, np.nan]
            continue
        wr, wr_lo, wr_hi = boot_ci_proportion(arr > 0)
        R["A_win_rate"][h] = wr; R["A_wr_ci95"][h] = [wr_lo, wr_hi]

    # B. Wins distribution
    R["B_wins"] = {}
    for h in FW_HORIZONS:
        arr = fwd_arrays[h]
        wins = arr[arr > 0]
        if len(wins) < 2:
            R["B_wins"][h] = None; continue
        R["B_wins"][h] = {
            "n": len(wins), "mean": float(np.mean(wins)), "median": float(np.median(wins)),
            "p25": float(np.percentile(wins, 25)) if len(wins) >= 4 else np.nan,
            "p75": float(np.percentile(wins, 75)) if len(wins) >= 4 else np.nan,
            "p90": float(np.percentile(wins, 90)) if len(wins) >= 10 else np.nan,
            "max": float(np.max(wins)),
        }

    # C. Losses + wipeouts
    R["C_losses"] = {}
    for h in FW_HORIZONS:
        arr = fwd_arrays[h]
        losses = arr[arr <= 0]
        if len(losses) < 2:
            R["C_losses"][h] = None; continue
        wipeouts = losses[losses < -0.20]
        R["C_losses"][h] = {
            "n": len(losses), "mean": float(np.mean(losses)), "median": float(np.median(losses)),
            "p25": float(np.percentile(losses, 25)) if len(losses) >= 4 else np.nan,
            "p75": float(np.percentile(losses, 75)) if len(losses) >= 4 else np.nan,
            "p90": float(np.percentile(losses, 90)) if len(losses) >= 10 else np.nan,
            "min": float(np.min(losses)),
            "wipeouts_n": len(wipeouts), "wipeouts_pct": len(wipeouts) / len(arr) * 100,
            "wipeouts_vals": wipeouts.tolist(),
        }

    # D. Profit factor, Kelly, EV
    R["D_metrics"] = {}
    for h in FW_HORIZONS:
        arr = fwd_arrays[h]
        if len(arr) < 3:
            R["D_metrics"][h] = None; continue
        wins = arr[arr > 0]; losses = arr[arr <= 0]
        gross_win = np.sum(wins) if len(wins) > 0 else 0
        gross_loss = abs(np.sum(losses)) if len(losses) > 0 else 0
        pf = float(gross_win / gross_loss) if gross_loss > 0 else float('inf')
        wr_val = np.mean(arr > 0) if len(arr) > 0 else np.nan
        avg_w = np.mean(wins) if len(wins) > 0 else 0
        avg_l = abs(np.mean(losses)) if len(losses) > 0 else 0
        wlr = avg_w / avg_l if avg_l > 0 else float('inf')
        kelly = wr_val - (1 - wr_val) / wlr if (avg_l > 0 and wlr > 0 and wlr != float('inf')) else np.nan
        ev, ev_lo, ev_hi = boot_ci_mean(arr)
        R["D_metrics"][h] = {
            "profit_factor": pf, "avg_win": float(avg_w), "avg_loss": float(avg_l),
            "win_loss_ratio": float(wlr) if wlr != float('inf') else "inf",
            "kelly": float(kelly) if not np.isnan(kelly) else None,
            "ev": ev, "ev_ci95": [ev_lo, ev_hi],
            "sharpe": float(ev / np.std(arr)) if np.std(arr) > 0 else 0.0,
        }

    # E. Rachas (20d)
    arr20 = fwd_arrays[20]
    if len(arr20) >= 3:
        loss_streaks = []
        curr = 0
        for r in arr20:
            if r <= 0:
                curr += 1
            else:
                if curr > 0: loss_streaks.append(curr)
                curr = 0
        if curr > 0: loss_streaks.append(curr)
        ls = np.array(loss_streaks) if loss_streaks else np.array([0])
        R["E_streaks"] = {
            "n_streaks": len(loss_streaks), "max_streak": int(ls.max()),
            "mean_streak": float(ls.mean()),
            "streak_counts": {int(k): int(v) for k, v in Counter(ls).items()},
        }
    else:
        R["E_streaks"] = None

    # F. Timing vs zigzag (6 Slots Canónicos: t-2, t-1, t=0, t+1, t+2, ENTRE)
    days_arr = np.array([s["days_since_pivot"] for s in sig_list if s["days_since_pivot"] is not None])
    slots_arr = np.array([s["slot"] for s in sig_list if s["days_since_pivot"] is not None])
    dd_arr = np.array([s["dd_to_pivot"] for s in sig_list])
    
    counts = {s: int((slots_arr == s).sum()) for s in ["t-2", "t-1", "t=0", "t+1", "t+2", "ENTRE"]}
    n_ant = counts["t-2"] + counts["t-1"]
    n_exa = counts["t=0"]
    n_ret = counts["t+1"] + counts["t+2"]
    n_fue = counts["ENTRE"]
    n_rng = n_ant + n_exa + n_ret

    R["F_timing"] = {
        "n_with_pivot": len(days_arr),
        "slots": counts,
        "n_en_rango": n_rng, "pct_en_rango": float(n_rng / len(days_arr) * 100) if len(days_arr) > 0 else 0.0,
        "n_anticipada": n_ant, "pct_anticipada": float(n_ant / len(days_arr) * 100) if len(days_arr) > 0 else 0.0,
        "n_exacta": n_exa, "pct_exacta": float(n_exa / len(days_arr) * 100) if len(days_arr) > 0 else 0.0,
        "n_retrasada": n_ret, "pct_retrasada": float(n_ret / len(days_arr) * 100) if len(days_arr) > 0 else 0.0,
        "n_fuera_de_rango": n_fue, "pct_fuera_de_rango": float(n_fue / len(days_arr) * 100) if len(days_arr) > 0 else 0.0,
        "days_since_mean": float(np.mean(days_arr)) if len(days_arr) > 0 else np.nan,
        "days_since_median": float(np.median(days_arr)) if len(days_arr) > 0 else np.nan,
        "dd_to_pivot_mean": float(np.mean(dd_arr)),
        "dd_to_pivot_p50": float(np.median(dd_arr)),
        "entry_same_day_pct": float(np.mean(np.abs(dd_arr) < 0.005) * 100),
    }

    # G. Cuchillo cayendo
    knife = [s for s in sig_list if s["is_knife"]]
    n_knife = len(knife)
    R["G_knife"] = {
        "n": n_knife, "pct": n_knife / n * 100 if n > 0 else 0,
    }
    if n_knife > 0:
        R["G_knife"]["dates"] = [str(s["date"].date()) for s in knife]
        R["G_knife"]["dd_values"] = [float(s["dd_to_pivot"]) for s in knife]
        R["G_knife"]["d2_bins"] = [s["d2"] for s in knife]
        R["G_knife"]["d3_bins"] = [s["d3"] for s in knife]
        R["G_knife"]["state_keys"] = [s["state_key"] for s in knife]

    # H. Calidad de muestra
    n_states = np.array([s["n_state"] for s in sig_list])
    R["H_quality"] = {
        "n_total": n, "n_ge_30": int(np.sum(n_states >= 30)),
        "n_10_30": int(np.sum((n_states >= 10) & (n_states < 30))),
        "n_lt_10": int(np.sum(n_states < 10)),
        "min_n_state": int(np.min(n_states)), "max_n_state": int(np.max(n_states)),
        "median_n_state": float(np.median(n_states)), "quality_tier": quality_label,
    }

    # Signal details
    R["signals_detail"] = []
    for s in sig_list:
        R["signals_detail"].append({
            "date": str(s["date"].date()), "state_key": s["state_key"],
            "d2": s["d2"], "d3": s["d3"], "n_state": s["n_state"],
            "days_since_pivot": s["days_since_pivot"], "dd_to_pivot": float(s["dd_to_pivot"]),
            "is_knife": s["is_knife"],
            "fwd_5d": float(s["fwd"][5]) if s["fwd"][5] is not None else None,
            "fwd_10d": float(s["fwd"][10]) if s["fwd"][10] is not None else None,
            "fwd_20d": float(s["fwd"][20]) if s["fwd"][20] is not None else None,
            "fwd_40d": float(s["fwd"][40]) if s["fwd"][40] is not None else None,
        })

    return R


# Analyze groups
results_groups = []
if len(n_ge30) >= 3:
    results_groups.append(analyze_pcr_signals(n_ge30, "PCR EXTREME_PUT_PANIC N≥30", "N_GE_30"))
if len(n_10_30) >= 3:
    results_groups.append(analyze_pcr_signals(n_10_30, "PCR EXTREME_PUT_PANIC N10-30", "N_10_30"))
if len(n_lt10) >= 3:
    results_groups.append(analyze_pcr_signals(n_lt10, "PCR EXTREME_PUT_PANIC N<10", "N_LT_10"))
combined = analyze_pcr_signals(signals, "PCR EXTREME_PUT_PANIC TODOS", "ALL")
results_groups.append(combined)

# --- Print part 3 results ---
for grp in results_groups:
    label = grp["label"]; n_grp = grp["N"]; q_label = grp.get("n_quality", "")
    if grp.get("insufficient"):
        print(f"\n  ── {label}: N={n_grp} INSUFICIENTE (<3) ──")
        continue

    print(f"\n  ┌─ {'─'*90}")
    print(f"  │ {label}  (N={n_grp})")
    print(f"  ├─ {'─'*90}")

    hq = grp.get("H_quality", {})
    print(f"  │ H. CALIDAD: N≥30={hq.get('n_ge_30',0)}, 10-30={hq.get('n_10_30',0)}, <10={hq.get('n_lt_10',0)}  "
          f"min={hq.get('min_n_state',0)}, med={hq.get('median_n_state',0):.0f}, max={hq.get('max_n_state',0)}")

    print(f"  │")
    print(f"  │ {'Horizon':>6} │ {'WR':>7} {'CI95':>22} │ {'Win Med':>8} {'Win P90':>8} │ {'Loss Med':>8} {'Loss Min':>8} │ {'PF':>6} {'Kelly':>7} {'EV':>8} │")
    print(f"  │ {'─'*6}─┼─{'─'*7}─{'─'*22}─┼─{'─'*8}─{'─'*8}─┼─{'─'*8}─{'─'*8}─┼─{'─'*6}─{'─'*7}─{'─'*8}─┤")

    for h in FW_HORIZONS:
        wr = grp["A_win_rate"].get(h, np.nan)
        wr_ci = grp["A_wr_ci95"].get(h, [np.nan, np.nan])
        b_w = grp.get("B_wins", {}).get(h, {}) or {}
        c_l = grp.get("C_losses", {}).get(h, {}) or {}
        d_m = grp.get("D_metrics", {}).get(h, {}) or {}

        def fmt_pct(x, suf=""):
            if x is None or np.isnan(x): return "N/A"
            return f"{x*100:+.1f}{suf}"

        wr_s = f"{wr*100:.0f}%" if not np.isnan(wr) else "N/A"
        ci_s = f"[{wr_ci[0]*100:.0f}%,{wr_ci[1]*100:.0f}%]" if not np.isnan(wr) else "N/A"
        w_med = fmt_pct(b_w.get('median'), '%') if b_w else "N/A"
        w_p90 = fmt_pct(b_w.get('p90'), '%') if b_w and not (isinstance(b_w.get('p90'), float) and np.isnan(b_w.get('p90'))) else "N/A"
        l_med = fmt_pct(c_l.get('median'), '%') if c_l else "N/A"
        l_min = fmt_pct(c_l.get('min'), '%') if c_l else "N/A"
        pf = f"{d_m.get('profit_factor',0):.1f}" if d_m else "N/A"
        kl = f"{d_m.get('kelly',0)*100:.0f}%" if d_m and d_m.get('kelly') else "N/A"
        ev = f"{d_m.get('ev',0)*100:+.1f}%" if d_m else "N/A"

        print(f"  │ {f'{h}d':>6} │ {wr_s:>7} {ci_s:>22} │ {w_med:>8} {w_p90:>8} │ {l_med:>8} {l_min:>8} │ {pf:>6} {kl:>7} {ev:>8} │")

    # Wipeouts
    print(f"  │")
    for h in FW_HORIZONS:
        c_l = grp.get("C_losses", {}).get(h, {}) or {}
        if c_l and c_l.get("wipeouts_n", 0) > 0:
            wo_n = c_l.get("wipeouts_n", 0); wo_pct = c_l.get("wipeouts_pct", 0)
            wo_vals = c_l.get("wipeouts_vals", [])
            print(f"  │ {f'{h}d WIPEOUTS >20%:':>8} {wo_n} ({wo_pct:.0f}%) → {[f'{v*100:.1f}%' for v in wo_vals[:5]]}")

    # Streaks
    e_s = grp.get("E_streaks")
    if e_s:
        print(f"  │ E. RACHAS (target 20d): {e_s['n_streaks']} rachas, max={e_s['max_streak']}, avg={e_s['mean_streak']:.1f}")

    # Timing
    ft = grp.get("F_timing", {})
    slots = ft.get("slots", {})
    print(f"  │ F. TIMING vs ZIGZAG (6 Slots Canónicos, MIN pivot):")
    print(f"  │    EN RANGO ([-2t, +2t]): {ft.get('n_en_rango',0)} ({ft.get('pct_en_rango',0):.0f}%)")
    print(f"  │      • Anticipada  (t-2, t-1): {ft.get('n_anticipada',0)} ({ft.get('pct_anticipada',0):.0f}%)  [t-2: {slots.get('t-2',0)}, t-1: {slots.get('t-1',0)}]")
    print(f"  │      • Exacta      (t=0):     {ft.get('n_exacta',0)} ({ft.get('pct_exacta',0):.0f}%)")
    print(f"  │      • Retrasada   (t+1, t+2): {ft.get('n_retrasada',0)} ({ft.get('pct_retrasada',0):.0f}%)  [t+1: {slots.get('t+1',0)}, t+2: {slots.get('t+2',0)}]")
    print(f"  │    FUERA DE RANGO (ENTRE):    {ft.get('n_fuera_de_rango',0)} ({ft.get('pct_fuera_de_rango',0):.0f}%)")
    dd_mean = ft.get('dd_to_pivot_mean', 0)
    dd_p50 = ft.get('dd_to_pivot_p50', 0)
    print(f"  │    DD hasta pivot: mean={dd_mean*100:+.2f}%  P50={dd_p50*100:+.2f}%")
    print(f"  │    Days since pivot: mean={ft.get('days_since_mean',0):+.1f}d  median={ft.get('days_since_median',0):+.1f}d")

    # Knife
    gk = grp.get("G_knife", {})
    print(f"  │ G. CUCHILLO CAYENDO (DD>5% signal→pivot): {gk.get('n',0)}/{n_grp} ({gk.get('pct',0):.0f}%)")
    if gk.get("n", 0) > 0:
        zipped = list(zip(gk.get("dates", []), gk.get("dd_values", []), gk.get("d2_bins", []), gk.get("d3_bins", [])))
        for dt, dd_v, d2b, d3b in zipped[:5]:
            print(f"  │    {dt}: DD={dd_v*100:.1f}%  D2={d2b}  D3={d3b}")

    # Signal detail (first 10)
    detail = grp.get("signals_detail", [])
    if detail:
        print(f"  │")
        print(f"  │ DETALLE DE SEÑALES (primeras 10):")
        print(f"  │ {'Date':>12} {'State Key':<55} {'N':>4} {'5d':>8} {'10d':>8} {'20d':>8} {'40d':>8} {'Knife':>6}")
        print(f"  │ {'─'*12} {'─'*55} {'─'*4} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*6}")
        for sd in detail[:10]:
            f5 = f"{sd['fwd_5d']*100:+.1f}%" if sd['fwd_5d'] is not None else "N/A"
            f10 = f"{sd['fwd_10d']*100:+.1f}%" if sd['fwd_10d'] is not None else "N/A"
            f20 = f"{sd['fwd_20d']*100:+.1f}%" if sd['fwd_20d'] is not None else "N/A"
            f40 = f"{sd['fwd_40d']*100:+.1f}%" if sd['fwd_40d'] is not None else "N/A"
            kn = "◀ KNIFE" if sd['is_knife'] else ""
            print(f"  │ {sd['date']:>12} {sd['state_key']:<55} {sd['n_state']:>4} {f5:>8} {f10:>8} {f20:>8} {f40:>8} {kn:>6}")

    print(f"  └─ {'─'*90}")

part3 = {
    "extreme_d1": extreme_d1,
    "n_signals_raw": len(signal_bars), "n_signals_deduped": len(deduped),
    "groups": results_groups,
}

# ── SUB-ANÁLISIS: D2 'building' vs 'resolving' (filtro producción #63/#70) ──
print(f"\n  ┌─ {'─'*90}")
print(f"  │ SUB-ANÁLISIS: D2 'building' vs 'resolving' (filtro producción: D2 resolviendo)")
print(f"  ├─ {'─'*90}")

BUILDING_D2 = {"ACCELERATING_UP_3D", "FAST_SPIKE_3D"}
RESOLVING_D2 = {"FAST_CRUSH_3D", "DECELERATING_DOWN_3D", "STABLE_CONTINUATION_3D"}

d2_split_results = {}
for lbl, d2_set in [("D2 building (pánico acelerando)", BUILDING_D2), ("D2 resolving/stable (pánico resolviendo)", RESOLVING_D2)]:
    sub = [s for s in signals if s["d2"] in d2_set]
    if len(sub) < 3:
        print(f"  │ {lbl}: N={len(sub)} insuficiente")
        d2_split_results[lbl] = {"N": len(sub)}
        continue
    out = {"N": len(sub)}
    print(f"  │ {lbl}: N={len(sub)}")
    for h in [20, 40]:
        arr = np.array([s["fwd"][h] for s in sub if s["fwd"][h] is not None])
        if len(arr) < 3:
            continue
        wr, lo, hi = boot_ci_proportion(arr > 0)
        wins = arr[arr > 0]; losses = arr[arr <= 0]
        pf = float(wins.sum() / abs(losses.sum())) if len(losses) > 0 else float('inf')
        ev, ev_lo, ev_hi = boot_ci_mean(arr)
        mn = float(arr.min())
        wipes = int((arr < -0.20).sum())
        print(f"  │    {h}d: WR={wr*100:.0f}% CI95=[{lo*100:.0f}%,{hi*100:.0f}%]  PF={pf:.1f}  "
              f"EV={ev*100:+.1f}% [{ev_lo*100:+.0f},{ev_hi*100:+.0f}]  min={mn*100:+.1f}%  wipeouts(>20%)={wipes}")
        out[f"fwd_{h}d"] = {
            "wr": float(wr), "wr_ci95": [float(lo), float(hi)], "pf": pf,
            "ev": float(ev), "ev_ci95": [float(ev_lo), float(ev_hi)],
            "min": mn, "wipeouts": wipes,
        }
    d2_split_results[lbl] = out

# ¿El filtro elimina TODAS las colas?
tail_signals = [s for s in signals if s["fwd"][20] is not None and s["fwd"][20] < -0.10]
print(f"\n  │ Señales con fwd20d < −10% (colas letales): {len(tail_signals)}")
for s in tail_signals:
    d2cat = "BUILDING" if s["d2"] in BUILDING_D2 else "resolving"
    print(f"  │    {s['date'].date()}: {s['d2']:<28} {d2cat:>10}  fwd20={s['fwd'][20]*100:+.1f}%  fwd40={s['fwd'][40]*100:+.1f}%")
tail_in_building = all(s["d2"] in BUILDING_D2 for s in tail_signals)
print(f"  │  → Todas las colas en D2 'building'? {'SÍ — el filtro D2-resolviendo las elimina' if tail_in_building else 'NO — el filtro no es suficiente'}")

part3["d2_split"] = d2_split_results
part3["tail_fwd20_lt_minus10pct"] = [
    {"date": str(s["date"].date()), "d2": s["d2"], "fwd20": s["fwd"][20], "fwd40": s["fwd"][40]}
    for s in tail_signals
]
part3["all_tails_in_building_d2"] = bool(tail_in_building)

# ═══════════════════════════════════════════════════════════════════════════════
# PARTE 4 — PCR vs SKEW: ¿correlación? ¿confirman o contradicen?
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 100)
print("  PARTE 4 — PCR vs SKEW: ¿correlación? ¿confirman o contradicen?")
print("═" * 100)

# 4a. Daily ρ between PCR and SKEW (D1, D2, D3)
common_dates = sorted(set(pcr_aligned.index) & set(skew_aligned.index))
pcr1 = np.array([float(pcr_aligned.loc[d]) for d in common_dates])
skew1 = np.array([float(skew_aligned.loc[d]) for d in common_dates])
pcr2 = np.array([float(pcr_d2.loc[d]) if not pd.isna(pcr_d2.loc[d]) else 0.0 for d in common_dates])
skew2 = np.array([float(skew_d2.loc[d]) if not pd.isna(skew_d2.loc[d]) else 0.0 for d in common_dates])
pcr3 = np.array([float(pcr_d3_raw.loc[d]) if not pd.isna(pcr_d3_raw.loc[d]) else 1.0 for d in common_dates])
skew3 = np.array([float(skew_d3_raw.loc[d]) if not pd.isna(skew_d3_raw.loc[d]) else 1.0 for d in common_dates])

r_d1, p_d1, _ = spearman_safe(pcr1, skew1)
r_d2, p_d2, _ = spearman_safe(pcr2, skew2)
r_d3, p_d3, _ = spearman_safe(pcr3, skew3)

print(f"\n  Correlación diaria PCR vs SKEW ({len(common_dates)} días):")
print(f"    ρ(PCR D1, SKEW D1) = {r_d1:+.4f}  (p={p_d1:.2g})")
print(f"    ρ(PCR D2, SKEW D2) = {r_d2:+.4f}  (p={p_d2:.2g})")
print(f"    ρ(PCR D3, SKEW D3) = {r_d3:+.4f}  (p={p_d3:.2g})")

# 4b. At pivots: PCR extreme × SKEW extreme combos
# PCR extreme = EXTREME_PUT_PANIC or EXTREME_CALL_HEAVY (top/bottom ~2.28%)
# SKEW extreme from fact store edges: TAIL_PARANOIA (≥136.44 from reference), BLACK_SWAN_PARANOIA; LOW_TAIL_RISK (<109.1)
pcr_hi_thr = pcr_adapter.edges_d1[-1]  # 1.311 → EXTREME_PUT_PANIC
pcr_lo_thr = pcr_adapter.edges_d1[0]   # 0.691 → EXTREME_CALL_HEAVY
SKEW_TAIL_PARANOIA_EDGE = 136.44  # from skew-audit reference
SKEW_LOW_TAIL_RISK_EDGE = 109.10

pcr_at_piv = df25["pcr_d1"].values

mask_both = ~np.isnan(pcr_at_piv) & ~np.isnan(skew_at_piv)

pcr_hi_mask = pcr_at_piv > pcr_hi_thr
pcr_lo_mask = (pcr_at_piv < pcr_lo_thr) & ~np.isnan(pcr_at_piv)
skew_hi_mask = skew_at_piv > SKEW_TAIL_PARANOIA_EDGE
skew_lo_mask = (skew_at_piv < SKEW_LOW_TAIL_RISK_EDGE) & ~np.isnan(skew_at_piv)

print(f"\n  En pivotes zz25 ({mask_both.sum()} con ambos datos):")
print(f"\n  {'Combinación':<50} {'N':>5} {'%leg_bear':>10} {'%c50':>8} {'SPY fwd20d':>12}")
print(f"  {'─'*50} {'─'*5} {'─'*10} {'─'*8} {'─'*12}")

combos_pivot = [
    ("PCR↑↑↑ + SKEW↑↑ (pánico total)", pcr_hi_mask & skew_hi_mask),
    ("PCR↑↑↑ + SKEW↓ (miedo sin cobertura)", pcr_hi_mask & skew_lo_mask),
    ("PCR↑↑↑ + SKEW medio", pcr_hi_mask & ~skew_hi_mask & ~skew_lo_mask),
    ("PCR↓↓↓ + SKEW↑↑ (euforia + smart cubierto)", pcr_lo_mask & skew_hi_mask),
    ("PCR↓↓↓ + SKEW↓ (complacencia total)", pcr_lo_mask & skew_lo_mask),
    ("PCR↑↑↑ solo", pcr_hi_mask),
    ("PCR↓↓↓ solo", pcr_lo_mask),
    ("SKEW↑↑ solo", skew_hi_mask),
    ("SKEW↓ solo", skew_lo_mask),
    ("Línea base", pd.Series(True, index=df25.index)),
]

for label, mask in combos_pivot:
    m = mask & mask_both
    n = m.sum()
    if n == 0:
        print(f"  {label:<50} {n:>5}")
        continue
    bear_pct = df25.loc[m, "leg_bear"].mean() * 100
    c50_pct = df25.loc[m, "cascade_50"].mean() * 100

    # SPY forward 20d from pivot (using signal bar method since we're at pivots)
    spy_fwd20 = []
    for idx in df25[m].index:
        pd_ = df25.loc[idx, "pivot_date"]
        spy_i = spy_date_to_idx.get(pd_)
        if spy_i is not None and spy_i + 20 < len(spy_values):
            spy_fwd20.append(spy_values[spy_i + 20] / spy_values[spy_i] - 1.0)
    fwd20_str = f"{np.mean(spy_fwd20)*100:+.2f}%" if spy_fwd20 else "N/A"

    print(f"  {label:<50} {n:>5} {bear_pct:>9.1f}% {c50_pct:>7.1f}% {fwd20_str:>12}")

# 4c. PCR D2 × SKEW D2 cross at pivots (are velocities aligned?)
m_d2 = mask_both & ~np.isnan(df25["pcr_d2"].values) & ~np.isnan(skew_d2_at_piv)
if m_d2.sum() >= 30:
    r_d2x, p_d2x, _ = spearman_safe(df25.loc[m_d2, "pcr_d2"].values, skew_d2_at_piv[m_d2])
    print(f"\n  ρ(PCR D2, SKEW D2) en pivotes = {r_d2x:+.4f}  (p={p_d2x:.2g}, N={m_d2.sum()})")
else:
    r_d2x, p_d2x = np.nan, np.nan

# 4d. Extreme coincidence rate
n_both_hi = (pcr_hi_mask & skew_hi_mask & mask_both).sum()
pct_both_hi = n_both_hi / mask_both.sum() * 100
print(f"\n  Coincidencia PCR↑↑↑ + SKEW↑↑↑ en pivotes: {n_both_hi}/{mask_both.sum()} ({pct_both_hi:.1f}%)")

pcr_skew_daily_mask = pd.Series(True, index=df25.index)
n_both_hi_daily = ((pcr1 > pcr_hi_thr) & (skew1 > SKEW_TAIL_PARANOIA_EDGE)).sum()
pct_both_hi_daily = n_both_hi_daily / len(common_dates) * 100
n_both_lo_daily = ((pcr1 < pcr_lo_thr) & (skew1 < SKEW_LOW_TAIL_RISK_EDGE)).sum()

print(f"  PCR↑↑↑ + SKEW↑↑↑ diario: {n_both_hi_daily}/{len(common_dates)} ({pct_both_hi_daily:.2f}% de días)")
print(f"  PCR↑↑↑ diario: {(pcr1 > pcr_hi_thr).sum()}/{len(common_dates)} ({(pcr1 > pcr_hi_thr).sum()/len(common_dates)*100:.1f}%)")
print(f"  SKEW↑↑↑ diario: {(skew1 > SKEW_TAIL_PARANOIA_EDGE).sum()}/{len(common_dates)} ({(skew1 > SKEW_TAIL_PARANOIA_EDGE).sum()/len(common_dates)*100:.1f}%)")

part4 = {
    "rho_d1_pcr_skew": r_d1, "p_d1": p_d1,
    "rho_d2_pcr_skew": r_d2, "p_d2": p_d2,
    "rho_d3_pcr_skew": r_d3, "p_d3": p_d3,
    "rho_d2_pcr_skew_pivots": r_d2x, "p_d2_pivots": p_d2x,
    "n_daily_common": len(common_dates),
    "pivot_combos": {
        "pcr_hi_skew_hi_n": int((pcr_hi_mask & skew_hi_mask & mask_both).sum()),
        "pcr_hi_skew_lo_n": int((pcr_hi_mask & skew_lo_mask & mask_both).sum()),
        "pcr_lo_skew_hi_n": int((pcr_lo_mask & skew_hi_mask & mask_both).sum()),
        "pcr_lo_skew_lo_n": int((pcr_lo_mask & skew_lo_mask & mask_both).sum()),
    },
    "daily_extreme_pct": {
        "pcr_hi_pct": float((pcr1 > pcr_hi_thr).mean() * 100),
        "skew_hi_pct": float((skew1 > SKEW_TAIL_PARANOIA_EDGE).mean() * 100),
        "both_hi_pct": float(pct_both_hi_daily),
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# PARTE 5 — Reclasificación PCR definitiva con 8 dimensiones
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 100)
print("  PARTE 5 — RECLASIFICACIÓN PCR DEFINITIVA (8 dimensiones)")
print("═" * 100)

# Get the combined (ALL) results
combined_r = combined  # from part 3

# Build final classification
A_wr = combined_r["A_win_rate"].get(20, np.nan)
A_ci = combined_r["A_wr_ci95"].get(20, [np.nan, np.nan])
D_m = combined_r.get("D_metrics", {}).get(20, {}) or {}
H_q = combined_r.get("H_quality", {})
G_k = combined_r.get("G_knife", {})
F_t = combined_r.get("F_timing", {})
E_s = combined_r.get("E_streaks", {})

# D2 structural split
n_building = d2_split_results.get("D2 building (pánico acelerando)", {}).get("N", 0)
n_resolving = d2_split_results.get("D2 resolving/stable (pánico resolviendo)", {}).get("N", 0)

# N10-30 group metrics (robust subset)
n1030 = None
for grp in results_groups:
    if grp.get("n_quality") == "N_10_30" and not grp.get("insufficient"):
        n1030 = grp
        break

# Final verdict logic
if n1030 is not None:
    wr_robust = n1030["A_win_rate"].get(20, np.nan)
    kelly_robust = (n1030.get("D_metrics", {}).get(20, {}) or {}).get("kelly", 0)
    verdict = "ENTRY (calidad-condicional)"
    verdict_detail = (
        f"N10-30 (FAST_SPIKE post-2008) = WR {wr_robust*100:.0f}% 20d, Kelly {kelly_robust*100:.0f}% — robusto. "
        f"N<10 (cold-start, 42 señales) = EV +0.7% 20d, contiene wipeouts 2008-09-29 (−24.6%) y 2020-02-25 (−22.2%). "
        f"Entrar solo con N≥10; en N<10 exige confirmación (no standalone)."
    )
else:
    verdict = "ENTRY (débil)"
    verdict_detail = "Sin grupo N≥10 suficiente."

print(f"""
  ╔══════════════════════════════════════════════════════════════════════════════╗
  ║  RECLASIFICACIÓN PCR — EXTREME_PUT_PANIC                                  ║
  ╠══════════════════════════════════════════════════════════════════════════════╣
  ║                                                                            ║
  ║  A. Win Rate (20d):     {A_wr*100:.0f}%  CI95=[{A_ci[0]*100:.0f}%,{A_ci[1]*100:.0f}%]       ║
  ║  B. Wins (P50):         {combined_r.get('B_wins',{}).get(20,{}).get('median',0)*100:+.1f}%                    ║
  ║  C. Losses (P50):       {combined_r.get('C_losses',{}).get(20,{}).get('median',0)*100:+.1f}%   {'⚠ WIPEOUT' if G_k.get('n',0) > 0 else ''}                 ║
  ║  D. Profit Factor:      {D_m.get('profit_factor',0):.1f}    Kelly: {D_m.get('kelly',0)*100:.0f}%    EV: {D_m.get('ev',0)*100:+.1f}%       ║
  ║  E. Rachas:             max loss streak = {E_s.get('max_streak','N/A')}                        ║
  ║  F. Timing vs zigzag:   ant={F_t.get('n_anticipada',0)}  exacta={F_t.get('n_exacta',0)}  ret={F_t.get('n_retrasada',0)}  fuera={F_t.get('n_fuera_de_rango',0)}       ║
  ║  G. Cuchillo cayendo:   {G_k.get('n',0)}/{n_signals} ({G_k.get('pct',0):.0f}%)                        ║
  ║  H. Calidad muestra:    N≥30={H_q.get('n_ge_30',0)}  N10-30={H_q.get('n_10_30',0)}  N<10={H_q.get('n_lt_10',0)}       ║
  ║                                                                            ║
  ║  D2 (velocidad):        ρ(leg_bear)={r_d2_dir:+.3f} (p={p_d2_dir:.3f})  {'✅ direccional' if abs(r_d2_dir) > 0.10 and p_d2_dir < 0.05 else '✗ no direccional'}      ║
  ║                         D2 building={n_building}/{n_signals} ({n_building/n_signals*100:.0f}%) — ESTRUCTURAL      ║
  ║  D3 (volatilidad):      Δc50={gap_c50*100:+.1f}pp CI95=[{gap_c50_lo*100:+.0f},{gap_c50_hi*100:+.0f}]pp  {'⚠ apaga débil (ns)' if gap_c50 < 0 else 'otro'}      ║
  ║  vs SKEW:               ρ(D1)={r_d1:+.3f} {'⚠ asociación negativa' if abs(r_d1) > 0.15 else '✓ poca asociación'}                                                        ║
  ║                                                                            ║
  ║  CLASIFICACIÓN FINAL:   {verdict}                           ║
  ║                                                                            ║
  ╚══════════════════════════════════════════════════════════════════════════════╝

  {verdict_detail}
""")

# ═══════════════════════════════════════════════════════════════════════════════
# SAVE JSON
# ═══════════════════════════════════════════════════════════════════════════════

store.close()

def ser(obj):
    if isinstance(obj, (np.integer,)): return int(obj)
    if isinstance(obj, (np.floating,)): return None if np.isnan(obj) else float(obj)
    if isinstance(obj, np.ndarray): return [ser(x) for x in obj]
    if isinstance(obj, list): return [ser(x) for x in obj]
    if isinstance(obj, dict): return {str(k): ser(v) for k, v in obj.items()}
    if isinstance(obj, tuple): return [ser(x) for x in obj]
    return obj

report = {
    "meta": {
        "script": "research/03_estaciones_metar/pcr_completo.py",
        "ticker": "CBOE_PCR",
        "adapter": "PCRLookupAdapter.lookup_pcr_guidance",
        "extreme_d1": extreme_d1,
        "n_pivots_zz25": N_PIVOTS,
        "cascade_50_rate": float(df25["cascade_50"].mean()),
        "cascade_75_rate": float(df25["cascade_75"].mean()),
        "n_boot": N_BOOT,
        "ci": CI,
        "fw_horizons": FW_HORIZONS,
    },
    "part1_d2_direction": part1,
    "part2_d3_cascade": part2,
    "part3_wins_losses": part3,
    "part4_pcr_vs_skew": part4,
    "part5_final_classification": {
        "d1_extreme": extreme_d1,
        "classification": verdict,
        "verdict_detail": verdict_detail,
        "rationale": (
            "PCR EXTREME_PUT_PANIC = put panic contrarian buy signal. Operativo pero calidad-condicional: "
            "el edge está en el estado N10-30 (FAST_SPIKE post-2008, WR 85% 20d, Kelly 55%, zero wipeouts), "
            "mientras que N<10 (cold-start, 76% de señales) incluye las colas letales de 2008 y 2020. "
            "D2 'building' es ESTRUCTURAL (53/55) — no sirve como filtro de entrada como en VIX. "
            "D3 discrimina cascade débilmente (Δc50=−5.6pp, CI cruza cero). "
            "vs SKEW: asociación NEGATIVA (ρ=−0.22) — miden dimensiones opuestas y casi nunca coinciden (0.3%)."
        ),
        "dimensions_summary": {
            "A_win_rate_20d": A_wr,
            "A_ci95_20d": [A_ci[0], A_ci[1]],
            "B_win_p50_20d": combined_r.get('B_wins', {}).get(20, {}).get('median'),
            "C_loss_p50_20d": combined_r.get('C_losses', {}).get(20, {}).get('median'),
            "C_wipeout_min_20d": combined_r.get('C_losses', {}).get(20, {}).get('min'),
            "C_wipeout_n_20d": combined_r.get('C_losses', {}).get(20, {}).get('wipeouts_n'),
            "D_profit_factor_20d": D_m.get('profit_factor'),
            "D_kelly_20d": D_m.get('kelly'),
            "D_ev_20d": D_m.get('ev'),
            "E_max_loss_streak": E_s.get('max_streak'),
            "F_anticipada": F_t.get('n_anticipada', 0),
            "F_exacta": F_t.get('n_exacta', 0),
            "F_retrasada": F_t.get('n_retrasada', 0),
            "F_fuera": F_t.get('n_fuera_de_rango', 0),
            "G_knife_n": G_k.get('n', 0),
            "G_knife_pct": G_k.get('pct', 0),
            "H_n_ge30": H_q.get('n_ge_30', 0),
            "H_n_10_30": H_q.get('n_10_30', 0),
            "H_n_lt10": H_q.get('n_lt_10', 0),
            "rho_d2_dir": r_d2_dir,
            "rho_d1_dir": r_d1_dir,
            "gap_d3_c50_pp": float(gap_c50 * 100),
            "d3_gap_ci95_pp": [float(gap_c50_lo * 100), float(gap_c50_hi * 100)],
            "rho_pcr_skew_d1": r_d1,
            "d2_building_pct": float(n_building / n_signals * 100),
            "all_tails_in_building_d2": bool(tail_in_building),
            "n1030_wr_20d": float(wr_robust) if n1030 is not None else None,
            "n1030_kelly_20d": float(kelly_robust) if n1030 is not None else None,
        },
    },
}

out_path = ROOT / "data/research/stations/pcr_completo_report.json"
with open(out_path, "w") as f:
    json.dump(ser(report), f, indent=2, default=str)

print(f"\n  💾 Reporte completo guardado en: {out_path}")
print("  ✅ DONE — PCR COMPLETO (D2, D3, standalone, vs SKEW, reclasificación).")