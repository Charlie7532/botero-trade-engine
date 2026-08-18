#!/usr/bin/env python3
"""SKEW PROFUNDO — suplemento: base rate drawdown, curva SKEW→fwd, post-2011."""
import sys, json
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter
from backend.modules.entry_decision.domain.rules.vix_lookup import VIXLookupAdapter

def boot_ci_mean(arr, n_boot=2000, seed=42):
    arr = np.asarray(arr, float); arr = arr[~np.isnan(arr)]
    if len(arr) < 3: return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    m = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1); m.sort()
    return float(arr.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))

def boot_ci_wr(arr, n_boot=2000, seed=42):
    arr = np.asarray(arr, float); arr = arr[~np.isnan(arr)]
    if len(arr) < 3: return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    p = (rng.choice(arr, size=(n_boot, len(arr)), replace=True) > 0).mean(axis=1); p.sort()
    return float((arr > 0).mean()), float(np.percentile(p, 2.5)), float(np.percentile(p, 97.5))

store = TimescaleDataStore()
spy_raw = store.load_bars("SPY", "1d")["close"].copy(); spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy = spy_raw[~spy_raw.index.duplicated(keep="last")].sort_index()
skew_raw = store.load_bars("SKEW", "1d")["close"].copy(); skew_raw.index = pd.to_datetime(skew_raw.index).normalize()
skew = skew_raw[~skew_raw.index.duplicated(keep="last")].sort_index()
vix_raw = store.load_bars("VIX", "1d")["close"].copy(); vix_raw.index = pd.to_datetime(vix_raw.index).normalize()
vix = vix_raw[~vix_raw.index.duplicated(keep="last")].sort_index()
store.close()

common = sorted(set(spy.index) & set(skew.index) & set(vix.index))
spy_s = spy.loc[common]; skew_s = skew.loc[common]; vix_s = vix.loc[common]
dates = list(spy_s.index); n = len(dates)
ad = SkewLookupAdapter(); va = VIXLookupAdapter()

def fwd(spy_s, dt, h):
    i = spy_s.index.get_loc(dt)
    if i + h >= len(spy_s): return np.nan
    return float((spy_s.iloc[i+h] / spy_s.iloc[i] - 1) * 100)

def maxdd_after(spy_s, dt, h):
    i = spy_s.index.get_loc(dt)
    peak = spy_s.iloc[i]; mdd = 0.0
    for j in range(i+1, min(len(spy_s), i+h+1)):
        v = spy_s.iloc[j]
        if v > peak: peak = v
        mdd = min(mdd, float((v/peak-1)*100))
    return mdd

# ── 1. BASE RATE: P(>10% DD within 60/120 td) from random de-clustered days ──
print("═══ BASE RATE: drawdown >10% desde un día cualquiera ═══")
# de-cluster all days by 60 td for independence
rng = np.random.default_rng(7)
sample_dates = [dates[i] for i in range(0, n, 60)]  # every 60 td = independent-ish
for h in [60, 120]:
    n_f = 0
    for dt in sample_dates:
        if maxdd_after(spy_s, dt, h) < -10:
            n_f += 1
    print(f"  >10% DD en {h}td: {n_f}/{len(sample_dates)} = {n_f/len(sample_dates)*100:.1f}%  (N={len(sample_dates)} días de-clustered 60td)")

# ── 2. CURVA SKEW→forward 60d (clean, all D2/D3 combined) ──
print("\n═══ CURVA SKEW D1 → FORWARD 60d (no D2 split) ═══")
for d1 in ad.labels_d1:
    ds = []
    for i, dt in enumerate(dates):
        if dt not in skew_s.index: continue
        if ad._classify_d1(float(skew_s.loc[dt])) == d1:
            ds.append(dt)
    rets = np.array([fwd(spy_s, d, 60) for d in ds]); rets = rets[~np.isnan(rets)]
    if len(rets) < 20:
        print(f"  {d1:<22s} N={len(rets):>4d} (insuf)")
        continue
    m, lo, hi = boot_ci_mean(rets); w, wl, wh = boot_ci_wr(rets)
    print(f"  {d1:<22s} N={len(rets):>4d}  f60d={m:+.2f}% CI95[{lo:+.2f},{hi:+.2f}]  WR={w*100:.0f}%")

# ── 3. POST-2011 quadrant robustness ──
print("\n═══ POST-2011 QUADRANT (robustness vs drift) ═══")
post = [dt for dt in dates if dt.date() >= date(2011, 1, 1)]
spy_11 = spy_s.loc[post]
sk_11 = skew_s.loc[post]; vx_11 = vix_s.loc[post]
sk_p15 = float(sk_11.quantile(0.15)); sk_p85 = float(sk_11.quantile(0.85))
vx_p85 = float(vx_11.quantile(0.85))
print(f"  Post-2011: SKEW P15={sk_p15:.1f} P85={sk_p85:.1f}  VIX P85={vx_p85:.1f}  (N={len(post)})")
sk_hi = sk_11 >= sk_p85; vx_hi = vx_11 >= vx_p85
quads = [
    ("PÁNICO TOTAL", sk_hi & vx_hi),
    ("Crisis sin miedo", (~sk_hi) & vx_hi),
    ("Miedo silencioso", sk_hi & (~vx_hi)),
    ("Calma total", (~sk_hi) & (~vx_hi)),
]
for qname, qm in quads:
    qd = [post[i] for i in range(len(post)) if qm.iloc[i]]
    rets60 = np.array([fwd(spy_11, d, 60) for d in qd]); rets60 = rets60[~np.isnan(rets60)]
    if len(rets60) < 5:
        print(f"  {qname:<20s} N={len(qd):>4d} (insuf)")
        continue
    m, lo, hi = boot_ci_mean(rets60); w, wl, wh = boot_ci_wr(rets60)
    print(f"  {qname:<20s} N={len(qd):>4d} ({len(qd)/len(post)*100:.1f}%)  f60d={m:+.2f}% CI95[{lo:+.2f},{hi:+.2f}]  WR={w*100:.0f}%")

# ── 4. SKEW ≥159 (BLACK_SWAN) event list ──
print("\n═══ SKEW ≥159 (BLACK_SWAN_PARANOIA) — eventos y forward 60d ═══")
bs = [dt for dt in dates if dt in skew_s.index and float(skew_s.loc[dt]) >= 159.31]
bs_dc = [bs[0]] if bs else []
for d in bs[1:]:
    if spy_s.index.get_loc(d) - spy_s.index.get_loc(bs_dc[-1]) >= 20:
        bs_dc.append(d)
print(f"  Eventos raw: {len(bs)}  de-clustered ≥20td: {len(bs_dc)}")
for d in bs_dc[:30]:
    print(f"    {d.date()}: SKEW={float(skew_s.loc[d]):.1f}  VIX={float(vix_s.loc[d]):.1f}  f60d={fwd(spy_s,d,60):+.1f}%")
