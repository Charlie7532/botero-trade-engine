"""Get raw SKEW distribution from DB."""
import sys
sys.path.insert(0, '/root/botero-trade/backend')
sys.path.insert(0, '/root/botero-trade')
import numpy as np
import pandas as pd
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.entry_decision.domain.rules.skew_lookup import SkewLookupAdapter

store = TimescaleDataStore()
raw = store.load_bars("SKEW", "1d")["close"].copy()
raw.index = pd.to_datetime(raw.index).normalize()
vals = raw[~raw.index.duplicated(keep="last")].sort_index()

print(f"SKEW bars: {len(vals)} rows")
print(f"Date range: {vals.index[0].date()} to {vals.index[-1].date()}")

print("\n=== SKEW RAW DISTRIBUTION ===")
print(f"  min:    {vals.min():.2f}")
print(f"  P1:     {np.percentile(vals, 1):.2f}")
print(f"  P2.5:   {np.percentile(vals, 2.5):.2f}")
print(f"  P5:     {np.percentile(vals, 5):.2f}")
print(f"  P10:    {np.percentile(vals, 10):.2f}")
print(f"  P25:    {np.percentile(vals, 25):.2f}")
print(f"  P50:    {np.percentile(vals, 50):.2f}")
print(f"  mean:   {vals.mean():.2f}")
print(f"  std:    {vals.std():.2f}")
print(f"  P75:    {np.percentile(vals, 75):.2f}")
print(f"  P90:    {np.percentile(vals, 90):.2f}")
print(f"  P95:    {np.percentile(vals, 95):.2f}")
print(f"  P97.5:  {np.percentile(vals, 97.5):.2f}")
print(f"  P99:    {np.percentile(vals, 99):.2f}")
print(f"  max:    {vals.max():.2f}")

# Gaussian sigma mapping
mu = vals.mean()
sig = vals.std()
print(f"\n=== GAUSSIAN SIGMA BINS (μ={mu:.2f}, σ={sig:.2f}) ===")
for k in range(-3, 4):
    edge = mu + k * sig
    pct = 100 * (vals < edge).sum() / len(vals)
    print(f"  μ{k:+d}σ = {edge:.2f}  →  {pct:.1f}% below")

# Fact store documented edges vs percentiles
print("\n=== FACT STORE EDGES vs ACTUAL PERCENTILES ===")
edges = [109.1, 113.483649, 120.435, 136.436351, 153.650508]
labels = ['LOW_TAIL_RISK (<{})', 'NORMAL ({}-{})', 'ELEVATED ({}-{})', 
          'HIGH ({}-{})', 'TAIL_PARANOIA ({}-{})', 'BLACK_SWAN (≥{})']
for i, e in enumerate(edges):
    pct_below = 100 * (vals < e).sum() / len(vals)
    print(f"  {e:10.2f}: {pct_below:5.2f}% below → {pct_below/100:.4f} quantile")

print(f"  {'max':>10}: {100:.2f}% below")

# Full histogram
print("\n=== HISTOGRAM ===")
bins = [-np.inf] + edges + [np.inf]
for i in range(len(bins)-1):
    lo = bins[i]
    hi = bins[i+1]
    if i == 0:
        cnt = (vals < hi).sum()
    elif i == len(bins)-2:
        cnt = (vals >= lo).sum()
    else:
        cnt = ((vals >= lo) & (vals < hi)).sum()
    pct = 100 * cnt / len(vals)
    print(f"  {labels[i].format(lo, hi)}: N={cnt:5d} ({pct:5.2f}%)")

# Classify every bar
print("\n=== CLASSIFIED BARS ===")
adapter = SkewLookupAdapter()
from collections import Counter
class_counts = Counter()
low_tail_dates = []
for dt in vals.index:
    cat = adapter._classify_d1(float(vals[dt]))
    class_counts[cat] += 1
    if cat == "LOW_TAIL_RISK":
        low_tail_dates.append(dt)

for label in adapter.labels_d1:
    print(f"  {label}: {class_counts.get(label, 0):5d} bars ({100*class_counts.get(label,0)/len(vals):.2f}%)")

# Cluster LOW_TAIL_RISK into episodes
print(f"\n=== LOW_TAIL_RISK EPISODES ({len(low_tail_dates)} raw bars) ===")
if low_tail_dates:
    low_tail_dates.sort()
    episodes = []
    current_ep = [low_tail_dates[0]]
    for i in range(1, len(low_tail_dates)):
        gap = (low_tail_dates[i] - low_tail_dates[i-1]).days
        if gap > 10:
            episodes.append(current_ep)
            current_ep = [low_tail_dates[i]]
        else:
            current_ep.append(low_tail_dates[i])
    episodes.append(current_ep)
    
    print(f"  Total episodes (≥10d gap): {len(episodes)}")
    for i, ep in enumerate(episodes):
        ep_dates = sorted(ep)
        print(f"  Episode {i+1}: {ep_dates[0].date()} to {ep_dates[-1].date()}, {len(ep)} bars")
        
    # Print all LOW_TAIL_RISK dates
    print(f"\n  All LOW_TAIL_RISK dates:")
    for d in sorted(low_tail_dates):
        print(f"    {d.date()}: SKEW={vals[d]:.2f}")