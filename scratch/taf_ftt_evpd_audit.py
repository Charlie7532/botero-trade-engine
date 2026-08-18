#!/usr/bin/env python3
"""
TAF AUDIT — ftt_days & ev_per_day predictive signal on SPY forward.
Layer 1 audit. Read-only. No code modification.

Uses the pre-built scratch/quants_obs.pkl (1,590 SPY zz25 pivots, generated with the
PRODUCTION LookupAdapters -> state_key matches fact stores exactly) and joins each
pivot's per-station state_key against zigzag_kinematic.{zz25,zz50,zz75} in the fact
stores to extract ftt_bull_days / ftt_bear_days / ev_per_day.

Targets ("SPY forward"):
  - daily_return_pct  : realized forward return per day of the leg starting at pivot
  - duration_bars     : realized duration (bars) of that leg
  - fwd_total_ret     : daily_return_pct * duration_bars  (total leg return %)
"""
import json, os, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path('/root/botero-trade')
FS_DIR = ROOT / 'backend/modules/entry_decision/domain/rules'

# stations with fact stores, exactly as the compositor's taf_station_codes
TAF_STATIONS = ["vix", "bsi", "fg", "credit", "rotation",
                "sv5_turbulence", "skew", "pcr", "vvix", "yield_curve", "dxy"]

# ── Load fact stores: state_key -> zigzag_kinematic per scale ──────────────
fact = {}
for code in TAF_STATIONS:
    fp = FS_DIR / f"{code}_fact_store.json"
    with open(fp) as f:
        fs = json.load(f)
    states = fs.get("states", {})
    lookup = {}
    for sk, sd in states.items():
        zk = sd.get("zigzag_kinematic", {})
        entry = {}
        for scale in ("zz25", "zz50", "zz75"):
            zz = zk.get(scale, {})
            entry[scale] = {
                "ftt_bull_days": zz.get("ftt_bull_days"),
                "ftt_bear_days": zz.get("ftt_bear_days"),
                "ev_per_day": zz.get("ev_per_day"),
                "e_days": zz.get("e_days"),
                "n_pos": zz.get("n_pos"),
                "n_neg": zz.get("n_neg"),
            }
        lookup[sk] = entry
    fact[code] = lookup

# ── Load pivot observations ────────────────────────────────────────────────
obs = pd.read_pickle(ROOT / 'scratch/quants_obs.pkl')
obs = obs.reset_index(drop=True)
N = len(obs)
print(f"pivots: {N}")
print(f"  leg_bear (next-leg bear=1): mean={obs['leg_bear'].mean():.3f}")
print(f"  daily_return_pct: mean={obs['daily_return_pct'].mean():.4f}  std={obs['daily_return_pct'].std():.4f}")
print(f"  duration_bars: mean={obs['duration_bars'].mean():.2f}  std={obs['duration_bars'].std():.2f}")

# forward total return (daily_return_pct is %/day -> * duration_bars = %)
obs["fwd_total_ret"] = obs["daily_return_pct"] * obs["duration_bars"]

# ── Join ftt/ev_per_day per station ────────────────────────────────────────
# build columns per station
rows = []
for code in TAF_STATIONS:
    sk_col = f"{code}_sk"
    if sk_col not in obs.columns:
        print(f"  WARN: missing {sk_col}")
        continue
    # direction-specific ftt: bull leg (leg_bear=0) -> ftt_bull, bear -> ftt_bear
    ft, ev, ed = [], [], []
    hit = 0
    for _, r in obs.iterrows():
        sk = r[sk_col]
        entry = fact[code].get(sk)
        if entry is None:
            ft.append(np.nan); ev.append(np.nan); ed.append(np.nan)
            continue
        zz = entry["zz25"]
        if zz["ftt_bull_days"] is None:
            ft.append(np.nan); ev.append(np.nan); ed.append(np.nan)
            continue
        hit += 1
        lb = int(r["leg_bear"])
        ftt = zz["ftt_bull_days"] if lb == 0 else zz["ftt_bear_days"]
        ft.append(ftt)
        ev.append(zz["ev_per_day"])
        ed.append(zz["e_days"])
    obs[f"{code}_ftt"] = ft
    obs[f"{code}_evpd"] = ev
    obs[f"{code}_edays"] = ed
    print(f"  {code:16s} state_key match: {hit}/{N} ({100*hit/N:.1f}%)")

# ── Composite (mean across stations, skip NaN) ─────────────────────────────
ftt_cols = [f"{c}_ftt" for c in TAF_STATIONS]
evpd_cols = [f"{c}_evpd" for c in TAF_STATIONS]
edays_cols = [f"{c}_edays" for c in TAF_STATIONS]
obs["comp_ftt"] = obs[ftt_cols].mean(axis=1, skipna=True)
obs["comp_evpd"] = obs[evpd_cols].mean(axis=1, skipna=True)
obs["comp_edays"] = obs[edays_cols].mean(axis=1, skipna=True)

def rho_t(x, y):
    """Spearman rho + t-stat + p-value on pairwise-complete rows."""
    m = x.notna() & y.notna()
    n = int(m.sum())
    if n < 5:
        return (np.nan, np.nan, np.nan, n)
    r, p = spearmanr(x[m], y[m])
    if np.isnan(r):
        return (np.nan, np.nan, np.nan, n)
    denom = max(1.0 - r*r, 1e-12)
    t = r * np.sqrt((n - 2) / denom)
    return (r, t, p, n)

def report(label, x, y):
    r, t, p, n = rho_t(x, y)
    star = "***" if (p is not None and not np.isnan(p) and p < 0.001) else ("**" if (p is not None and not np.isnan(p) and p < 0.01) else ("*" if (p is not None and not np.isnan(p) and p < 0.05) else ""))
    print(f"  {label:52s} ρ={r:+.4f}  t={t:+.2f}  p={p:.4f}  n={n}  {star}")

print("\n" + "=" * 100)
print("A. COMPOSITE (mean over 11 stations)")
print("=" * 100)
report("comp_ftt   -> duration_bars (duration calibration)", obs["comp_ftt"], obs["duration_bars"])
report("comp_ftt   -> daily_return_pct (dur predicts ret/day)", obs["comp_ftt"], obs["daily_return_pct"])
report("comp_ftt   -> fwd_total_ret", obs["comp_ftt"], obs["fwd_total_ret"])
report("comp_evpd  -> daily_return_pct (EV/day -> ret/day)", obs["comp_evpd"], obs["daily_return_pct"])
report("comp_evpd  -> fwd_total_ret (EV/day -> total ret)", obs["comp_evpd"], obs["fwd_total_ret"])
report("comp_edays -> duration_bars", obs["comp_edays"], obs["duration_bars"])

print("\n" + "=" * 100)
print("B. PER-STATION — ftt_direction -> duration_bars  and  ev_per_day -> daily_return_pct")
print("=" * 100)
print(f"  {'station':16s} {'ftt->dur':>12s} {'ftt->dur t':>11s} {'evpd->retday':>13s} {'evpd->retday t':>14s} {'n':>5s}")
for code in TAF_STATIONS:
    r1, t1, p1, n1 = rho_t(obs[f"{code}_ftt"], obs["duration_bars"])
    r2, t2, p2, n2 = rho_t(obs[f"{code}_evpd"], obs["daily_return_pct"])
    print(f"  {code:16s} {r1:+12.4f} {t1:+11.2f} {r2:+13.4f} {t2:+14.2f} {n1:5d}")

print("\n" + "=" * 100)
print("C. PER-STATION — ev_per_day -> fwd_total_ret  (EV/day -> total leg return)")
print("=" * 100)
for code in TAF_STATIONS:
    r, t, p, n = rho_t(obs[f"{code}_evpd"], obs["fwd_total_ret"])
    star = "***" if (p is not None and not np.isnan(p) and p < 0.001) else ("**" if (p is not None and not np.isnan(p) and p < 0.01) else ("*" if (p is not None and not np.isnan(p) and p < 0.05) else ""))
    print(f"  {code:16s} ρ={r:+.4f}  t={t:+.2f}  p={p:.4f}  n={n}  {star}")

# ── Multi-scale: does zz50/zz75 ev_per_day / ftt add anything over zz25? ───
print("\n" + "=" * 100)
print("D. MULTI-SCALE — ev_per_day / ftt per scale (composite over 11 stations), target = zz25 leg")
print("=" * 100)
for scale in ("zz25", "zz50", "zz75"):
    ftt_list, ev_list = [], []
    for code in TAF_STATIONS:
        sk_col = f"{code}_sk"
        cftt = []; cev = []
        for _, r in obs.iterrows():
            entry = fact[code].get(r[sk_col])
            if entry is None:
                cftt.append(np.nan); cev.append(np.nan); continue
            zz = entry[scale]
            if zz["ftt_bull_days"] is None:
                cftt.append(np.nan); cev.append(np.nan); continue
            lb = int(r["leg_bear"])
            cftt.append(zz["ftt_bull_days"] if lb == 0 else zz["ftt_bear_days"])
            cev.append(zz["ev_per_day"])
        ftt_list.append(cftt); ev_list.append(cev)
    s_ftt = pd.Series(np.nanmean(np.array(ftt_list), axis=0))
    s_ev = pd.Series(np.nanmean(np.array(ev_list), axis=0))
    r1, t1, p1, n1 = rho_t(s_ftt, obs["duration_bars"])
    r2, t2, p2, n2 = rho_t(s_ev, obs["daily_return_pct"])
    r3, t3, p3, n3 = rho_t(s_ev, obs["fwd_total_ret"])
    print(f"  {scale}: ftt->dur ρ={r1:+.4f} (t={t1:+.2f}, n={n1}) | evpd->retday ρ={r2:+.4f} (t={t2:+.2f}) | evpd->totret ρ={r3:+.4f} (t={t3:+.2f})")

print("\nDONE")
