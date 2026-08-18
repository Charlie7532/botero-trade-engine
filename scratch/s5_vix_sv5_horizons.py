#!/usr/bin/env python3
"""Supplementary: SV5 discrimination (SV5↑ vs SV5↓) within each VIX×S5 regime
across ALL fixed horizons 5/10/20/40d. Complements s5_vix_sv5_triple.py."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/root/botero-trade")
sys.path.insert(0, str(ROOT))
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

N_BOOT = 3000
SEED = 42
FW = [5, 10, 20, 40]

def _rng(): return np.random.default_rng(SEED)

def boot_diff_ci(a, b):
    a = np.asarray(a, float); a = a[~np.isnan(a)]
    b = np.asarray(b, float); b = b[~np.isnan(b)]
    if len(a) < 5 or len(b) < 5:
        return np.nan, np.nan, np.nan, np.nan
    rng = _rng(); diffs = np.empty(N_BOOT)
    for i in range(N_BOOT):
        diffs[i] = rng.choice(a, len(a), replace=True).mean() - rng.choice(b, len(b), replace=True).mean()
    diffs.sort()
    return a.mean()-b.mean(), np.percentile(diffs,2.5), np.percentile(diffs,97.5), np.mean(diffs>0)

def norm_idx(s):
    s = s.copy(); s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()

store = TimescaleDataStore()
vix = norm_idx(store.load_bars("VIX","1d")["close"])
s5 = norm_idx(store.load_bars("S5TW","1d")["close"])
sv5 = norm_idx(store.load_bars("SV5TW","1d")["close"])
spy = norm_idx(store.load_bars("SPY","1d")["close"])
store.close()

common = sorted(set(vix.index)&set(s5.index)&set(sv5.index)&set(spy.index))
vv = vix.diff(3).reindex(common).values
sv = s5.diff(3).reindex(common).values
svv = sv5.diff(3).reindex(common).values
px = spy.reindex(common).values
n = len(common)

REGIME = {(1,1):"1 MIEDO SIN VENTA",(1,0):"2 MIEDO CON VENTA",(0,1):"3 CALMA CON AMPLITUD",(0,0):"4 CALMA SIN CONVICCIÓN"}

# precompute masks
valid = ~(np.isnan(vv)|np.isnan(sv)|np.isnan(svv))
idx_valid = np.where(valid)[0]
vix_up = (vv>0)[valid]; s5_up = (sv>0)[valid]; sv5_up = (svv>0)[valid]
px_v = px[valid]

def sig_returns(mask, h):
    out=[]; last=-11
    for i in np.where(mask)[0]:
        if i-last>=10 and i+h<len(px_v):
            out.append(px_v[i+h]/px_v[i]-1.0); last=i
    return out

print(f"{'Régimen':<28}{'h':>3} {'N↑':>5} {'N↓':>5} {'ret↑':>7} {'ret↓':>7} {'Δ(SV5↑−SV5↓)':>14} {'CI95':>22} {'p(↑>↓)':>8}  SIG")
for (vu,su),label in REGIME.items():
    base = (vix_up==vu)&(s5_up==su)
    for h in FW:
        r_up = sig_returns(base&(sv5_up==1), h)
        r_dn = sig_returns(base&(sv5_up==0), h)
        if len(r_up)<5 or len(r_dn)<5:
            continue
        diff,lo,hi,pos = boot_diff_ci(r_up,r_dn)
        sig = "← CI excl 0" if (lo>0 or hi<0) else ""
        print(f"{label:<28}{h:>3} {len(r_up):>5} {len(r_dn):>5} {np.mean(r_up):>+7.2%} {np.mean(r_dn):>+7.2%} {diff:>+14.2%} [{lo:+.2%},{hi:+.2%}] {pos:>8.0%}  {sig}")
