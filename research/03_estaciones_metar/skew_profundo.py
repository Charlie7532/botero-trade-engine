#!/usr/bin/env python3
"""
SKEW PROFUNDO — capa de riesgo de cola (Botero Trade)
=====================================================

4 partes:
  1. CUADRANTE VIX×SKEW — 4 regímenes, forward returns 20/40/60d.
  2. LOW_TAIL_RISK LETAL vs SANO — 2008 (−40%) vs 2009 (+40%).
  3. SKEW como EARLY WARNING — timing vs crashes, ¿precede drawdowns?
  4. SKEW D2/D3 — velocidad (D2) y volatilidad (D3) como señales propias.

Método: barras diarias SPY/SKEW/VIX, %iles P15/P85 para cuartiles.
CI95 bootstrap 2000 iteraciones, seed 42.
Forward returns solapados (raw) + de-cluster ≥20d trading.
"""

import sys, json
from pathlib import Path
from datetime import timedelta, date
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter
from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter

# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def boot_ci_mean(arr, n_boot=2000, seed=42, ci=95):
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    means = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    means.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float(arr.mean()), float(np.percentile(means, lo)), float(np.percentile(means, hi))


def boot_ci_wr(arr, n_boot=2000, seed=42, ci=95):
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    props = (rng.choice(arr, size=(n_boot, len(arr)), replace=True) > 0).mean(axis=1)
    props.sort()
    lo = (100 - ci) / 2
    hi = 100 - lo
    return float((arr > 0).mean()), float(np.percentile(props, lo)), float(np.percentile(props, hi))


def compute_d2_d3(series):
    """D2 = diff(3d), D3 = std(2d)/std(10d) — formula pitfall #46."""
    d2 = series.diff(3)
    s2 = series.rolling(2).std()
    s10 = series.rolling(10).std()
    d3 = (s2 / s10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    return d2, d3


def de_cluster(dates, min_td=20):
    """Remove signals closer than min_td trading days."""
    if len(dates) < 2:
        return dates
    dates = sorted(dates)
    pos_map = {d: i for i, d in enumerate(aligned_dates)}
    keep = [dates[0]]
    for d in dates[1:]:
        if d in pos_map and keep[-1] in pos_map:
            if pos_map[d] - pos_map[keep[-1]] >= min_td:
                keep.append(d)
        else:
            keep.append(d)
    return keep


def fwd_return_at(spy_s, entry_date, horizon_td):
    """Forward return in % from entry_date, horizon_td trading days."""
    idx = spy_s.index.get_loc(entry_date)
    future_idx = idx + horizon_td
    if future_idx >= len(spy_s):
        return np.nan
    return float((spy_s.iloc[future_idx] / spy_s.iloc[idx] - 1) * 100)


def quadrant_stats(dates, spy_s, horizons, name):
    """Compute forward returns for a list of entry dates (can be overlapping)."""
    results = {}
    for h in horizons:
        rets = np.array([fwd_return_at(spy_s, d, h) for d in dates])
        rets = rets[~np.isnan(rets)]
        if len(rets) < 2:
            results[h] = None
            continue
        wins = rets[rets > 0]
        losses = rets[rets <= 0]
        mean_val, ci_lo, ci_hi = boot_ci_mean(rets)
        wr, wr_lo, wr_hi = boot_ci_wr(rets)
        results[h] = {
            "n": int(len(rets)),
            "n_wins": int(len(wins)),
            "n_losses": int(len(losses)),
            "mean": float(np.mean(rets)),
            "median": float(np.median(rets)),
            "std": float(np.std(rets)),
            "ci95_mean": [float(ci_lo), float(ci_hi)],
            "win_rate": float(wr),
            "ci95_wr": [float(wr_lo), float(wr_hi)],
            "min": float(np.min(rets)),
            "max": float(np.max(rets)),
            "p10": float(np.percentile(rets, 10)),
            "p25": float(np.percentile(rets, 25)),
            "p75": float(np.percentile(rets, 75)),
            "p90": float(np.percentile(rets, 90)),
            "wipeouts_gt20": int((rets < -20).sum()),
            "wipeouts_gt20_pct": float((rets < -20).mean() * 100) if len(rets) > 0 else 0,
            "avg_win": float(np.mean(wins)) if len(wins) > 0 else 0,
            "avg_loss": float(np.mean(losses)) if len(losses) > 0 else 0,
            "profit_factor": float(wins.sum() / abs(losses.sum())) if abs(losses.sum()) > 0 else (np.inf if len(wins) > 0 else 0),
            "win_p25": float(np.percentile(wins, 25)) if len(wins) > 2 else 0,
            "win_p50": float(np.percentile(wins, 50)) if len(wins) > 2 else 0,
            "win_p75": float(np.percentile(wins, 75)) if len(wins) > 2 else 0,
            "win_max": float(np.max(wins)) if len(wins) > 0 else 0,
            "loss_p25": float(np.percentile(losses, 25)) if len(losses) > 2 else 0,
            "loss_p50": float(np.percentile(losses, 50)) if len(losses) > 2 else 0,
            "loss_p75": float(np.percentile(losses, 75)) if len(losses) > 2 else 0,
            "loss_min": float(np.min(losses)) if len(losses) > 0 else 0,
        }
    return results


# ═══════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ═══════════════════════════════════════════════════════════════════════════

print("═══ CARGANDO DATOS ═══")
store = TimescaleDataStore()

spy_raw = store.load_bars("SPY", "1d")["close"].copy()
spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()

skew_raw = store.load_bars("SKEW", "1d")["close"].copy()
skew_raw.index = pd.to_datetime(skew_raw.index).normalize()
skew = skew_raw[~skew_raw.index.duplicated(keep="last")].sort_index()

vix_raw = store.load_bars("VIX", "1d")["close"].copy()
vix_raw.index = pd.to_datetime(vix_raw.index).normalize()
vix = vix_raw[~vix_raw.index.duplicated(keep="last")].sort_index()

store.close()

# Align
common = sorted(set(spy.index) & set(skew.index) & set(vix.index))
spy_s = spy.loc[common]
skew_s = skew.loc[common]
vix_s = vix.loc[common]
aligned_dates = list(spy_s.index)
n_total = len(aligned_dates)

print(f"Barras alineadas SPY∩SKEW∩VIX: {n_total}")
print(f"Rango: {aligned_dates[0].date()} → {aligned_dates[-1].date()}")

# Compute D2/D3
skew_d2, skew_d3 = compute_d2_d3(skew_s)
vix_d2, vix_d3 = compute_d2_d3(vix_s)

# Adapters
sk_adapter = SkewLookupAdapter()
vx_adapter = VIXLookupAdapter()

# Percentile splits
skew_p15 = float(skew_s.quantile(0.15))
skew_p85 = float(skew_s.quantile(0.85))
vix_p85 = float(vix_s.quantile(0.85))
vix_p15 = float(vix_s.quantile(0.15))

print(f"\nPercentiles (full history {aligned_dates[0].date()} → {aligned_dates[-1].date()}):")
print(f"  SKEW P15={skew_p15:.1f}  P85={skew_p85:.1f}")
print(f"  VIX  P15={vix_p15:.1f}  P85={vix_p85:.1f}")

# Binary masks
skew_hi = skew_s >= skew_p85       # SKEW↑
skew_lo = skew_s < skew_p15        # SKEW BAJO (complacencia)
vix_hi = vix_s >= vix_p85          # VIX↑ (crisis)
vix_lo = vix_s < vix_p15           # VIX↓ (calma profunda)

# Quadrant masks (2×2, covering 100%: ↑ = ≥P85, ↓ = <P85)
q_panico   = skew_hi & vix_hi                     # PÁNICO TOTAL
q_crisis_sin_miedo = (~skew_hi) & vix_hi          # VIX↑ + SKEW↓
q_miedo_silencioso = skew_hi & (~vix_hi)          # VIX↓ + SKEW↑
q_calma    = (~skew_hi) & (~vix_hi)               # VIX↓ + SKEW↓

n_panico = q_panico.sum()
n_crisis_sin_miedo = q_crisis_sin_miedo.sum()
n_miedo_silencioso = q_miedo_silencioso.sum()
n_calma = q_calma.sum()

print(f"\nCUADRANTE VIX×SKEW (barras diarias, P85 split):")
print(f"  PÁNICO TOTAL (VIX↑+SKEW↑):         {n_panico:>5} ({n_panico/n_total*100:.1f}%)")
print(f"  Crisis sin miedo (VIX↑+SKEW↓):     {n_crisis_sin_miedo:>5} ({n_crisis_sin_miedo/n_total*100:.1f}%)")
print(f"  Miedo silencioso (VIX↓+SKEW↑):     {n_miedo_silencioso:>5} ({n_miedo_silencioso/n_total*100:.1f}%)")
print(f"  Calma total (VIX↓+SKEW↓):          {n_calma:>5} ({n_calma/n_total*100:.1f}%)")

# Also: SKEW bajo (<P15) durante crisis (la "complacencia peligrosa")
q_complacencia_crisis = skew_lo & vix_hi
n_cc = q_complacencia_crisis.sum()
print(f"  ── Complacencia+crisis (SKEW<P15 + VIX↑): {n_cc:>5} ({n_cc/n_total*100:.1f}%) — la letal")

# Post-2011 subset (robustness vs secular drift)
post2011 = np.array([d.date() >= date(2011, 1, 1) for d in aligned_dates])
n_post2011 = int(post2011.sum())
print(f"\n  Post-2011: {n_post2011} barras ({n_post2011/n_total*100:.0f}%)")

# ═══════════════════════════════════════════════════════════════════════════
# PART 1: CUADRANTE VIX×SKEW — FORWARD RETURNS
# ═══════════════════════════════════════════════════════════════════════════

print("\n\n" + "╔" + "═" * 78 + "╗")
print("║  PARTE 1: CUADRANTE VIX×SKEW — FORWARD RETURNS 20/40/60d".center(78) + "║")
print("╚" + "═" * 78 + "╝")

HORIZONS = [20, 40, 60]
QUADRANTS = [
    ("PÁNICO TOTAL (VIX↑+SKEW↑)", q_panico, "🔴"),
    ("Crisis sin miedo (VIX↑+SKEW↓)", q_crisis_sin_miedo, "🟠"),
    ("Miedo silencioso (VIX↓+SKEW↑)", q_miedo_silencioso, "🟡"),
    ("Calma total (VIX↓+SKEW↓)", q_calma, "🟢"),
]

part1_results = {}
for name, mask, icon in QUADRANTS:
    dates = [aligned_dates[i] for i in range(n_total) if mask.iloc[i]]
    stats = quadrant_stats(dates, spy_s, HORIZONS, name)

    print(f"\n{'─'*80}")
    print(f"  {icon} {name}  |  N={mask.sum()} barras ({mask.sum()/n_total*100:.1f}%)")
    print(f"{'─'*80}")

    for h in HORIZONS:
        s = stats.get(h)
        if s is None:
            print(f"    {h}d: N insuficiente")
            continue
        print(f"\n    ═══ FORWARD {h}d (N={s['n']}) ═══")
        print(f"      Return: mean={s['mean']:+.2f}%  median={s['median']:+.2f}%  "
              f"CI95=[{s['ci95_mean'][0]:+.2f}%, {s['ci95_mean'][1]:+.2f}%]")
        print(f"      Win Rate: {s['win_rate']*100:.1f}%  CI95=[{s['ci95_wr'][0]*100:.1f}%, {s['ci95_wr'][1]*100:.1f}%]")
        print(f"      Wins: {s['n_wins']} (mean={s['avg_win']:+.2f}%, p50={s['win_p50']:+.2f}%, max={s['win_max']:+.2f}%)")
        print(f"      Losses: {s['n_losses']} (mean={s['avg_loss']:+.2f}%, p50={s['loss_p50']:+.2f}%, min={s['loss_min']:+.2f}%)")
        print(f"      Profit Factor: {s['profit_factor']:.2f}" if s['profit_factor'] != np.inf else f"      Profit Factor: ∞")
        print(f"      P10: {s['p10']:+.2f}%  P90: {s['p90']:+.2f}%  Wipeouts>20%: {s['wipeouts_gt20']} ({s['wipeouts_gt20_pct']:.1f}%)")

    part1_results[name] = stats

# ── DE-CLUSTERED (≥20 trading days) for cleaner stats ──
print(f"\n\n{'─'*80}")
print(f"  ── DE-CLUSTERED (≥20 trading days) ──")
print(f"{'─'*80}")

for name, mask, icon in QUADRANTS:
    raw_dates = [aligned_dates[i] for i in range(n_total) if mask.iloc[i]]
    dc_dates = de_cluster(raw_dates, min_td=20)
    dc_stats = quadrant_stats(dc_dates, spy_s, HORIZONS, f"{name} (de-cluster)")

    print(f"\n  {icon} {name} — De-clustered:")
    print(f"    Barras raw: {len(raw_dates)} → De-clustered (≥20d): {len(dc_dates)}")
    for h in HORIZONS:
        s = dc_stats.get(h)
        if s is None or s['n'] < 5:
            print(f"    {h}d: N<5, insuficiente")
            continue
        print(f"    {h}d: N={s['n']:>3d}  mean={s['mean']:+.2f}%  WR={s['win_rate']*100:.0f}%  "
              f"CI95=[{s['ci95_mean'][0]:+.2f}%, {s['ci95_mean'][1]:+.2f}%]  PF={s['profit_factor']:.2f}")


# ═══════════════════════════════════════════════════════════════════════════
# PART 2: LOW_TAIL_RISK LETAL vs SANO
# ═══════════════════════════════════════════════════════════════════════════

print("\n\n" + "╔" + "═" * 78 + "╗")
print("║  PARTE 2: LOW_TAIL_RISK LETAL vs SANO — 2008 vs 2009".center(78) + "║")
print("╚" + "═" * 78 + "╝")

# Use SKEW < P15 as "LOW_TAIL_RISK" (matches <~113 ≈ the D1 edge 114.67)
# Also compute D1 classification for the full state vector
low_tail_mask = skew_lo  # SKEW < P15

# Compute SPY drawdown from peak
spy_peak = spy_s.cummax()
spy_dd = (spy_s / spy_peak - 1) * 100  # % drawdown from peak

# Classify each low-tail day by market phase
lt_dates_all = [aligned_dates[i] for i in range(n_total) if low_tail_mask.iloc[i]]
print(f"\nLOW_TAIL_RISK días (SKEW < P15={skew_p15:.0f}): {len(lt_dates_all)}")

# De-cluster to episodes
lt_dates = de_cluster(lt_dates_all, min_td=60)  # wider to get distinct episodes
print(f"Episodios de-clustered (≥60d trading): {len(lt_dates)}")

# For each episode, capture context
lt_episodes = []
for dt in lt_dates:
    i = aligned_dates.index(dt)
    sval = float(skew_s.iloc[i]) if i < len(skew_s) else np.nan
    vval = float(vix_s.iloc[i]) if i < len(vix_s) else np.nan
    s_d2 = float(skew_d2.iloc[i]) if not pd.isna(skew_d2.iloc[i]) else 0.0
    s_d3 = float(skew_d3.iloc[i]) if not pd.isna(skew_d3.iloc[i]) else 1.0
    dd_val = float(spy_dd.iloc[i]) if i < len(spy_dd) else 0.0
    spy_val = float(spy_s.iloc[i])

    # VIX D1
    vix_d1 = "?"
    try:
        vg = vx_adapter.lookup_vix_guidance(val=vval, d3_speed=0.0, vol_norm=1.0, vol_d3=0.0)
        if vg: vix_d1 = vg.state_key.split("__")[0]
    except: pass

    # SKEW D1
    skew_d1 = sk_adapter._classify_d1(sval)

    # Forward SPY at 20/60/120/250 trading days
    f20 = fwd_return_at(spy_s, dt, 20)
    f60 = fwd_return_at(spy_s, dt, 60)
    f120 = fwd_return_at(spy_s, dt, 120)
    f250 = fwd_return_at(spy_s, dt, 250)

    lt_episodes.append({
        "date": str(dt.date()),
        "skew": sval, "vix": vval,
        "skew_d1": skew_d1, "vix_d1": vix_d1,
        "d2": float(s_d2), "d3": float(s_d3),
        "spy_dd": float(dd_val), "spy": float(spy_val),
        "f20": f20, "f60": f60, "f120": f120, "f250": f250,
    })

# ── 2008 vs 2009 specific episodes ──
print(f"\n═══ EPISODIOS LOW_TAIL_RISK 2007-2010 (contexto GFC) ═══")
gfc_eps = [e for e in lt_episodes if "2007" <= e["date"][:4] <= "2010"]
for e in sorted(gfc_eps, key=lambda x: x["date"]):
    print(f"  {e['date']}: SKEW={e['skew']:.1f} VIX={e['vix']:.1f} "
          f"D2={e['d2']:+.1f} D3={e['d3']:.2f} "
          f"SPY={e['spy']:.1f} DD={e['spy_dd']:+.1f}% "
          f"→ f20={e['f20']:+.1f}% f60={e['f60']:+.1f}% f120={e['f120']:+.1f}% f250={e['f250']:+.1f}%")

# ── DISCRIMINATION: what separates lethal from healthy ──
print(f"\n═══ DISCRIMINACIÓN: LETAL vs SANO ═══")
print(f"  ¿Qué distingue un LOW_TAIL_RISK que precede -40% de uno que precede +40%?")

# Split by VIX regime (the key hypothesis from orthogonality)
lt_vix_crisis = [e for e in lt_episodes if e["vix"] >= vix_p85]
lt_vix_calm = [e for e in lt_episodes if e["vix"] < vix_p85]

print(f"\n  ── LOW_TAIL_RISK + VIX↑ (crisis, N={len(lt_vix_crisis)}) — ¿la letal? ──")
for h_label, h_key in [("20d","f20"),("60d","f60"),("120d","f120"),("250d","f250")]:
    rets = np.array([e[h_key] for e in lt_vix_crisis if not np.isnan(e[h_key])])
    if len(rets) >= 3:
        n_w = int((rets>0).sum()); n_l = int((rets<=0).sum())
        mean_v, lo, hi = boot_ci_mean(rets)
        wr, wrl, wrh = boot_ci_wr(rets)
        print(f"    {h_label}: N={len(rets)}  mean={mean_v:+.2f}% CI95=[{lo:+.2f},{hi:+.2f}]  "
              f"WR={wr*100:.1f}%  wins={n_w} losses={n_l}")

print(f"\n  ── LOW_TAIL_RISK + VIX↓ (calma, N={len(lt_vix_calm)}) — ¿la sana? ──")
for h_label, h_key in [("20d","f20"),("60d","f60"),("120d","f120"),("250d","f250")]:
    rets = np.array([e[h_key] for e in lt_vix_calm if not np.isnan(e[h_key])])
    if len(rets) >= 3:
        n_w = int((rets>0).sum()); n_l = int((rets<=0).sum())
        mean_v, lo, hi = boot_ci_mean(rets)
        wr, wrl, wrh = boot_ci_wr(rets)
        print(f"    {h_label}: N={len(rets)}  mean={mean_v:+.2f}% CI95=[{lo:+.2f},{hi:+.2f}]  "
              f"WR={wr*100:.1f}%  wins={n_w} losses={n_l}")

# Split by SPY drawdown
print(f"\n  ── LOW_TAIL_RISK + SPY en drawdown <-10% vs no drawdown ──")
lt_dd = [e for e in lt_episodes if e["spy_dd"] < -10]
lt_no_dd = [e for e in lt_episodes if e["spy_dd"] >= -10]
print(f"    SPY DD<-10%: N={len(lt_dd)}")
print(f"    SPY DD≥-10%: N={len(lt_no_dd)}")
for h_label, h_key in [("60d","f60"),("250d","f250")]:
    for dd_lbl, dd_list in [("DD<-10%",lt_dd), ("DD≥-10%",lt_no_dd)]:
        rets = np.array([e[h_key] for e in dd_list if not np.isnan(e[h_key])])
        if len(rets) >= 3:
            mean_v, lo, hi = boot_ci_mean(rets)
            wr, _, _ = boot_ci_wr(rets)
            print(f"    {h_label} {dd_lbl}: N={len(rets)}  mean={mean_v:+.2f}% CI95=[{lo:+.2f},{hi:+.2f}] WR={wr*100:.0f}%")

# D2 split: FAST_CRUSH (skew falling fast) vs not
skew_d2_edges = sk_adapter.edges_d2
lt_crush = [e for e in lt_episodes if e["d2"] < skew_d2_edges[0]]  # FAST_CRUSH
lt_not_crush = [e for e in lt_episodes if e["d2"] >= skew_d2_edges[0]]
print(f"\n  ── D2 discrimina: FAST_CRUSH vs not ──")
print(f"    SKEW D2 FAST_CRUSH (<{skew_d2_edges[0]:.1f}): N={len(lt_crush)}")
print(f"    SKEW D2 not crush: N={len(lt_not_crush)}")
for h_label, h_key in [("60d","f60"),("250d","f250")]:
    for lbl, lst in [("FAST_CRUSH",lt_crush), ("no_crush",lt_not_crush)]:
        rets = np.array([e[h_key] for e in lst if not np.isnan(e[h_key])])
        if len(rets) >= 3:
            mean_v, lo, hi = boot_ci_mean(rets)
            wr, _, _ = boot_ci_wr(rets)
            print(f"    {h_label} {lbl}: N={len(rets)}  mean={mean_v:+.2f}% CI95=[{lo:+.2f},{hi:+.2f}] WR={wr*100:.0f}%")

# D3 split
skew_d3_edges = sk_adapter.edges_d3
lt_squeeze = [e for e in lt_episodes if e["d3"] < skew_d3_edges[1]]  # compressed
lt_expansion = [e for e in lt_episodes if e["d3"] >= skew_d3_edges[2]]  # chaotic
print(f"\n  ── D3 discrimina ──")
print(f"    Vol comprimida (D3<{skew_d3_edges[1]:.2f}): N={len(lt_squeeze)}")
print(f"    Vol expansion (D3≥{skew_d3_edges[2]:.2f}): N={len(lt_expansion)}")
for h_label, h_key in [("60d","f60"),("250d","f250")]:
    for lbl, lst in [("COMPRESS",lt_squeeze), ("EXPAND",lt_expansion)]:
        rets = np.array([e[h_key] for e in lst if not np.isnan(e[h_key])])
        if len(rets) >= 3:
            mean_v, lo, hi = boot_ci_mean(rets)
            wr, _, _ = boot_ci_wr(rets)
            print(f"    {h_label} {lbl}: N={len(rets)}  mean={mean_v:+.2f}% CI95=[{lo:+.2f},{hi:+.2f}] WR={wr*100:.0f}%")

# The definitive answer: VIX regime
print(f"\n  ═══ RESPUESTA: ¿qué discrimina LOW_TAIL_RISK letal del sano? ═══")
for h_label, h_key in [("20d","f20"),("40d","f40_approx"),("60d","f60"),("120d","f120"),("250d","f250")]:
    if h_key == "f40_approx":
        # approximate f40 from f60/f20 interpolation? skip for now
        continue
    c_vals = np.array([e[h_key] for e in lt_vix_crisis if not np.isnan(e[h_key])])
    s_vals = np.array([e[h_key] for e in lt_vix_calm if not np.isnan(e[h_key])])
    if len(c_vals) < 3 or len(s_vals) < 3:
        continue
    c_m, c_l, c_h = boot_ci_mean(c_vals)
    s_m, s_l, s_h = boot_ci_mean(s_vals)
    delta = s_m - c_m
    c_wr, _, _ = boot_ci_wr(c_vals)
    s_wr, _, _ = boot_ci_wr(s_vals)
    print(f"  {h_label}:   con VIX↑ → {c_m:+.2f}% CI95[{c_l:+.2f},{c_h:+.2f}] WR={c_wr*100:.0f}%")
    print(f"            con VIX↓ → {s_m:+.2f}% CI95[{s_l:+.2f},{s_h:+.2f}] WR={s_wr*100:.0f}%")
    print(f"            ΔVIX↓-VIX↑ = {delta:+.2f}pp")


# ═══════════════════════════════════════════════════════════════════════════
# PART 3: SKEW como EARLY WARNING
# ═══════════════════════════════════════════════════════════════════════════

print("\n\n" + "╔" + "═" * 78 + "╗")
print("║  PARTE 3: SKEW como EARLY WARNING — timing vs crashes".center(78) + "║")
print("╚" + "═" * 78 + "╝")

# 3a: SKEW at SPY peaks (just before major drawdowns)
# Find SPY drawdown episodes >10%
spy_values = spy_s.values
peak = spy_values[0]
peak_date = aligned_dates[0]
in_dd = False
dd_start = None
dd_episodes = []
prev_dt = aligned_dates[0]
prev_val = spy_values[0]

for i in range(1, len(aligned_dates)):
    val = spy_values[i]
    dt = aligned_dates[i]
    if val > peak:
        peak = val
        peak_date = dt
        if in_dd:
            dd_episodes[-1]["end_date"] = prev_dt
            dd_episodes[-1]["end_val"] = prev_val
        in_dd = False
    dd = (val / peak - 1) * 100
    if dd <= -10 and not in_dd:
        in_dd = True
        dd_episodes.append({
            "peak_date": peak_date, "peak_val": peak,
            "start_date": dt, "start_val": val,
            "start_dd": dd, "end_date": None, "end_val": None,
        })
    if in_dd and val > (dd_episodes[-1]["start_val"] if dd_episodes else 0):
        # trough passed
        pass
    prev_dt = dt
    prev_val = val

# Close last episode
if in_dd and dd_episodes:
    dd_episodes[-1]["end_date"] = aligned_dates[-1]

print(f"\nSPY drawdowns >10%: {len(dd_episodes)}")
for ep in dd_episodes[:10]:
    max_dd_pct = ep.get("max_dd", ep.get("start_dd", 0))
    print(f"  {ep['peak_date'].date()} → {ep['start_date'].date()}: "
          f"peak={ep['peak_val']:.1f}  dd={ep['start_dd']:+.1f}%")

# 3b: For each dd episode, SKEW value at peak, at dd start, at dd-60d, dd+60d
print(f"\n═══ SKEW ALREDEDOR DE DRAWDOWNS >10% ═══")
print(f"  {'Episodio':<25} {'SKEW@Peak':>9} {'SKEW@DD':>9} {'SKEW@-60d':>9} {'SKEW@+60d':>9}")
print(f"  {'─'*25} {'─'*9} {'─'*9} {'─'*9} {'─'*9}")

skew_map = {dt: float(skew_s.loc[dt]) for dt in aligned_dates if dt in skew_s.index}
for ep in dd_episodes:
    pk = ep["peak_date"]
    st = ep["start_date"]
    # Find nearest aligned dates
    def nearest(arr, target):
        candidates = [d for d in arr if d <= target]
        return candidates[-1] if candidates else None

    # SKEW at peak, at start, T-60, T+60
    pk_idx = aligned_dates.index(pk) if pk in aligned_dates else None
    st_idx = aligned_dates.index(st) if st in aligned_dates else None

    sk_pk = skew_map.get(pk, np.nan)
    sk_st = skew_map.get(st, np.nan)

    # T-60, T+60 from start
    if st_idx:
        t_minus = aligned_dates[max(0, st_idx-60)] if st_idx >= 60 else None
        t_plus = aligned_dates[min(len(aligned_dates)-1, st_idx+60)]
        sk_m60 = skew_map.get(t_minus, np.nan) if t_minus else np.nan
        sk_p60 = skew_map.get(t_plus, np.nan)
    else:
        sk_m60 = np.nan; sk_p60 = np.nan

    ep_label = f"{pk.date()}→{st.date()}"
    print(f"  {ep_label:<25} {sk_pk:>9.1f} {sk_st:>9.1f} {sk_m60:>9.1f} {sk_p60:>9.1f}")

# 3c: ¿SKEW alto PRECEDE o SIGUE a crashes?
print(f"\n═══ ¿SKEW alto PRECEDE o SIGUE a crashes? ═══")
skew_before = []
skew_after = []
for ep in dd_episodes:
    st = ep["start_date"]
    st_idx = aligned_dates.index(st) if st in aligned_dates else None
    if st_idx is None: continue
    if st_idx >= 20:
        sk_before = skew_map.get(aligned_dates[max(0, st_idx-20)], np.nan)
        skew_before.append(sk_before)
    if st_idx + 20 < len(aligned_dates):
        sk_after = skew_map.get(aligned_dates[min(len(aligned_dates)-1, st_idx+20)], np.nan)
        skew_after.append(sk_after)

print(f"  SKEW 20d ANTES de drawdown: median={np.nanmedian(skew_before):.1f}, mean={np.nanmean(skew_before):.1f}")
print(f"  SKEW 20d DESPUÉS de drawdown: median={np.nanmedian(skew_after):.1f}, mean={np.nanmean(skew_after):.1f}")

skew_hi_before = sum(1 for s in skew_before if not np.isnan(s) and s >= skew_p85)
skew_hi_after = sum(1 for s in skew_after if not np.isnan(s) and s >= skew_p85)
print(f"  SKEW≥P85 antes: {skew_hi_before}/{sum(1 for s in skew_before if not np.isnan(s))} ({skew_hi_before/max(1,sum(1 for s in skew_before if not np.isnan(s)))*100:.0f}%)")
print(f"  SKEW≥P85 después: {skew_hi_after}/{sum(1 for s in skew_after if not np.isnan(s))} ({skew_hi_after/max(1,sum(1 for s in skew_after if not np.isnan(s)))*100:.0f}%)")

# 3d: ¿LOW_TAIL_RISK precede drawdowns >10%?
print(f"\n═══ ¿LOW_TAIL_RISK precede drawdowns >10%? ═══")
# For each de-clustered LOW_TAIL_RISK signal, does a >10% drawdown follow within 60/120 days?
lt_signals_wide = de_cluster(lt_dates_all, min_td=60)
print(f"  Señales LOW_TAIL_RISK de-clustered (≥60d): {len(lt_signals_wide)}")

for window_days in [60, 120]:
    n_followed = 0
    details = []
    for sig_dt in lt_signals_wide:
        sig_idx = aligned_dates.index(sig_dt)
        end_idx = min(len(aligned_dates)-1, sig_idx + window_days)
        # Check max drawdown in window
        window_peak = spy_s.iloc[sig_idx]
        max_dd = 0.0
        for j in range(sig_idx+1, end_idx+1):
            val = spy_s.iloc[j]
            if val > window_peak:
                window_peak = val
            dd = (val / window_peak - 1) * 100
            max_dd = min(max_dd, dd)
        if max_dd < -10:
            n_followed += 1
            if n_followed <= 15:
                details.append((sig_dt.date(), max_dd))

    base_rate_pct = n_followed / max(1, len(lt_signals_wide)) * 100
    print(f"  → Drawdown >10% en {window_days}d tras LOW_TAIL_RISK:")
    print(f"    {n_followed}/{len(lt_signals_wide)} = {base_rate_pct:.1f}%")
    if details:
        for d, dd in details[:10]:
            print(f"      {d}: maxDD={dd:.1f}%")


# ═══════════════════════════════════════════════════════════════════════════
# PART 4: SKEW D2/D3 — velocidad (D2) y volatilidad (D3)
# ═══════════════════════════════════════════════════════════════════════════

print("\n\n" + "╔" + "═" * 78 + "╗")
print("║  PARTE 4: SKEW D2 (velocidad) y D3 (volatilidad) — señales propias".center(78) + "║")
print("╚" + "═" * 78 + "╝")

# 4a: SKEW D2 standalone — forward returns per D2 bin (ALL days)
print(f"\n═══ SKEW D2 (velocidad Δ3d) — forward returns por bin ═══")
print(f"  Edges D2: {sk_adapter.edges_d2}")
print(f"  Labels D2: {sk_adapter.labels_d2}")

d2_labels = sk_adapter.labels_d2
d2_edges = sk_adapter.edges_d2

for d2_bin in d2_labels:
    # Find all dates where D2 falls in this bin
    dates_in_bin = []
    for i, dt in enumerate(aligned_dates):
        if dt not in skew_d2.index: continue
        d2_val = float(skew_d2.loc[dt]) if not pd.isna(skew_d2.loc[dt]) else 0.0
        cat = sk_adapter._classify_d2(d2_val)
        if cat == d2_bin:
            dates_in_bin.append(dt)

    n_bin = len(dates_in_bin)
    if n_bin < 20:
        print(f"\n  {d2_bin}: N={n_bin} (insuficiente)")
        continue

    stats = quadrant_stats(dates_in_bin, spy_s, HORIZONS, d2_bin)
    print(f"\n  ═══ {d2_bin} (N={n_bin}, {n_bin/n_total*100:.1f}%) ═══")
    for h in HORIZONS:
        s = stats.get(h)
        if s is None: continue
        print(f"    {h}d: mean={s['mean']:+.2f}% CI95=[{s['ci95_mean'][0]:+.2f},{s['ci95_mean'][1]:+.2f}]%  "
              f"WR={s['win_rate']*100:.0f}%  N={s['n']}  PF={s['profit_factor']:.2f}")

# 4b: SKEW D3 standalone — forward returns per D3 bin
print(f"\n\n═══ SKEW D3 (vol std2/std10) — forward returns por bin ═══")
print(f"  Edges D3: {sk_adapter.edges_d3}")
print(f"  Labels D3: {sk_adapter.labels_d3}")

d3_labels = sk_adapter.labels_d3
d3_edges = sk_adapter.edges_d3

for d3_bin in d3_labels:
    dates_in_bin = []
    for i, dt in enumerate(aligned_dates):
        if dt not in skew_d3.index: continue
        d3_val = float(skew_d3.loc[dt]) if not pd.isna(skew_d3.loc[dt]) else 1.0
        cat = sk_adapter._classify_d3(d3_val)
        if cat == d3_bin:
            dates_in_bin.append(dt)

    n_bin = len(dates_in_bin)
    if n_bin < 20:
        print(f"\n  {d3_bin}: N={n_bin} (insuficiente)")
        continue

    stats = quadrant_stats(dates_in_bin, spy_s, HORIZONS, d3_bin)
    print(f"\n  ═══ {d3_bin} (N={n_bin}, {n_bin/n_total*100:.1f}%) ═══")
    for h in HORIZONS:
        s = stats.get(h)
        if s is None: continue
        print(f"    {h}d: mean={s['mean']:+.2f}% CI95=[{s['ci95_mean'][0]:+.2f},{s['ci95_mean'][1]:+.2f}]%  "
              f"WR={s['win_rate']*100:.0f}%  N={s['n']}")

# 4c: D2×D1 interaction: within each SKEW D1 bin, does D2 discriminate?
print(f"\n\n═══ D2×D1: ¿D2 discrimina outcome dentro de cada D1? ═══")
skew_d1_labels = sk_adapter.labels_d1
for d1_bin in skew_d1_labels:
    # Get all dates in this D1 bin
    d1_dates = []
    for i, dt in enumerate(aligned_dates):
        if dt not in skew_s.index: continue
        val = float(skew_s.loc[dt])
        cat = sk_adapter._classify_d1(val)
        if cat == d1_bin:
            d1_dates.append(dt)

    if len(d1_dates) < 50:
        continue

    print(f"\n  ── {d1_bin} (N={len(d1_dates)}) ──")
    # Split by D2
    d2_groups = defaultdict(list)
    for dt in d1_dates:
        if dt not in skew_d2.index: continue
        d2_val = float(skew_d2.loc[dt]) if not pd.isna(skew_d2.loc[dt]) else 0.0
        d2_cat = sk_adapter._classify_d2(d2_val)
        d2_groups[d2_cat].append(dt)

    for d2_bin, dates in sorted(d2_groups.items(), key=lambda x: -len(x[1])):
        n = len(dates)
        if n < 10:
            continue
        f60_rets = np.array([fwd_return_at(spy_s, d, 60) for d in dates])
        f60_rets = f60_rets[~np.isnan(f60_rets)]
        if len(f60_rets) < 5:
            continue
        mean_v, lo, hi = boot_ci_mean(f60_rets)
        wr, _, _ = boot_ci_wr(f60_rets)
        n_w = int((f60_rets > 0).sum())
        n_l = int((f60_rets <= 0).sum())
        print(f"    {d2_bin:<30s} N={n:>4d}  f60d={mean_v:+.2f}% CI95[{lo:+.2f},{hi:+.2f}]  "
              f"WR={wr*100:.0f}%  wins={n_w} losses={n_l}")

# 4d: D3×D1 interaction
print(f"\n\n═══ D3×D1: ¿D3 discrimina outcome dentro de cada D1? ═══")
for d1_bin in skew_d1_labels:
    d1_dates = []
    for i, dt in enumerate(aligned_dates):
        if dt not in skew_s.index: continue
        val = float(skew_s.loc[dt])
        cat = sk_adapter._classify_d1(val)
        if cat == d1_bin:
            d1_dates.append(dt)

    if len(d1_dates) < 50:
        continue

    print(f"\n  ── {d1_bin} (N={len(d1_dates)}) ──")
    d3_groups = defaultdict(list)
    for dt in d1_dates:
        if dt not in skew_d3.index: continue
        d3_val = float(skew_d3.loc[dt]) if not pd.isna(skew_d3.loc[dt]) else 1.0
        d3_cat = sk_adapter._classify_d3(d3_val)
        d3_groups[d3_cat].append(dt)

    for d3_bin, dates in sorted(d3_groups.items(), key=lambda x: -len(x[1])):
        n = len(dates)
        if n < 10:
            continue
        f60_rets = np.array([fwd_return_at(spy_s, d, 60) for d in dates])
        f60_rets = f60_rets[~np.isnan(f60_rets)]
        if len(f60_rets) < 5:
            continue
        mean_v, lo, hi = boot_ci_mean(f60_rets)
        wr, _, _ = boot_ci_wr(f60_rets)
        n_w = int((f60_rets > 0).sum())
        n_l = int((f60_rets <= 0).sum())
        print(f"    {d3_bin:<30s} N={n:>4d}  f60d={mean_v:+.2f}% CI95[{lo:+.2f},{hi:+.2f}]  "
              f"WR={wr*100:.0f}%  wins={n_w} losses={n_l}")

# 4e: PÁNICO TOTAL with D2/D3 refinement (confirm +6.81% and show sub-quadrants)
print(f"\n\n═══ PÁNICO TOTAL — refinamiento D2×D3 ═══")
panico_dates = [aligned_dates[i] for i in range(n_total) if q_panico.iloc[i]]
print(f"  PÁNICO TOTAL: {len(panico_dates)} días raw")

# D2 breakdown within PÁNICO
print(f"\n  ── D2 dentro de PÁNICO TOTAL ──")
d2_in_panico = defaultdict(list)
for dt in panico_dates:
    if dt not in skew_d2.index: continue
    d2_val = float(skew_d2.loc[dt]) if not pd.isna(skew_d2.loc[dt]) else 0.0
    d2_cat = sk_adapter._classify_d2(d2_val)
    d2_in_panico[d2_cat].append(dt)

for d2_bin, dates in sorted(d2_in_panico.items(), key=lambda x: -len(x[1])):
    f60_rets = np.array([fwd_return_at(spy_s, d, 60) for d in dates])
    f60_rets = f60_rets[~np.isnan(f60_rets)]
    if len(f60_rets) < 3: continue
    mean_v, lo, hi = boot_ci_mean(f60_rets)
    wr, _, _ = boot_ci_wr(f60_rets)
    n_w = int((f60_rets>0).sum()); n_l = int((f60_rets<=0).sum())
    print(f"    {d2_bin:<30s} N={len(dates):>2d} → f60d={mean_v:+.2f}% CI95[{lo:+.2f},{hi:+.2f}] "
          f"WR={wr*100:.0f}% wins={n_w} losses={n_l}")

# D3 breakdown within PÁNICO
print(f"\n  ── D3 dentro de PÁNICO TOTAL ──")
d3_in_panico = defaultdict(list)
for dt in panico_dates:
    if dt not in skew_d3.index: continue
    d3_val = float(skew_d3.loc[dt]) if not pd.isna(skew_d3.loc[dt]) else 1.0
    d3_cat = sk_adapter._classify_d3(d3_val)
    d3_in_panico[d3_cat].append(dt)

for d3_bin, dates in sorted(d3_in_panico.items(), key=lambda x: -len(x[1])):
    f60_rets = np.array([fwd_return_at(spy_s, d, 60) for d in dates])
    f60_rets = f60_rets[~np.isnan(f60_rets)]
    if len(f60_rets) < 3: continue
    mean_v, lo, hi = boot_ci_mean(f60_rets)
    wr, _, _ = boot_ci_wr(f60_rets)
    n_w = int((f60_rets>0).sum()); n_l = int((f60_rets<=0).sum())
    print(f"    {d3_bin:<30s} N={len(dates):>2d} → f60d={mean_v:+.2f}% CI95[{lo:+.2f},{hi:+.2f}] "
          f"WR={wr*100:.0f}% wins={n_w} losses={n_l}")


# ═══════════════════════════════════════════════════════════════════════════
# SAVE RESULTS JSON
# ═══════════════════════════════════════════════════════════════════════════

output = {
    "meta": {
        "script": "skew_profundo.py",
        "n_total": n_total,
        "date_range": [str(aligned_dates[0].date()), str(aligned_dates[-1].date())],
        "skew_p15": skew_p15, "skew_p85": skew_p85,
        "vix_p15": vix_p15, "vix_p85": vix_p85,
        "skew_d1_edges": sk_adapter.edges_d1,
        "skew_d1_labels": sk_adapter.labels_d1,
        "vix_d1_edges": vx_adapter.edges_d1,
        "vix_d1_labels": vx_adapter.labels_d1,
    },
    "part1_quadrant_raw": {name: part1_results[name] for name, _, _ in QUADRANTS},
    "part2_low_tail_episodes": lt_episodes,
    "part2_gfc": gfc_eps,
    "part2_discrimination": {
        "lt_vix_crisis": [{"date":e["date"],"f20":e["f20"],"f60":e["f60"],"f120":e["f120"],"f250":e["f250"],"vix":e["vix"]} for e in lt_vix_crisis],
        "lt_vix_calm": [{"date":e["date"],"f20":e["f20"],"f60":e["f60"],"f120":e["f120"],"f250":e["f250"],"vix":e["vix"]} for e in lt_vix_calm],
    },
    "part3_drawdown_episodes": [{
        "peak_date": str(ep["peak_date"].date()), "start_date": str(ep["start_date"].date()),
        "peak_val": ep["peak_val"], "start_dd": ep["start_dd"],
    } for ep in dd_episodes],
}

with open(Path(ROOT) / "scratch" / "skew_profundo_results.json", "w") as f:
    json.dump(output, f, indent=2, default=str)

print(f"\n\n{'═'*80}")
print(f"  RESULTADOS GUARDADOS en scratch/skew_profundo_results.json")
print(f"{'═'*80}")