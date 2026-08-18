#!/usr/bin/env python3
"""
RECALIBRADO FG + BSI — Escalas del Proyecto Botero Trade
=========================================================
Especialista en Fear & Greed (FG) y Breadth Shock Index (BSI).

5 ANÁLISIS:

1. MATRIZ FG: D1 ∈ {EXTREME_GREED, EUPHORIA} × D2_bin × D3_bin → SPY forward 5d/10d/20d
2. GRADIENTE FG: Recorrido D2 bins (FAST_SPIKE → STABLE → FAST_CRUSH) → SPY forward
3. MATRIZ BSI: D1 extremo de BSI × D2_bin × D3_bin → SPY forward
4. COMPARAR con VIX: ¿Simetría comprar-miedo = vender-euforia?
5. TRANSICIONES: D2 flip en FG/BSI → SPY forward

Usa FGLookupAdapter.lookup_fg_guidance() y BSILookupAdapter.lookup_bsi_guidance()
con ticker S5TW para BSI. Datos: market.ohlcv_bars + market.zigzag_legs.

Dato mata relato — todo viene de la base de datos.
"""
import sys
import json
from pathlib import Path
from datetime import timedelta
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ttest_1samp, ttest_ind, bootstrap

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
from backend.modules.entry_decision.domain.rules.fg_lookup import FGLookupAdapter
from backend.modules.entry_decision.domain.rules.bsi_lookup import BSILookupAdapter
from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter

# ── Helpers ────────────────────────────────────────────────────────────────

def ic(a, b):
    """Spearman IC between two series."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = ~np.isnan(a) & ~np.isnan(b)
    if m.sum() < 5 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
        return np.nan, np.nan, int(m.sum())
    r, p = spearmanr(a[m], b[m])
    return float(r), float(p), int(m.sum())

def boot_ci(arr, ci=95, n_boot=2000, random_state=42):
    """Bootstrap CI for mean of array."""
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 5:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(random_state)
    means = []
    for _ in range(n_boot):
        sample = rng.choice(arr, size=len(arr), replace=True)
        means.append(sample.mean())
    means = np.sort(means)
    lo = (100 - ci) / 2
    hi = 100 - lo
    return arr.mean(), np.percentile(means, lo), np.percentile(means, hi)

def fmt_pct(x, decimals=1):
    """Format as percentage string."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "  n/a"
    return f"{x*100:+.{decimals}f}%"

def fmt_ci(mean, lo, hi):
    if any(np.isnan(v) for v in [mean, lo, hi]):
        return "n/a"
    return f"mean={mean*100:+.2f}%  CI95=[{lo*100:+.2f}%, {hi*100:+.2f}%]"

# ── Load Data ──────────────────────────────────────────────────────────────

store = TimescaleDataStore()
repo = ZigzagLegRepository(store)

print("══════════════════════════════════════════════════════════════════")
print("  CARGANDO DATOS — market.ohlcv_bars + market.zigzag_legs")
print("══════════════════════════════════════════════════════════════════")

# OHLCV bars
spy_raw = store.load_bars("SPY", "1d")["close"].copy()
fg_raw  = store.load_bars("FG",  "1d")["close"].copy()
bsi_raw = store.load_bars("S5TW", "1d")["close"].copy()
vix_raw = store.load_bars("VIX", "1d")["close"].copy()

def _naive_idx(s):
    s = s.copy()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()

spy = _naive_idx(spy_raw)
fg  = _naive_idx(fg_raw)
bsi = _naive_idx(bsi_raw)
vix = _naive_idx(vix_raw)

print(f"  SPY: {spy.index[0].date()} → {spy.index[-1].date()} ({len(spy)} bars)")
print(f"  FG:  {fg.index[0].date()}  → {fg.index[-1].date()}  ({len(fg)} bars)")
print(f"  BSI: {bsi.index[0].date()} → {bsi.index[-1].date()} ({len(bsi)} bars)")
print(f"  VIX: {vix.index[0].date()} → {vix.index[-1].date()} ({len(vix)} bars)")

# Zigzag legs
legs25 = sorted(repo.get_confirmed_legs("SPY", "zz25"), key=lambda l: l.start_timestamp)
legs50 = repo.get_confirmed_legs("SPY", "zz50")
legs75 = repo.get_confirmed_legs("SPY", "zz75")

starts50 = {pd.to_datetime(l.start_timestamp).date() for l in legs50}
starts75 = {pd.to_datetime(l.start_timestamp).date() for l in legs75}

# Pivot dataframe
df_pivots = pd.DataFrame([
    {"start_timestamp": pd.to_datetime(l.start_timestamp),
     "start_type": l.start_type,
     "prev_leg_return": l.prev_leg_return}
    for l in legs25
])
df_pivots["pivot_date"] = df_pivots["start_timestamp"].dt.date
df_pivots["leg_bear"] = (df_pivots["start_type"] == "MAX").astype(int)
df_pivots["cascade_50"] = df_pivots["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts50 for i in range(-3, 4))))
df_pivots["cascade_75"] = df_pivots["pivot_date"].apply(
    lambda d: int(any(d + timedelta(days=i) in starts75 for i in range(-3, 4))))
df_pivots = df_pivots.dropna(subset=["prev_leg_return"]).reset_index(drop=True)

print(f"  zigzag_legs zz25: {len(df_pivots)} pivots")

# Build daily feature table
common_dates = sorted(set(fg.index) & set(bsi.index) & set(vix.index) & set(spy.index))
print(f"  Common dates (FG ∩ BSI ∩ VIX ∩ SPY): {len(common_dates)}")

# Compute D2 (Δ3d) and D3 (vol_norm) for each indicator
def compute_d2_d3(s):
    """D2 = diff(3), D3 = std(2d)/std(10d)."""
    d2 = s.diff(3)
    s2, s10 = s.rolling(2).std(), s.rolling(10).std()
    d3 = (s2 / s10).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    return d2, d3

fg_d2, fg_d3   = compute_d2_d3(fg)
bsi_d2, bsi_d3 = compute_d2_d3(bsi)
vix_d2, vix_d3 = compute_d2_d3(vix)

# SPY forward returns
spy_ret_5d  = spy.pct_change(5).shift(-5)
spy_ret_10d = spy.pct_change(10).shift(-10)
spy_ret_20d = spy.pct_change(20).shift(-20)

# ── Classify every day through project adapters ──────────────────────────────

print("\n═══ CLASIFICANDO DÍAS con FGLookupAdapter y BSILookupAdapter ═══")

fg_adapter  = FGLookupAdapter()
bsi_adapter = BSILookupAdapter()
vix_adapter = VIXLookupAdapter()

print(f"  FG  edges D1: {[round(e,1) for e in fg_adapter.edges_d1]}")
print(f"  FG  labels D1: {fg_adapter.labels_d1}")
print(f"  FG  labels D2: {fg_adapter.labels_d2}")
print(f"  FG  labels D3: {fg_adapter.labels_d3}")
print(f"  BSI edges D1: {[round(e,1) for e in bsi_adapter.edges_d1]}")
print(f"  BSI labels D1: {bsi_adapter.labels_d1}")
print(f"  BSI labels D2: {bsi_adapter.labels_d2}")
print(f"  VIX labels D1: {vix_adapter.labels_d1}")

records = []
for dt in common_dates:
    if (dt not in fg.index or dt not in fg_d2.index or dt not in fg_d3.index or
        dt not in bsi.index or dt not in bsi_d2.index or dt not in bsi_d3.index or
        dt not in vix.index or dt not in vix_d2.index or dt not in vix_d3.index or
        dt not in spy.index):
        continue

    fg_val  = float(fg[dt])
    fg_vel  = float(fg_d2[dt]) if not pd.isna(fg_d2[dt]) else 0.0
    fg_vol  = float(fg_d3[dt]) if not pd.isna(fg_d3[dt]) else 1.0

    bsi_val = float(bsi[dt])
    bsi_vel = float(bsi_d2[dt]) if not pd.isna(bsi_d2[dt]) else 0.0
    bsi_vol = float(bsi_d3[dt]) if not pd.isna(bsi_d3[dt]) else 1.0

    vix_val = float(vix[dt])
    vix_vel = float(vix_d2[dt]) if not pd.isna(vix_d2[dt]) else 0.0
    vix_vol = float(vix_d3[dt]) if not pd.isna(vix_d3[dt]) else 1.0

    # SPY forward returns
    spy5  = float(spy_ret_5d[dt])  if dt in spy_ret_5d.index  and not pd.isna(spy_ret_5d[dt])  else np.nan
    spy10 = float(spy_ret_10d[dt]) if dt in spy_ret_10d.index and not pd.isna(spy_ret_10d[dt]) else np.nan
    spy20 = float(spy_ret_20d[dt]) if dt in spy_ret_20d.index and not pd.isna(spy_ret_20d[dt]) else np.nan
    spy_price = float(spy[dt])

    # Classify through project adapters
    try:
        fg_g = fg_adapter.lookup_fg_guidance(val=fg_val, d3_speed=fg_vel, vol_norm=fg_vol, vol_d3=0.0)
    except Exception:
        fg_g = None
    try:
        bsi_g = bsi_adapter.lookup_bsi_guidance(val=bsi_val, d3_speed=bsi_vel, vol_norm=bsi_vol, vol_d3=0.0)
    except Exception:
        bsi_g = None
    try:
        vix_g = vix_adapter.lookup_vix_guidance(val=vix_val, d3_speed=vix_vel, vol_norm=vix_vol, vol_d3=0.0)
    except Exception:
        vix_g = None

    rec = {
        "date": dt,
        "spy_close": spy_price,
        "spy_fwd5": spy5, "spy_fwd10": spy10, "spy_fwd20": spy20,
        "fg_val": fg_val, "fg_vel": fg_vel, "fg_vol": fg_vol,
        "fg_d1": fg_g.fg_bin if fg_g else "UNCLASSIFIED",
        "fg_d2": fg_g.velocity_vector if fg_g else "UNCLASSIFIED",
        "fg_d3": fg_g.pivot_vector if fg_g else "UNCLASSIFIED",
        "fg_state_key": fg_g.state_key if fg_g else "",
        "fg_n": fg_g.n if fg_g else 0,
        "fg_zz50_p_bull": fg_g.zz50.p_bull if fg_g else np.nan,
        "fg_zz50_ev_net": fg_g.zz50.ev_net if fg_g else np.nan,
        "bsi_val": bsi_val, "bsi_vel": bsi_vel, "bsi_vol": bsi_vol,
        "bsi_d1": bsi_g.bsi_bin if bsi_g else "UNCLASSIFIED",
        "bsi_d2": bsi_g.velocity_vector if bsi_g else "UNCLASSIFIED",
        "bsi_d3": bsi_g.pivot_vector if bsi_g else "UNCLASSIFIED",
        "bsi_state_key": bsi_g.state_key if bsi_g else "",
        "bsi_n": bsi_g.n if bsi_g else 0,
        "bsi_zz50_p_bull": bsi_g.zz50.p_bull if bsi_g else np.nan,
        "bsi_zz50_ev_net": bsi_g.zz50.ev_net if bsi_g else np.nan,
        "vix_val": vix_val, "vix_vel": vix_vel, "vix_vol": vix_vol,
        "vix_d1": vix_g.vix_bin if vix_g else "UNCLASSIFIED",
        "vix_d2": vix_g.velocity_vector if vix_g else "UNCLASSIFIED",
        "vix_d3": vix_g.pivot_vector if vix_g else "UNCLASSIFIED",
    }
    records.append(rec)

df = pd.DataFrame(records)
print(f"  Días clasificados: {len(df)}")

store.close()

# ── FG D2 bins in order (gradient) ─────────────────────────────────────────
FG_D2_ORDER = [
    "FAST_SPIKE_3D",
    "ACCELERATING_UP_3D",
    "STABLE_CONTINUATION_3D",
    "DECELERATING_DOWN_3D",
    "FAST_CRUSH_3D",
]

FG_D1_EXTREME_GREED = ["EXTREME_GREED", "EUPHORIA"]
BSI_D1_EXTREME = ["BREADTH_WASHED_OUT", "HYPER_EXPANSIVE_BREADTH"]

# ═════════════════════════════════════════════════════════════════════════════
# 1. MATRIZ FG — D1 ∈ {EXTREME_GREED, EUPHORIA} × D2_bin × D3_bin → SPY fwd
# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 90)
print("  1. MATRIZ FG — D1 ∈ {EXTREME_GREED, EUPHORIA} × D2 × D3 → SPY forward")
print("═" * 90)

mask_fg_extreme = df["fg_d1"].isin(FG_D1_EXTREME_GREED)
n_total = mask_fg_extreme.sum()
print(f"  Días en D1 EXTREME_GREED/EUPHORIA: {n_total} / {len(df)} ({n_total/len(df)*100:.1f}%)")
print(f"  SPY fwd 5d global (todos los días):  mean={df['spy_fwd5'].mean()*100:+.2f}%  median={df['spy_fwd5'].median()*100:+.2f}%")

for horizon, col in [("5d", "spy_fwd5"), ("10d", "spy_fwd10"), ("20d", "spy_fwd20")]:
    print(f"\n  ── MATRIZ FG D2×D3 → SPY forward {horizon} ──")
    sub = df[mask_fg_extreme].dropna(subset=[col])
    if len(sub) == 0:
        print("    (sin datos)")
        continue

    # Header
    d3_bins_all = sorted(sub["fg_d3"].unique())
    print(f"    {'D2 ↓ / D3 →':<28}", end="")
    for d3b in d3_bins_all:
        print(f"{d3b:<30}", end="")
    print()
    print("    " + "-" * (28 + 30 * len(d3_bins_all)))

    for d2b in FG_D2_ORDER:
        print(f"    {d2b:<28}", end="")
        for d3b in d3_bins_all:
            cell = sub[(sub["fg_d2"] == d2b) & (sub["fg_d3"] == d3b)]
            n_cell = len(cell)
            if n_cell < 3:
                print(f"{'-- (N<3)':<30}", end="")
            else:
                m = cell[col].mean()
                pos = (cell[col] > 0).mean()
                print(f"{m*100:+6.2f}% ({pos*100:3.0f}%↑) N={n_cell:<6}", end="")
        print()

    # Row subtotals by D2
    print(f"\n    Subtotales por D2 (SPY fwd {horizon}):")
    for d2b in FG_D2_ORDER:
        cell = sub[sub["fg_d2"] == d2b]
        if len(cell) < 3:
            continue
        m = cell[col].mean()
        pos = (cell[col] > 0).mean()
        med = cell[col].median()
        m_boot, lo, hi = boot_ci(cell[col].values)
        print(f"      {d2b:<28} N={len(cell):<5}  mean={m*100:+.2f}%  median={med*100:+.2f}%  " +
              f"pos={(pos*100):.0f}%  CI95=[{lo*100:+.2f}%, {hi*100:+.2f}%]")

# ═════════════════════════════════════════════════════════════════════════════
# 2. GRADIENTE FG — Recorrido D2 bins → SPY forward
# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 90)
print("  2. GRADIENTE FG — Recorrido por D2 bins completo → SPY forward")
print("═" * 90)

for horizon, col in [("5d", "spy_fwd5"), ("10d", "spy_fwd10"), ("20d", "spy_fwd20")]:
    print(f"\n  ── GRADIENTE D2 → SPY forward {horizon} ──")
    valid = df.dropna(subset=[col])
    print(f"    {'D2 bin':<28} {'N':>5} {'mean':>9} {'median':>8} {'%pos':>6} {'p-vs-global':>10}")

    global_mean = valid[col].mean()
    for d2b in FG_D2_ORDER:
        cell = valid[valid["fg_d2"] == d2b]
        if len(cell) < 5:
            continue
        m = cell[col].mean()
        med = cell[col].median()
        pos = (cell[col] > 0).mean()

        # t-test vs global mean
        t_stat, p_val = ttest_1samp(cell[col].dropna(), global_mean)
        print(f"    {d2b:<28} {len(cell):>5} {m*100:>+8.2f}% {med*100:>+7.2f}% {pos*100:>5.0f}% p={p_val:.4f}")

    print(f"    {'GLOBAL (todos D2)':<28} {len(valid):>5} {global_mean*100:>+8.2f}%")

# ═════════════════════════════════════════════════════════════════════════════
# 3. MATRIZ BSI — D1 extremo × D2_bin × D3_bin → SPY forward
# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 90)
print("  3. MATRIZ BSI — D1 extremo × D2 × D3 → SPY forward")
print("═" * 90)

mask_bsi_extreme = df["bsi_d1"].isin(BSI_D1_EXTREME)
n_bsi = mask_bsi_extreme.sum()
print(f"  Días en D1 extremo BSI (WASHED_OUT / HYPER_EXPANSIVE): {n_bsi} / {len(df)} ({n_bsi/len(df)*100:.1f}%)")

# Split by which extreme
for extreme_label in BSI_D1_EXTREME:
    mask_one = df["bsi_d1"] == extreme_label
    n_one = mask_one.sum()
    print(f"    - {extreme_label}: {n_one} días")

for horizon, col in [("5d", "spy_fwd5"), ("10d", "spy_fwd10"), ("20d", "spy_fwd20")]:
    print(f"\n  ── MATRIZ BSI D2×D3 → SPY forward {horizon} ──")
    sub = df[mask_bsi_extreme].dropna(subset=[col])
    if len(sub) == 0:
        print("    (sin datos)")
        continue

    d3_bins_all = sorted(sub["bsi_d3"].unique())
    print(f"    {'D2 ↓ / D3 →':<28}", end="")
    for d3b in d3_bins_all:
        print(f"{d3b:<30}", end="")
    print()
    print("    " + "-" * (28 + 30 * len(d3_bins_all)))

    for d2b in FG_D2_ORDER:
        print(f"    {d2b:<28}", end="")
        for d3b in d3_bins_all:
            cell = sub[(sub["bsi_d2"] == d2b) & (sub["bsi_d3"] == d3b)]
            n_cell = len(cell)
            if n_cell < 3:
                print(f"{'-- (N<3)':<30}", end="")
            else:
                m = cell[col].mean()
                pos = (cell[col] > 0).mean()
                print(f"{m*100:+6.2f}% ({pos*100:3.0f}%↑) N={n_cell:<6}", end="")
        print()

    # Per D2 subtotals
    print(f"\n    Subtotales por D2 (SPY fwd {horizon}):")
    for d2b in FG_D2_ORDER:
        cell = sub[sub["bsi_d2"] == d2b]
        if len(cell) < 3:
            continue
        m = cell[col].mean()
        pos = (cell[col] > 0).mean()
        m_boot, lo, hi = boot_ci(cell[col].values)
        print(f"      {d2b:<28} N={len(cell):<5}  mean={m*100:+.2f}%  pos={(pos*100):.0f}%  " +
              f"CI95=[{lo*100:+.2f}%, {hi*100:+.2f}%]")

# ═════════════════════════════════════════════════════════════════════════════
# 4. COMPARAR con VIX — ¿Simetría comprar-miedo = vender-euforia?
# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 90)
print("  4. COMPARACIÓN VIX vs FG/BSI — ¿Simetría miedo ↔ euforia?")
print("═" * 90)

# Define extreme fear (VIX) and extreme greed (FG)
# VIX extreme = CRISIS_SPIKE, ELEVATED_PANIC (from convergence_compositor)
VIX_D1_FEAR    = ["CRISIS_SPIKE", "ELEVATED_PANIC"]
VIX_D1_GREED   = ["DEEP_COMPLACENCY", "LOW_VOL"]

mask_vix_fear  = df["vix_d1"].isin(VIX_D1_FEAR)
mask_vix_greed = df["vix_d1"].isin(VIX_D1_GREED)
mask_fg_greed  = df["fg_d1"].isin(FG_D1_EXTREME_GREED)
mask_fg_fear   = df["fg_d1"].isin(["EXTREME_FEAR", "FEAR"])
mask_bsi_wash  = df["bsi_d1"] == "BREADTH_WASHED_OUT"
mask_bsi_hyper = df["bsi_d1"] == "HYPER_EXPANSIVE_BREADTH"

print(f"\n  Estados extremos (N días):")
print(f"    VIX MIEDO:     {mask_vix_fear.sum():>5}  ({VIX_D1_FEAR[0]}, {VIX_D1_FEAR[1]})")
print(f"    VIX COMPLACENCIA: {mask_vix_greed.sum():>5}  ({VIX_D1_GREED[0]}, {VIX_D1_GREED[1]})")
print(f"    FG MIEDO:      {mask_fg_fear.sum():>5}  (EXTREME_FEAR, FEAR)")
print(f"    FG EUFORIA:    {mask_fg_greed.sum():>5}  (EXTREME_GREED, EUPHORIA)")
print(f"    BSI WASHED_OUT:{mask_bsi_wash.sum():>5}  (capitulación breadth)")
print(f"    BSI HYPER_EXP: {mask_bsi_hyper.sum():>5}  (euforia breadth)")

# Forward returns comparison
print(f"\n  ── SPY forward returns desde cada estado extremo ──")
for horizon, col in [("5d", "spy_fwd5"), ("10d", "spy_fwd10"), ("20d", "spy_fwd20")]:
    print(f"\n    Horizonte {horizon}:")
    print(f"    {'Estado':<22} {'N':>5} {'mean':>8} {'median':>8} {'%pos':>6} {'CI95':>28} {'sign':>6}")

    for label, mask in [
        ("VIX MIEDO (crisis)", mask_vix_fear),
        ("FG MIEDO (extreme_fear)", mask_fg_fear),
        ("BSI WASHED_OUT", mask_bsi_wash),
        ("─── (línea media) ───", slice(None)),
        ("VIX COMPLACENCY", mask_vix_greed),
        ("FG EUFORIA", mask_fg_greed),
        ("BSI HYPER_EXP", mask_bsi_hyper),
    ]:
        # "línea media" is all data
        if isinstance(mask, slice):
            cell = df.dropna(subset=[col])
        else:
            cell = df[mask].dropna(subset=[col])

        if len(cell) < 3:
            print(f"    {label:<22} {len(cell):>5} {'--':>8}")
            continue
        m = cell[col].mean()
        med = cell[col].median()
        pos = (cell[col] > 0).mean()
        m_boot, lo, hi = boot_ci(cell[col].values)

        # Test sign: is mean significantly different from 0?
        _, p_sign = ttest_1samp(cell[col].dropna(), 0.0)
        sign_str = "✓" if p_sign < 0.05 else "ns"

        print(f"    {label:<22} {len(cell):>5} {m*100:>+7.2f}% {med*100:>+7.2f}% " +
              f"{pos*100:>5.0f}% [{lo*100:+.2f}%,{hi*100:+.2f}%] p={p_sign:.3f}")

# Symmetry test: compare VIX fear vs FG greed
print(f"\n  ── PRUEBA DE SIMETRÍA: ¿comprar miedo ≡ vender euforia? ──")
for horizon, col in [("5d", "spy_fwd5"), ("10d", "spy_fwd10"), ("20d", "spy_fwd20")]:
    fear_arr = df.loc[mask_vix_fear, col].dropna().values
    greed_arr = df.loc[mask_fg_greed, col].dropna().values

    if len(fear_arr) < 5 or len(greed_arr) < 5:
        print(f"    {horizon}: sin suficientes datos (N_fear={len(fear_arr)}, N_greed={len(greed_arr)})")
        continue

    # Test if means are equal
    t_eq, p_eq = ttest_ind(fear_arr, greed_arr, equal_var=False)

    # Test symmetry: H0: fear_mean = -greed_mean (miedo y euforia son espejos)
    # Compare fear_arr vs -greed_arr
    greed_neg = -greed_arr  # flip sign for symmetry test
    t_sym, p_sym = ttest_ind(fear_arr, greed_neg, equal_var=False)

    # Bootstrap test for difference of means
    rng = np.random.default_rng(42)
    diffs = []
    for _ in range(2000):
        f_sample = rng.choice(fear_arr, size=len(fear_arr), replace=True)
        g_sample = rng.choice(greed_arr, size=len(greed_arr), replace=True)
        diffs.append(f_sample.mean() + g_sample.mean())  # fear_mean + greed_mean ≈ 0 for symmetry
    diffs = np.sort(diffs)
    p_sym_boot = (diffs < 0).mean() if np.mean(diffs) > 0 else (diffs > 0).mean()

    print(f"    {horizon}: VIX_miedo={fear_arr.mean()*100:+.2f}% (N={len(fear_arr)}) " +
          f"vs FG_euforia={greed_arr.mean()*100:+.2f}% (N={len(greed_arr)})")
    print(f"      ¿medias iguales? p={p_eq:.4f} (t={t_eq:.3f})")
    print(f"      ¿simetría (miedo=−euforia)? t-test p={p_sym:.4f}  bootstrap p={p_sym_boot:.4f}")
    print(f"      gap |miedo|−|euforia| = {abs(fear_arr.mean())-abs(greed_arr.mean()):+.4f}")

# BSI symmetry
print(f"\n  ── SIMETRÍA BSI: WASHED_OUT vs HYPER_EXPANSIVE ──")
for horizon, col in [("5d", "spy_fwd5"), ("10d", "spy_fwd10"), ("20d", "spy_fwd20")]:
    wash_arr = df.loc[mask_bsi_wash, col].dropna().values
    hyper_arr = df.loc[mask_bsi_hyper, col].dropna().values

    if len(wash_arr) < 5 or len(hyper_arr) < 5:
        print(f"    {horizon}: sin suficientes datos")
        continue

    t_eq, p_eq = ttest_ind(wash_arr, hyper_arr, equal_var=False)
    hyper_neg = -hyper_arr
    t_sym, p_sym = ttest_ind(wash_arr, hyper_neg, equal_var=False)

    # Bootstrap
    rng = np.random.default_rng(42)
    diffs = []
    for _ in range(2000):
        w_sample = rng.choice(wash_arr, size=len(wash_arr), replace=True)
        h_sample = rng.choice(hyper_arr, size=len(hyper_arr), replace=True)
        diffs.append(w_sample.mean() + h_sample.mean())
    diffs = np.sort(diffs)
    p_sym_boot = (diffs < 0).mean() if np.mean(diffs) > 0 else (diffs > 0).mean()

    print(f"    {horizon}: BSI_WASH={wash_arr.mean()*100:+.2f}% (N={len(wash_arr)}) " +
          f"vs BSI_HYPER={hyper_arr.mean()*100:+.2f}% (N={len(hyper_arr)})")
    print(f"      ¿simetría? t-test p={p_sym:.4f}  bootstrap p={p_sym_boot:.4f}")

# ═════════════════════════════════════════════════════════════════════════════
# 5. TRANSICIONES — D2 flip en FG/BSI → SPY forward
# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 90)
print("  5. TRANSICIONES — D2 flip (cambio de signo Δ3d) → SPY forward")
print("═" * 90)

# D2 flip detection: sign(D2_t) != sign(D2_{t-3})  (comparing to 3d ago, same window)
df_sorted = df.sort_values("date").reset_index(drop=True)
df_sorted["fg_d2_prev"] = df_sorted["fg_vel"].shift(3)
df_sorted["bsi_d2_prev"] = df_sorted["bsi_vel"].shift(3)
df_sorted["vix_d2_prev"] = df_sorted["vix_vel"].shift(3)

df_sorted["fg_flip"] = (np.sign(df_sorted["fg_vel"]) != np.sign(df_sorted["fg_d2_prev"]))
df_sorted["bsi_flip"] = (np.sign(df_sorted["bsi_vel"]) != np.sign(df_sorted["bsi_d2_prev"]))
df_sorted["vix_flip"] = (np.sign(df_sorted["vix_vel"]) != np.sign(df_sorted["vix_d2_prev"]))

# Direction of flip
df_sorted["fg_flip_up"]   = df_sorted["fg_flip"] & (df_sorted["fg_vel"] > 0)
df_sorted["fg_flip_down"] = df_sorted["fg_flip"] & (df_sorted["fg_vel"] < 0)
df_sorted["bsi_flip_up"]   = df_sorted["bsi_flip"] & (df_sorted["bsi_vel"] > 0)
df_sorted["bsi_flip_down"] = df_sorted["bsi_flip"] & (df_sorted["bsi_vel"] < 0)
df_sorted["vix_flip_up"]   = df_sorted["vix_flip"] & (df_sorted["vix_vel"] > 0)
df_sorted["vix_flip_down"] = df_sorted["vix_flip"] & (df_sorted["vix_vel"] < 0)

# Conditional flips: extreme D1 + flip
fg_extreme_flip_down = df_sorted["fg_d1"].isin(FG_D1_EXTREME_GREED) & df_sorted["fg_flip_down"]
fg_extreme_flip_up   = df_sorted["fg_d1"].isin(FG_D1_EXTREME_GREED) & df_sorted["fg_flip_up"]
fg_fear_flip_down    = df_sorted["fg_d1"].isin(["EXTREME_FEAR", "FEAR"]) & df_sorted["fg_flip_down"]
fg_fear_flip_up      = df_sorted["fg_d1"].isin(["EXTREME_FEAR", "FEAR"]) & df_sorted["fg_flip_up"]

bsi_extreme_flip_down = df_sorted["bsi_d1"].isin(BSI_D1_EXTREME) & df_sorted["bsi_flip_down"]
bsi_extreme_flip_up   = df_sorted["bsi_d1"].isin(BSI_D1_EXTREME) & df_sorted["bsi_flip_up"]

vix_crisis_flip_down = mask_vix_fear & df_sorted["vix_flip_down"]
vix_crisis_flip_up   = mask_vix_fear & df_sorted["vix_flip_up"]

print(f"\n  Días con flip D2 (total):")
print(f"    FG:  {df_sorted['fg_flip'].sum():>5}")
print(f"    BSI: {df_sorted['bsi_flip'].sum():>5}")
print(f"    VIX: {df_sorted['vix_flip'].sum():>5}")

# Full flip table (all D1 levels)
print(f"\n  ── SPY forward desde flip D2 (todos los D1) ──")
for indicator, flip_col in [("FG", "fg_flip"), ("BSI", "bsi_flip"), ("VIX", "vix_flip")]:
    print(f"\n    {indicator}:")
    for horizon, col in [("5d", "spy_fwd5"), ("10d", "spy_fwd10"), ("20d", "spy_fwd20")]:
        valid = df_sorted.dropna(subset=[col])

        no_flip = valid[~valid[flip_col]]
        yes_flip = valid[valid[flip_col]]
        flip_up = valid[valid[f"{indicator.lower()}_flip_up"]]
        flip_down = valid[valid[f"{indicator.lower()}_flip_down"]]

        for label, sub in [("no flip", no_flip), ("flip", yes_flip),
                            ("flip ↑", flip_up), ("flip ↓", flip_down)]:
            if len(sub) < 5:
                continue
            m = sub[col].mean()
            pos = (sub[col] > 0).mean()
            _, p_sig = ttest_1samp(sub[col].dropna(), 0.0)
            print(f"      {label:<10} {horizon}: N={len(sub):<5} mean={m*100:+6.2f}% " +
                  f"pos={pos*100:.0f}% p(≠0)={p_sig:.4f}")

# Conditional flips: extreme + flip (the key trading signal)
print(f"\n  ── TRANSICIONES CONDICIONALES: D1 extremo + D2 flip → SPY forward ──")
transitions = [
    ("FG EUFORIA + flip ↓ (agotamiento)", fg_extreme_flip_down),
    ("FG EUFORIA + flip ↑ (acelerando)",  fg_extreme_flip_up),
    ("FG MIEDO + flip ↓ (miedo pasado)",  fg_fear_flip_down),
    ("FG MIEDO + flip ↑ (miedo crece)",   fg_fear_flip_up),
    ("BSI extremo + flip ↓",              bsi_extreme_flip_down),
    ("BSI extremo + flip ↑",              bsi_extreme_flip_up),
    ("VIX CRISIS + flip ↓ (pánico resuelto)", vix_crisis_flip_down),
    ("VIX CRISIS + flip ↑ (pánico acelera)",  vix_crisis_flip_up),
]

for horizon, col in [("5d", "spy_fwd5"), ("10d", "spy_fwd10"), ("20d", "spy_fwd20")]:
    print(f"\n    Horizonte {horizon}:")
    print(f"    {'Transición':<42} {'N':>5} {'mean':>8} {'median':>8} {'%pos':>6} {'CI95':>28}")

    for label, mask_t in transitions:
        sub = df_sorted.loc[mask_t, col].dropna()
        if len(sub) < 3:
            print(f"    {label:<42} {len(sub):>5} {'-- (N<3)':>8}")
            continue
        m = sub.mean()
        med = sub.median()
        pos = (sub > 0).mean()
        m_boot, lo, hi = boot_ci(sub.values)
        print(f"    {label:<42} {len(sub):>5} {m*100:>+7.2f}% {med*100:>+7.2f}% " +
              f"{pos*100:>5.0f}% [{lo*100:+.2f}%, {hi*100:+.2f}%]")

# ═════════════════════════════════════════════════════════════════════════════
# SUMMARY TABLE — FG extreme D1 × D2 gradient (key finding)
# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 90)
print("  RESUMEN — FG D1 EXTREME_GREED/EUPHORIA × D2 gradiente")
print("═" * 90)
sub_fg_ext = df[mask_fg_extreme]
print(f"  N total: {len(sub_fg_ext)}")
print(f"\n  {'D2 bin':<28} {'N':>5} {'SPY 5d':>9} {'SPY 10d':>9} {'SPY 20d':>9} {'%pos_20d':>9}")
for d2b in FG_D2_ORDER:
    cell = sub_fg_ext[sub_fg_ext["fg_d2"] == d2b]
    if len(cell) < 3:
        continue
    m5 = cell["spy_fwd5"].mean()
    m10 = cell["spy_fwd10"].mean()
    m20 = cell["spy_fwd20"].mean()
    p20 = (cell["spy_fwd20"] > 0).mean() if len(cell.dropna(subset=["spy_fwd20"])) > 0 else np.nan
    print(f"  {d2b:<28} {len(cell):>5} {m5*100:>+8.2f}% {m10*100:>+8.2f}% {m20*100:>+8.2f}% {p20*100:>8.0f}%")

print(f"\n  ── RESUMEN BSI extremo × D2 gradiente ──")
sub_bsi_ext = df[mask_bsi_extreme]
print(f"  N total: {len(sub_bsi_ext)}")
print(f"\n  {'D2 bin':<28} {'N':>5} {'SPY 5d':>9} {'SPY 10d':>9} {'SPY 20d':>9} {'%pos_20d':>9}")
for d2b in FG_D2_ORDER:
    cell = sub_bsi_ext[sub_bsi_ext["bsi_d2"] == d2b]
    if len(cell) < 3:
        continue
    m5 = cell["spy_fwd5"].mean()
    m10 = cell["spy_fwd10"].mean()
    m20 = cell["spy_fwd20"].mean()
    p20 = (cell["spy_fwd20"] > 0).mean() if len(cell.dropna(subset=["spy_fwd20"])) > 0 else np.nan
    print(f"  {d2b:<28} {len(cell):>5} {m5*100:>+8.2f}% {m10*100:>+8.2f}% {m20*100:>+8.2f}% {p20*100:>8.0f}%")

print("\n══════════════════════════════════════════════════════════════════")
print("  RECALIBRACIÓN FG + BSI — COMPLETADA")
print("══════════════════════════════════════════════════════════════════")